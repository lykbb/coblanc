"""任务过程记录：每个任务一份 state_dir/traces/<任务>.jsonl，后台任务详情只读展示。

记两类：每次对话模型调用（步骤、模型、完整输入消息、输出、用量），每次生图请求（完整提示词、参数、参考图、响应元数据、状态）。
写入前统一脱敏：密钥类字段打码，图片 base64 换成占位，超长文本截断。记录失败不影响业务。
"""

from __future__ import annotations

import json
import re
import threading
import time

from app.common.config import settings
from app.common.log import current_step, current_task

_lock = threading.Lock()
_SECRET_KEY = re.compile(r"(?i)(api[_-]?key|secret|password|passwd|authorization|cookie|^token$|access[_-]?token|bearer)")
_SECRET_VALUE = re.compile(r"\b(sk-[A-Za-z0-9_\-]{12,}|Bearer\s+\S+)")
_DATA_URL = re.compile(r"^data:(image/[a-z+]+);base64,", re.I)
MAX_TEXT = 40000
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")


def mask(value, key: str = ""):
    if key and _SECRET_KEY.search(key):
        return "***"
    if isinstance(value, dict):
        return {k: mask(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(v) for v in value]
    if isinstance(value, str):
        found = _DATA_URL.match(value)
        if found:
            return f"[{found.group(1)} {len(value) * 3 // 4 // 1024} KB]"
        value = _SECRET_VALUE.sub("***", value)
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"…（截断，共 {len(value)} 字）"
    return value


def _path(task_id: str):
    return settings.state_dir / "traces" / f"{task_id}.jsonl" if _ID.match(task_id or "") else None


def add(kind: str, data: dict, task_id: str | None = None) -> None:
    path = _path(task_id or current_task.get())
    if path is None:
        return
    entry = {"at": time.time(), "step": current_step.get(), "kind": kind, **mask(data)}
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def read(task_id: str) -> list[dict]:
    path = _path(task_id)
    if path is None or not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            items.append(json.loads(line))
        except ValueError:
            continue
    return items


def delete(task_id: str) -> None:
    path = _path(task_id)
    if path is not None:
        path.unlink(missing_ok=True)
