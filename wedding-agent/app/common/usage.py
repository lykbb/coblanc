"""模型用量记录：只记真实 API 响应里返回的用量（对话模型的 token、生图的张数和 usage），写 state_dir/usage.jsonl。

- 对话模型：get_llm 给模型挂 UsageCallback，每次调用结束从响应的 usage_metadata / token_usage 取数。
- 生图：Seedream 记响应里的 usage 和张数；RunningHub 不返回 token，只记一次调用和张数。
- 费用估算只按 state_dir/token_prices.json 里填的单价算（不填就不估）：
  {"模型名": {"input_per_million": 2, "output_per_million": 8, "per_image": 0.25, "currency": "CNY"}}
"""

from __future__ import annotations

import json
import threading
import time

from langchain_core.callbacks import BaseCallbackHandler

from app.common.config import settings
from app.common.log import current_task

_lock = threading.Lock()


def _path():
    return settings.state_dir / "usage.jsonl"


def record(provider: str, model: str, kind: str, input_tokens: int = 0, output_tokens: int = 0,
           total_tokens: int | None = None, images: int = 0) -> None:
    task = current_task.get()
    entry = {"at": time.time(), "task_id": None if task == "-" else task, "provider": provider, "model": model or "?",
             "kind": kind, "input": int(input_tokens or 0), "output": int(output_tokens or 0),
             "total": int(total_tokens if total_tokens is not None else (input_tokens or 0) + (output_tokens or 0)),
             "images": int(images or 0)}
    try:
        with _lock:
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 记账失败不影响业务


def read(since: float = 0) -> list[dict]:
    try:
        lines = _path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    items = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("at", 0) >= since:
            items.append(entry)
    return items


def prices() -> dict:
    try:
        data = json.loads((settings.state_dir / "token_prices.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def cost(entry: dict, table: dict) -> tuple[float, str] | None:
    price = table.get(entry["model"])
    if not isinstance(price, dict):
        return None
    value = (entry["input"] * float(price.get("input_per_million", 0)) + entry["output"] * float(price.get("output_per_million", 0))) / 1e6
    value += entry["images"] * float(price.get("per_image", 0))
    return value, str(price.get("currency", "CNY"))


class UsageCallback(BaseCallbackHandler):
    """挂在对话模型上：每次调用结束记一条真实用量。"""

    def __init__(self, provider: str, model: str, kind: str) -> None:
        self.provider, self.model, self.kind = provider, model, kind

    def on_llm_end(self, response, **kwargs) -> None:
        found = False
        for generations in response.generations or []:
            for generation in generations:
                meta = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if meta:
                    record(self.provider, self.model, self.kind, meta.get("input_tokens", 0), meta.get("output_tokens", 0), meta.get("total_tokens"))
                    found = True
        if not found:
            usage = (response.llm_output or {}).get("token_usage") or {}
            if usage:
                record(self.provider, (response.llm_output or {}).get("model_name") or self.model, self.kind,
                       usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("total_tokens"))
