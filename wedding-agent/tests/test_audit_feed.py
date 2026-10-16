"""审计的浏览与安全记录：gate 记访问 / 拒绝（节流）、nginx / fail2ban 日志解析与增量同步、回填。"""
from fastapi.testclient import TestClient

from app import audit_feed, portal
from app.api import app

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0"


def gate(name, uri, ip="9.9.9.9", mode="navigate"):
    headers = {"X-Original-IP": ip, "X-Original-URI": uri, "X-Original-Host": "43.0.0.1", "User-Agent": UA}
    if mode:
        headers["Sec-Fetch-Mode"] = mode
    return TestClient(app).get(f"/internal/gate/{name}", headers=headers).status_code


def actions():
    return [(e["action"], e["site"], e["detail"].get("path")) for e in portal.read_audit(100)]


def test_denied_and_visits_are_throttled(portal_env):
    audit_feed._seen.clear()
    assert gate("team", "/gallery/") == 403
    assert gate("team", "/gallery/api/refs", mode="cors") == 403
    assert actions() == [("forbidden", "gallery", "/gallery/")]  # 同 IP 同站 10 分钟只记一次
    entry = portal.read_audit(1)[0]
    assert entry["ip"] == "9.9.9.9" and entry["ua"] == UA and entry["detail"]["reason"] == "ip"


def test_page_detection_and_site():
    assert audit_feed.is_page("/gallery/?style=06") and not audit_feed.is_page("/gallery/assets/a.js")
    assert not audit_feed.is_page("/api/tasks/t_1") and not audit_feed.is_page("/favicon.ico")
    assert not audit_feed.is_page("/", "cors") and audit_feed.is_page("/x", "navigate")
    assert audit_feed.site_of("/abordadmin/login", "", "team") == "admin"
    assert audit_feed.site_of("/", "gallery.example.com", "team") == "gallery"
    assert audit_feed.site_of("/coblanc-film/", "", "front") == "front"


def test_parse_logs():
    rec = audit_feed.parse_access('1.2.3.4 - - [16/Oct/2026:22:08:04 +0800] "GET /gallery/ HTTP/1.1" 403 153 "-" "curl/8"')
    assert rec["status"] == 403 and rec["ip"] == "1.2.3.4" and rec["ua"] == "curl/8"
    assert audit_feed.nginx_events(rec) == "forbidden"
    assert audit_feed.nginx_events({**rec, "status": 429}) == "rate_limited"
    assert audit_feed.nginx_events({**rec, "status": 200, "uri": "/gallery/assets/x.js"}) is None
    ban = audit_feed.parse_ban("2026-10-16 15:50:54,260 fail2ban.actions        [349772]: NOTICE  [nginx-http-auth] Ban 163.192.5.254")
    assert ban["action"] == "banned" and ban["jail"] == "nginx-http-auth" and ban["ip"] == "163.192.5.254"


def test_sync_reads_only_new_lines(portal_env, tmp_path, monkeypatch):
    log, f2b = tmp_path / "access.log", tmp_path / "fail2ban.log"
    old = '5.5.5.5 - - [16/Oct/2026:10:00:00 +0800] "POST /login HTTP/1.1" 429 10 "-" "curl/8"\n'
    log.write_text(old)
    f2b.write_text("")
    monkeypatch.setattr(audit_feed, "ACCESS_LOGS", [tmp_path / "none", log])
    monkeypatch.setattr(audit_feed, "FAIL2BAN_LOG", f2b)
    assert audit_feed.sync_logs() == 0  # 第一次只记位置
    with log.open("a") as f:
        f.write(old.replace("10:00:00", "10:05:00"))
    with f2b.open("a") as f:
        f.write("2026-10-16 15:50:54,260 fail2ban.actions        [1]: NOTICE  [nginx-http-auth] Ban 5.5.5.5\n")
    assert audit_feed.sync_logs() == 2
    assert audit_feed.sync_logs() == 0
    assert {e["action"] for e in portal.read_audit(10)} == {"rate_limited", "banned"}


def test_backfill_marks_and_dedupes(portal_env, tmp_path, monkeypatch):
    log = tmp_path / "access.log"
    lines = ['7.7.7.7 - - [16/Oct/2026:09:00:00 +0800] "GET /gallery/ HTTP/1.1" 403 1 "-" "curl/8"',
             '8.8.8.8 - - [16/Oct/2026:09:00:00 +0800] "GET / HTTP/1.1" 200 1 "-" "Safari"',
             '8.8.8.8 - - [16/Oct/2026:09:10:00 +0800] "GET /coblanc HTTP/1.1" 200 1 "-" "Safari"']
    log.write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(audit_feed, "ACCESS_LOGS", [log])
    monkeypatch.setattr(audit_feed, "FAIL2BAN_LOG", tmp_path / "none")
    first = audit_feed.backfill(0, 2e9)
    assert first["counts"] == {"forbidden": 1, "visit": 1}  # 30 分钟内同人同站只算一次访问
    assert all(e.get("backfilled") for e in portal.read_audit(10))
    assert audit_feed.backfill(0, 2e9)["written"] == 0
