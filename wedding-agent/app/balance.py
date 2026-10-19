"""DeepSeek 账户余额跟踪：官方 GET {CHAT_BASE_URL}/user/balance（https://api-docs.deepseek.com/zh-cn/api/get-user-balance），
用已配置的对话模型 Key（进程内读配置，不落盘、不打印）。

- 轮询：后台概览 / Token 用量页开着（2 分钟内看过）或最近 10 分钟有模型调用 → 每 60 秒；否则每 15 分钟。
- 快照写 state/balance.jsonl（按月归档到 state/archive/；时间、可用、币种、总额 / 赠金 / 充值）；余额没变时最多 15 分钟写一条。出错只记日志和最近错误。
- 今日实际花费 = 今天余额每次下降之和（上涨视为充值，不计）；与我们按单价算的 DeepSeek 费用对照。
火山方舟（Seedream）余额不在这里：方舟没有可用 API Key 直接查的余额接口（要走火山引擎账号 AK/SK 的计费 OpenAPI）。
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from app.common import usage
from app.common.config import settings
from app.common.log import get_logger
from app.common.monthly_log import MonthlyLog

log = get_logger("balance")
FAST, SLOW, VIEW_WINDOW, ACTIVE_WINDOW, KEEP_EVERY = 60, 15 * 60, 120, 600, 15 * 60
_state = {"viewed": 0.0, "last_poll": 0.0, "error": "", "last": None}
_lock = threading.Lock()


LOG = MonthlyLog("balance")  # 当月 state_dir/balance.jsonl，往月归档到 state_dir/archive/


def enabled() -> bool:
    return bool(settings.chat_api_key) and not settings.fake and urlsplit(settings.chat_base_url).hostname == "api.deepseek.com"


def fetch() -> dict:
    request = urllib.request.Request(settings.chat_base_url.rstrip("/") + "/user/balance",
                                     headers={"Authorization": f"Bearer {settings.chat_api_key}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read())
    infos = data.get("balance_infos") or [{}]
    info = next((i for i in infos if i.get("currency") == "CNY"), infos[0])
    return {"at": time.time(), "available": bool(data.get("is_available")), "currency": info.get("currency", ""),
            "total": float(info.get("total_balance") or 0), "granted": float(info.get("granted_balance") or 0),
            "topped_up": float(info.get("topped_up_balance") or 0)}


def read(since: float = 0) -> list[dict]:
    return LOG.read(since)


def poll() -> dict | None:
    try:
        snap = fetch()
    except Exception as e:  # 网络、鉴权、格式问题都安静处理
        _state["error"] = type(e).__name__ + (f" {e.code}" if hasattr(e, "code") else "")
        log.warning("查询 DeepSeek 余额失败：%s", _state["error"])
        return None
    with _lock:
        last = _state["last"] or (read(time.time() - 86400)[-1:] or [None])[0]
        if not last or last["total"] != snap["total"] or snap["at"] - last["at"] >= KEEP_EVERY:
            LOG.append([snap])
            _state["last"] = snap
        _state["error"] = ""
        _state["current"] = snap
    return snap


def interval() -> int:
    now = time.time()
    try:
        recent_call = now - usage.LOG.path.stat().st_mtime < ACTIVE_WINDOW
    except OSError:
        recent_call = False
    return FAST if now - _state["viewed"] < VIEW_WINDOW or recent_call else SLOW


def run(stop: threading.Event) -> None:
    """后台线程：每 5 秒看一眼是否到点，到点才真正请求。"""
    while not stop.wait(5):
        if time.time() - _state["last_poll"] >= interval():
            _state["last_poll"] = time.time()
            poll()


def viewed() -> None:
    """后台页面看了一眼：切到快档；离上次查询超过 60 秒就顺手查一次（线程里会做，这里只标记）。"""
    _state["viewed"] = time.time()


def _start_of_today() -> float:
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def spent(snaps: list[dict]) -> float:
    """余额下降之和；上涨（充值、赠金）不计。"""
    return sum(max(0.0, a["total"] - b["total"]) for a, b in zip(snaps, snaps[1:]))


def summary(our_cost_today: float) -> dict:
    today = _start_of_today()
    history = read(today - 86400)
    current = _state.get("current") or (history[-1] if history else None)
    if current and (not history or history[-1]["at"] < current["at"]):
        history.append(current)
    before = [s for s in history if s["at"] < today][-1:]  # 零点前最后一条作基线
    spent_today = round(spent(before + [s for s in history if s["at"] >= today]), 4)
    diff = round(spent_today - our_cost_today, 4)
    base = max(spent_today, our_cost_today)
    step = max(1, len(history) // 48)
    return {
        "enabled": enabled(), "error": _state["error"], "current": current,
        "spent_today": spent_today, "our_cost_today": round(our_cost_today, 4), "diff": diff,
        "warn": bool(base) and abs(diff) > 0.5 and abs(diff) / base > 0.2,
        "spark": [[s["at"], s["total"]] for s in history[::step]] + ([[history[-1]["at"], history[-1]["total"]]] if history else []),
        "interval": interval(), "last_poll": _state["last_poll"],
    }
