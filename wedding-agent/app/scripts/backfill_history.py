"""一次性回填（上线「操作人」和用量记录之前的任务），只填能从存档确定的数，并标为回填：

1. 任务操作人：任务第一个检查点的时间 ↔ 后端日志里同一时刻（3 秒内）的 POST /api/tasks 的来源 IP
   ↔ 当前绑定该 IP 的用户站设备持有人。对不上就不填（后台显示 —），operator_source 记 "backfill"。
2. 生图：后端日志里每次 generation_attempt（成功的）带 Seedream 响应里的真实 usage（output_tokens、generated_images、
   request_id），逐条回填（source=journal，步骤 generate）；日志覆盖不到的部分再用任务存档里的 total_images
   补一条下限（source=archive）。已有实时记录（同任务 120 秒内）的不再回填；按 request_id 去重，可重复运行。
   对话模型（DeepSeek）的 token 日志和存档里都没有，不回填——以 platform.deepseek.com 的用量导出为准（后台可导入）。
   用量条目带 backfilled: true；改写用量文件前自动备份。

用法（服务器 wedding-agent 目录）：
  sudo journalctl -u wedding-backend --no-pager -o short-iso | .venv/bin/python -m app.scripts.backfill_history [--apply]
不加 --apply 只打印将要写入的内容。重复运行不会重复写（已回填的任务跳过）。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime

from app import access
from app.common import usage
from app.common.config import settings

ATTEMPT = re.compile(r"^(\S+) .*?\[(t_[0-9a-f]+)\] wedding\.generation: generation_attempt (\{.*\})\s*$")
POST = re.compile(r"^(\S+) .*? (\d+\.\d+\.\d+\.\d+):\d+ - \"POST /api/tasks HTTP")


def first_and_last_state():
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serde = JsonPlusSerializer()
    conn = sqlite3.connect(f"file:{settings.state_dir / 'checkpoints.sqlite'}?mode=ro", uri=True)
    result = {}
    for (thread,) in conn.execute("SELECT DISTINCT thread_id FROM checkpoints"):
        rows = conn.execute("SELECT type, checkpoint FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id", (thread,)).fetchall()
        first, last = serde.loads_typed(rows[0]), serde.loads_typed(rows[-1])
        result[thread] = (datetime.fromisoformat(first["ts"]).timestamp(), datetime.fromisoformat(last["ts"]).timestamp(), last["channel_values"])
    return result


def _write_operator(task_id: str, holder: str) -> None:
    """直接改任务文件（不经 TaskStore，它读取时会刷新文件时间）并保留原修改时间（后台「更新」列不变，也不会改动任务状态）。"""
    path = settings.state_dir / "tasks" / f"{task_id}.json"
    stat = path.stat()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(operator=holder, operator_source="backfill")
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.utime(path, (stat.st_atime, stat.st_mtime))


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    posts, attempts = [], []
    for line in sys.stdin:
        match = POST.match(line)
        if match:
            posts.append((datetime.fromisoformat(match.group(1)).timestamp(), match.group(2)))
            continue
        match = ATTEMPT.match(line)
        if match:
            try:
                event = json.loads(match.group(3))
            except ValueError:
                continue
            if event.get("status") == "succeeded" and event.get("engine") == "seedream":
                attempts.append((datetime.fromisoformat(match.group(1)).timestamp(), match.group(2), event))
    devices = sorted((d for d in access._load()["devices"].values() if d.get("kind", "site") == "site" and d.get("ip")),
                     key=lambda d: d.get("last_seen", 0))
    ip_holder = {d["ip"]: d["holder"] for d in devices}  # 后面的（最近的）覆盖前面的
    existing = usage.read()
    live = [(e["task_id"], e["at"]) for e in existing if e.get("provider") == "seedream" and not e.get("backfilled")]
    seen = {e.get("request_id") for e in existing if e.get("request_id")}
    new_entries: list[dict] = []
    journal_images: dict[str, int] = {}
    for at, task_id, event in attempts:
        response = event.get("response") or {}
        used = response.get("usage") or {}
        rid = response.get("request_id")
        if rid in seen or any(t == task_id and abs(a - at) < 120 for t, a in live):
            journal_images[task_id] = journal_images.get(task_id, 0) + int(used.get("generated_images", 1))
            continue
        seen.add(rid)
        images = int(used.get("generated_images", 1))
        journal_images[task_id] = journal_images.get(task_id, 0) + images
        new_entries.append({"at": at, "task_id": task_id, "step": "generate", "provider": "seedream",
                            "model": response.get("model") or event.get("model"), "kind": "image",
                            "input": int(used.get("input_tokens", 0)), "cached": 0, "output": int(used.get("output_tokens", 0)),
                            "total": int(used.get("total_tokens", used.get("output_tokens", 0))), "images": images,
                            "backfilled": True, "source": "journal", "request_id": rid})
    replace_tasks = set()
    for task_id, (created, updated, values) in sorted(first_and_last_state().items(), key=lambda x: x[1][0]):
        path = settings.state_dir / "tasks" / f"{task_id}.json"
        if not path.exists():
            continue
        if not json.loads(path.read_text(encoding="utf-8")).get("operator"):
            near = [ip for at, ip in posts if 0 <= created - at <= 3]
            holder = ip_holder.get(near[-1]) if near else None
            print(f"{task_id} 操作人 {holder or '—'}（IP {near[-1] if near else '无记录'}）")
            if holder and apply:
                _write_operator(task_id, holder)
        generation = values.get("generation") or {}
        archived = (generation.get("total_images") or 0) if generation.get("engine") == "seedream" else 0
        rest = archived - journal_images.get(task_id, 0)
        replace_tasks.add(task_id)
        if rest > 0:  # 日志覆盖不到的部分：只知道张数下限
            new_entries.append({"at": updated, "task_id": task_id, "step": "generate", "provider": "seedream",
                                "model": settings.seedream_model, "kind": "image", "input": 0, "cached": 0, "output": 0,
                                "total": 0, "images": rest, "backfilled": True, "source": "archive"})
    tokens = sum(e["output"] for e in new_entries)
    print(f"日志：成功生图请求 {len(attempts)} 次；新回填 {sum(1 for e in new_entries if e['source'] == 'journal')} 条，"
          f"{sum(e['images'] for e in new_entries if e['source'] == 'journal')} 张，输出 token {tokens}")
    print(f"存档补下限：{sum(e['images'] for e in new_entries if e['source'] == 'archive')} 张")
    if apply:
        # 旧的存档下限条目（source 为空或 archive）整体替换为本次结果；日志条目保留并按 request_id 去重
        dropped = usage.rewrite(lambda e: not (e.get("backfilled") and e.get("provider") == "seedream"
                                               and e.get("source") in (None, "archive") and e.get("task_id") in replace_tasks),
                                new_entries)
        print(f"已写入，替换旧回填 {dropped} 条")
    else:
        print("（预览，加 --apply 写入）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
