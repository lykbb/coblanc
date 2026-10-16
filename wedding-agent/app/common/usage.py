"""模型用量与费用（框架维护）：只记真实 API 响应里返回的用量，写 state_dir/usage.jsonl；单价见同目录 prices.json。

每条记录：at、task_id、step（流水线步骤 = graph 节点名）、provider、model、kind（agent/cheap/vision/image）、
input（含缓存命中）、cached（缓存命中的输入）、output、total、images；回填的旧任务带 backfilled。
- 对话模型：get_llm 挂 UsageCallback，调用结束取 usage_metadata / token_usage（含缓存命中数），同时写任务过程记录。
- 生图：Seedream 记响应里的 usage 和张数；RunningHub 不返回 token，只记张数。
- 费用：按 prices.json 里的官方公开价算（CNY）；DeepSeek 按请求时刻的北京时间分高峰/空闲；verified=false 的不算。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

from app.common import trace
from app.common.config import settings
from app.common.log import current_step, current_task

_lock = threading.Lock()
PRICES_FILE = Path(__file__).with_name("prices.json")
BEIJING = timezone(timedelta(hours=8))

# graph 节点名 → 页面上显示的 agent / 步骤
STEPS = {
    "intake": "小囍·接单", "compose": "小囍·写最终提示词", "reveal": "小囍·揭幕寄语",
    "style": "妆造师", "frame": "摄影师", "generate": "生图", "check": "修图师·质检",
    "retouch": "修图师·修图方案", "make_previews": "物料·预览", "package": "物料·套版",
}


def step_label(step: str | None) -> str:
    if not step or step == "-":
        return "未标注（旧记录）"
    return STEPS.get(step, step)


def _path():
    return settings.state_dir / "usage.jsonl"


def record(provider: str, model: str, kind: str, input_tokens: int = 0, output_tokens: int = 0,
           total_tokens: int | None = None, images: int = 0, *, cached_tokens: int = 0, at: float | None = None,
           task_id: str | None = None, step: str | None = None, backfilled: bool = False, **extra) -> None:
    """backfilled=True：事后还原的记录（页面标「回填」）；extra 可带 source（journal / archive / deepseek_export）、
    request_id、requests（账单里的请求次数）、billed（账单金额，元）。"""
    task = task_id or current_task.get()
    stage = step or current_step.get()
    entry = {"at": at or time.time(), "task_id": None if task == "-" else task, "step": None if stage == "-" else stage,
             "provider": provider, "model": model or "?", "kind": kind,
             "input": int(input_tokens or 0), "cached": int(cached_tokens or 0), "output": int(output_tokens or 0),
             "total": int(total_tokens if total_tokens is not None else (input_tokens or 0) + (output_tokens or 0)),
             "images": int(images or 0), **({"backfilled": True} if backfilled else {}),
             **{k: v for k, v in extra.items() if k in EXTRA and v is not None}}
    try:
        with _lock:
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 记账失败不影响业务


EXTRA = {"source", "request_id", "requests", "billed"}


def rewrite(keep, add: list[dict]) -> int:
    """改写用量文件（回填、导入用）：保留 keep(entry) 为真的条目，追加 add；先备份为 usage.jsonl.bak-<时间>。返回去掉的条数。"""
    with _lock:
        path = _path()
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if lines:
            path.with_name(f"usage.jsonl.bak-{time.strftime('%Y%m%d-%H%M%S')}").write_text("\n".join(lines) + "\n", encoding="utf-8")
        kept, dropped = [], 0
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                kept.append(line)
                continue
            if keep(entry):
                kept.append(line)
            else:
                dropped += 1
        kept += [json.dumps(e, ensure_ascii=False) for e in add]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        tmp.replace(path)
    return dropped


def read(since: float = 0, task_id: str | None = None) -> list[dict]:
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
        if entry.get("at", 0) >= since and (task_id is None or entry.get("task_id") == task_id):
            entry.setdefault("cached", 0)
            if not entry.get("step"):
                entry["step"] = "generate" if entry.get("kind") == "image" else None  # 生图只发生在生图步骤
            items.append(entry)
    return items


# ---- 单价 ----


@lru_cache(maxsize=1)
def price_table() -> dict:
    return json.loads(PRICES_FILE.read_text(encoding="utf-8"))


def price_for(provider: str, model: str) -> dict | None:
    for item in price_table()["models"]:
        names = [item["match"], *item.get("aliases", [])]
        if any((model or "").startswith(name) for name in names) or provider == item["match"]:
            return item
    return None


def is_peak(at: float) -> bool:
    moment = datetime.fromtimestamp(at, BEIJING)
    minutes = moment.hour * 60 + moment.minute
    return moment.weekday() < 5 and (540 <= minutes < 720 or 840 <= minutes < 1080)


def cost(entry: dict) -> float | None:
    """这一条的费用（元）：账单导入的用账单金额；否则按官方单价；没有可核实的官方单价返回 None。"""
    if entry.get("billed") is not None:
        return float(entry["billed"])
    price = price_for(entry.get("provider", ""), entry.get("model", ""))
    if not price or not price.get("verified"):
        return None
    if price["unit"] == "per_image":
        return entry.get("images", 0) * float(price["per_image"])
    tier = price["tiers"]["peak" if is_peak(entry["at"]) else "offpeak"]
    cached = min(entry.get("cached", 0), entry.get("input", 0))
    return ((entry.get("input", 0) - cached) * tier["input"] + cached * tier["cache_hit"]
            + entry.get("output", 0) * tier["output"]) / 1e6


# ---- DeepSeek 账单导入（platform.deepseek.com 用量导出，唯一权威来源） ----

_COLUMNS = [  # (字段, 表头关键词)；先匹配前面的
    ("cached", ("缓存命中", "命中缓存", "cache hit", "cache_hit", "hit")),
    ("miss", ("未命中", "cache miss", "cache_miss", "miss")),
    ("output", ("输出", "output", "completion")),
    ("input", ("输入", "input", "prompt")),
    ("requests", ("请求", "次数", "request", "calls")),
    ("billed", ("金额", "费用", "花费", "消费", "cost", "amount", "price")),
    ("model", ("模型", "model")),
    ("date", ("日期", "时间", "date", "time", "day")),
]


def _number(value: str) -> float:
    value = (value or "").replace(",", "").replace("¥", "").replace("￥", "").strip()
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def parse_deepseek_export(text: str) -> list[dict]:
    """解析 DeepSeek 用量导出 CSV：按（日期, 模型）汇总成用量条目（provider=deepseek-export，按天，无任务/步骤）。
    认表头关键词（中英文）；缺日期或模型列、没有任何 token 列时报 ValueError。"""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        raise ValueError("文件是空的")
    columns: dict[str, int] = {}
    for index, header in enumerate(rows[0]):
        name = header.strip().lower()
        for field, words in _COLUMNS:
            if field not in columns and any(w in name for w in words):
                columns[field] = index
                break
    if "date" not in columns or "model" not in columns or not ({"input", "miss", "cached", "output"} & set(columns)):
        raise ValueError("认不出表头：需要日期、模型和 token 列（输入/缓存命中/未命中/输出）")
    merged: dict[tuple, dict] = {}
    for row in rows[1:]:
        if len(row) < len(rows[0]) or not row[columns["date"]].strip():
            continue
        raw = row[columns["date"]].strip().replace("/", "-")[:10]
        try:
            day = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        model = row[columns["model"]].strip() or "?"
        get = lambda f: _number(row[columns[f]]) if f in columns else 0.0
        cached = get("cached")
        entry = merged.setdefault((day, model), {"day": day, "model": model, "input": 0, "cached": 0, "output": 0,
                                                 "requests": 0, "billed": 0.0, "has_billed": "billed" in columns})
        entry["input"] += int(get("input") or (get("miss") + cached))
        entry["cached"] += int(cached)
        entry["output"] += int(get("output"))
        entry["requests"] += int(get("requests"))
        entry["billed"] += get("billed")
    result = []
    for (day, model), item in sorted(merged.items()):
        at = datetime(day.year, day.month, day.day, 12, tzinfo=BEIJING).timestamp()
        result.append({"at": at, "task_id": None, "step": None, "provider": "deepseek-export", "model": model, "kind": "chat",
                       "input": item["input"], "cached": item["cached"], "output": item["output"],
                       "total": item["input"] + item["output"], "images": 0, "backfilled": True,
                       "source": "deepseek_export", "requests": item["requests"] or None,
                       "billed": round(item["billed"], 6) if item["has_billed"] else None})
    if not result:
        raise ValueError("没有可导入的行")
    return result


def import_deepseek(text: str) -> dict:
    """导入账单：同一天已导入过的先替换（重复导入不重复计）。"""
    entries = [{k: v for k, v in e.items() if v is not None} for e in parse_deepseek_export(text)]
    days = {_beijing_day(e["at"]) for e in entries}
    dropped = rewrite(lambda e: not (e.get("source") == "deepseek_export" and _beijing_day(e["at"]) in days), entries)
    return {"rows": len(entries), "days": sorted(days), "replaced": dropped}


def _beijing_day(at: float) -> str:
    return datetime.fromtimestamp(at, BEIJING).strftime("%Y-%m-%d")


# ---- 已接入的全部模型（含未启用） ----

ROLE_STEPS = {
    "agent": ["intake", "compose", "style", "frame", "retouch"],
    "cheap": ["reveal"],
    "vision": ["intake", "check"],
}


def catalog() -> list[dict]:
    """代码里接入的全部模型及是否在用（只读非密钥配置；不返回任何 key）。"""
    from app.common.llm import llm_config

    rows = []
    for kind, steps in ROLE_STEPS.items():
        config = llm_config(kind)
        chat = config["provider"] == "chat"
        rows.append({"provider": "chat" if chat else "ark", "model": config["model"] or "未配置", "kind": kind,
                     "steps": steps, "active": bool(config["api_key"] and config["model"]),
                     "note": "对话模型（CHAT_*）" if chat else "方舟对话（LLM_MODEL_*）"})
        if chat:  # 方舟对话只在没配 CHAT_API_KEY 时才用
            ark = getattr(settings, f"llm_model_{kind}")
            rows.append({"provider": "ark", "model": ark or "未配置", "kind": kind, "steps": steps, "active": False,
                         "note": "方舟对话备用：仅在未配置 CHAT_API_KEY 时启用"})
    rows.append({"provider": "seedream", "model": settings.seedream_model or "未配置", "kind": "image",
                 "steps": ["generate"], "active": bool(settings.llm_api_key and settings.seedream_model),
                 "note": "生图主路（方舟 /images/generations）"})
    from app.modules.generation.client import _runninghub_ready

    rows.append({"provider": "runninghub", "model": settings.runninghub_workflow_id or "未配置", "kind": "image",
                 "steps": ["generate"], "active": _runninghub_ready(), "note": "生图备用：Seedream 失败且可重试时切换"})
    for row in rows:
        price = price_for(row["provider"], row["model"])
        row["step_labels"] = [step_label(s) for s in row["steps"]]
        row["price"] = price
    return rows


# ---- 对话模型回调 ----


def _message(message) -> dict:
    item = {"role": getattr(message, "type", "?"), "content": getattr(message, "content", "")}
    calls = getattr(message, "tool_calls", None)
    if calls:
        item["tool_calls"] = [{"name": c.get("name"), "args": c.get("args")} for c in calls]
    return item


class UsageCallback(BaseCallbackHandler):
    """挂在对话模型上：每次调用结束记一条真实用量，并把完整输入输出写进任务过程记录。"""

    def __init__(self, provider: str, model: str, kind: str) -> None:
        self.provider, self.model, self.kind = provider, model, kind
        self._inputs: dict = {}

    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs) -> None:
        self._inputs[run_id] = [_message(m) for batch in messages for m in batch]

    def on_llm_error(self, error, *, run_id=None, **kwargs) -> None:
        trace.add("llm", {"provider": self.provider, "model": self.model, "role": self.kind,
                          "input": self._inputs.pop(run_id, None), "error": type(error).__name__})

    def on_llm_end(self, response, *, run_id=None, **kwargs) -> None:
        raw = (response.llm_output or {}).get("token_usage") or {}
        model = (response.llm_output or {}).get("model_name") or self.model
        outputs, used = [], None
        for generations in response.generations or []:
            for generation in generations:
                message = getattr(generation, "message", None)
                if message is not None:
                    outputs.append(_message(message))
                meta = getattr(message, "usage_metadata", None)
                if meta and used is None:
                    raw = raw or (getattr(message, "response_metadata", {}) or {}).get("token_usage") or {}
                    used = (meta.get("input_tokens", 0), meta.get("output_tokens", 0), meta.get("total_tokens"),
                            (meta.get("input_token_details") or {}).get("cache_read"))
        if used is None and raw:
            used = (raw.get("prompt_tokens", 0), raw.get("completion_tokens", 0), raw.get("total_tokens"), None)
        if used is not None:
            cached = used[3] if used[3] is not None else (
                raw.get("prompt_cache_hit_tokens") or (raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
            record(self.provider, model, self.kind, used[0], used[1], used[2], cached_tokens=cached)
        trace.add("llm", {"provider": self.provider, "model": model, "role": self.kind,
                          "input": self._inputs.pop(run_id, None), "output": outputs,
                          "usage": {"input": used[0], "output": used[1], "cached": cached} if used else None})
