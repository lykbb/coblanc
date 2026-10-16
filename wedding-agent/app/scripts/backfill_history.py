"""一次性回填（上线「操作人」和用量记录之前的任务），只填能从存档确定的数，并标为回填：

1. 任务操作人：任务第一个检查点的时间 ↔ 后端日志里同一时刻（3 秒内）的 POST /api/tasks 的来源 IP
   ↔ 当前绑定该 IP 的用户站设备持有人。对不上就不填（后台显示 —），operator_source 记 "backfill"。
2. 生图张数：任务存档里最后一次生成记录的 total_images（Seedream），只是下限（之前被覆盖的批次查不到）；
   对话模型的 token 存档里没有，不回填。用量条目带 backfilled: true。

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
from app.common.progress import store  # 只读

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
    """直接改任务文件并保留原修改时间（后台「更新」列不变，也不会改动任务状态）。"""
    path = settings.state_dir / "tasks" / f"{task_id}.json"
    stat = path.stat()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(operator=holder, operator_source="backfill")
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.utime(path, (stat.st_atime, stat.st_mtime))


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    posts = []
    for line in sys.stdin:
        match = POST.match(line)
        if match:
            posts.append((datetime.fromisoformat(match.group(1)).timestamp(), match.group(2)))
    devices = sorted((d for d in access._load()["devices"].values() if d.get("kind", "site") == "site" and d.get("ip")),
                     key=lambda d: d.get("last_seen", 0))
    ip_holder = {d["ip"]: d["holder"] for d in devices}  # 后面的（最近的）覆盖前面的
    already = {e.get("task_id") for e in usage.read() if e.get("backfilled")}
    for task_id, (created, updated, values) in sorted(first_and_last_state().items(), key=lambda x: x[1][0]):
        info = store.get(task_id)
        if info is None:
            continue
        if not info.operator:
            near = [ip for at, ip in posts if 0 <= created - at <= 3]
            holder = ip_holder.get(near[-1]) if near else None
            print(f"{task_id} 操作人 {holder or '—'}（IP {near[-1] if near else '无记录'}）")
            if holder and apply:
                _write_operator(task_id, holder)
        generation = values.get("generation") or {}
        images = generation.get("total_images") or 0
        if images and generation.get("engine") == "seedream" and task_id not in already:
            print(f"{task_id} 生图 ≥{images} 张（{settings.seedream_model}）")
            if apply:
                usage.record("seedream", settings.seedream_model, "image", images=images, at=updated, task_id=task_id, backfilled=True)
    if not apply:
        print("（预览，加 --apply 写入）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
