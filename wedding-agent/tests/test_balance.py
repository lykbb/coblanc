"""DeepSeek 余额：今日花费只算下降（充值不计）、偏差告警阈值、快照去重写盘。"""
import time

from app import balance


def test_spent_ignores_top_ups():
    snaps = [{"total": v} for v in (10.0, 9.5, 9.2, 50.0, 49.0)]
    assert round(balance.spent(snaps), 4) == 1.8


def test_poll_writes_changes_only(portal_env, monkeypatch):
    values = iter([10.0, 10.0, 9.0])
    monkeypatch.setattr(balance, "fetch", lambda: {"at": time.time(), "available": True, "currency": "CNY",
                                                   "total": next(values), "granted": 0.0, "topped_up": 0.0})
    balance._state["last"] = None
    for _ in range(3):
        balance.poll()
    assert [s["total"] for s in balance.read()] == [10.0, 9.0]
    summary = balance.summary(0.2)
    assert summary["spent_today"] == 1.0 and summary["warn"] is True  # 差 0.8 > 0.5 且 > 20%
    assert balance.summary(0.9)["warn"] is False


def test_errors_are_quiet(portal_env, monkeypatch):
    def boom():
        raise OSError("down")
    monkeypatch.setattr(balance, "fetch", boom)
    assert balance.poll() is None and balance._state["error"] == "OSError"
    balance._state["error"] = ""
