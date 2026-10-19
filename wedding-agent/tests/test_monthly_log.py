"""按月归档：跨月第一次写入前归档旧文件、按窗口只读需要的月份、最新 N 条、改写覆盖归档；用量合计跨归档仍正确。"""
import json
import time

from app.common import usage
from app.common.config import settings
from app.common.monthly_log import MonthlyLog
from app.portal import AUDIT, read_audit


def _at(year, month, day=15):
    return time.mktime((year, month, day, 12, 0, 0, 0, 0, -1))


def _seed(log, *ats):
    log.path.parent.mkdir(parents=True, exist_ok=True)
    with log.path.open("a", encoding="utf-8") as f:
        for at in ats:
            f.write(json.dumps({"at": at, "v": at}) + "\n")


def test_rotates_on_new_month_and_keeps_everything(portal_env):
    log = MonthlyLog("demo")
    _seed(log, _at(2026, 9, 10), _at(2026, 9, 28))
    assert log.rotate(now=_at(2026, 9, 29)) is None  # 同月不动
    target = log.rotate(now=_at(2026, 10, 2))
    assert target == settings.state_dir / "archive" / "demo-2026-09.jsonl" and not log.path.exists()
    log.append([{"at": _at(2026, 10, 2)}])
    assert len(log.read()) == 3
    assert [i["at"] for i in log.read(_at(2026, 10, 1))] == [_at(2026, 10, 2)]
    assert log.files(_at(2026, 10, 1)) == [log.path]  # 窗口在本月：不打开归档


def test_same_month_archive_gets_suffix(portal_env):
    log = MonthlyLog("demo")
    _seed(log, _at(2026, 9))
    log.rotate(now=_at(2026, 10))
    _seed(log, _at(2026, 9, 20))  # 回填进来的旧月份记录
    log.rotate(now=_at(2026, 10))
    assert [p.name for _, p in log.archives()] == ["demo-2026-09.jsonl", "demo-2026-09.1.jsonl"]
    assert len(log.read(_at(2026, 9, 1))) == 2


def test_newest_reads_across_archives(portal_env):
    _seed(AUDIT, _at(2026, 8), _at(2026, 8, 20))
    AUDIT.rotate(now=_at(2026, 9))
    _seed(AUDIT, _at(2026, 9))
    AUDIT.rotate(now=_at(2026, 10))
    _seed(AUDIT, _at(2026, 10))
    assert [i["at"] for i in read_audit(2)] == [_at(2026, 10), _at(2026, 9)]
    assert len(read_audit(10)) == 4


def test_usage_rewrite_and_totals_span_archives(portal_env):
    usage.record("chat", "deepseek-flash", "agent", 10, 5, at=_at(2026, 9), source="deepseek_export")
    usage.record("chat", "deepseek-flash", "agent", 1, 1, at=_at(2026, 9, 20))
    usage.LOG.rotate(now=_at(2026, 10))
    usage.record("chat", "deepseek-flash", "agent", 2, 2)
    assert len(usage.read()) == 3 and len(usage.read(_at(2026, 9, 18))) == 2
    dropped = usage.rewrite(lambda e: e.get("source") != "deepseek_export", [])
    assert dropped == 1 and len(usage.read()) == 2
    assert any(p.name.startswith("usage-2026-09.jsonl.bak-") for p in (settings.state_dir / "archive").iterdir())


def test_audit_file_mode(portal_env):
    AUDIT.append([{"at": time.time()}])
    assert AUDIT.path.stat().st_mode & 0o777 == 0o600
