"""后台：白名单、CSRF、审计、邀请码管理、任务只读、会话超时。"""
import time

from fastapi.testclient import TestClient

from app import access
from app.admin import read_audit
from app.api import app
from app.common.config import settings


def login(holder: str) -> TestClient:
    client = TestClient(app, headers={"X-Admin-CSRF": "1"})
    [(_, code)] = access.create([holder])
    client.post("/api/admin/redeem", json={"code": code})
    return client


def test_non_admin_code_rejected_and_not_consumed(admin_client):
    client = TestClient(app, headers={"X-Admin-CSRF": "1"})
    [(_, code)] = access.create(["小王"])
    assert client.post("/api/admin/redeem", json={"code": code}).status_code == 403
    assert client.get("/api/admin/access").status_code == 401
    assert TestClient(app).post("/api/access/redeem", json={"code": code}).status_code == 200  # 码没被后台作废


def test_removed_from_allowlist_is_forbidden(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_holders", ["someone_else"])
    assert admin_client.get("/api/admin/access").status_code == 403
    assert admin_client.get("/api/admin/status").json()["authorized"] is False
    assert read_audit(5)[0]["action"] == "forbidden"


def test_site_cookie_cannot_use_admin(admin_client):
    site = TestClient(app, headers={"X-Admin-CSRF": "1"})
    [(_, code)] = access.create(["lyk"])
    site.post("/api/access/redeem", json={"code": code})  # lyk 的用户站凭证
    assert site.get("/api/admin/tasks").status_code == 401


def test_csrf_required(admin_client):
    cookies = dict(admin_client.cookies)
    bare = TestClient(app, cookies=cookies)
    r = bare.post("/api/admin/access/codes", json={"holders": ["x"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ADMIN_CSRF"
    evil = TestClient(app, cookies=cookies, headers={"X-Admin-CSRF": "1", "Origin": "http://evil.example"})
    assert evil.post("/api/admin/access/codes", json={"holders": ["x"]}).status_code == 403
    assert bare.get("/api/admin/access").status_code == 200  # 只读不需要
    assert read_audit(5)[0]["action"] == "csrf_rejected"


def test_codes_revoke_and_audit(admin_client):
    r = admin_client.post("/api/admin/access/codes", json={"holders": ["小王"], "count": 3, "prefix": "公测"})
    codes = r.json()["codes"]
    assert [c["holder"] for c in codes] == ["小王", "公测-1", "公测-2", "公测-3"]
    TestClient(app).post("/api/access/redeem", json={"code": codes[0]["code"]})
    overview = admin_client.get("/api/admin/access").json()
    device = next(d for d in overview["devices"] if d["holder"] == "小王")
    assert "hash" not in str(overview) and overview["admins"] == ["lyk"]
    assert admin_client.delete(f"/api/admin/access/devices/{device['id']}").json()["revoked"] is True
    assert admin_client.post("/api/admin/access/revoke", json={"holder": "公测-1"}).json()["revoked"] == 1
    actions = [e["action"] for e in admin_client.get("/api/admin/audit").json()["items"]]
    assert actions[:4] == ["holder_revoked", "device_revoked", "codes_created", "login"]
    entry = read_audit(1)[0]
    assert entry["holder"] == "lyk" and entry["at"] > 0


def test_idle_session_expires(admin_client, monkeypatch):
    assert admin_client.get("/api/admin/status").json()["authorized"] is True
    monkeypatch.setattr(time, "time", lambda real=time.time: real() + settings.admin_session_hours * 3600 + 120)
    assert admin_client.get("/api/admin/access").status_code == 401


def test_logout(admin_client):
    assert admin_client.post("/api/admin/logout").status_code == 200
    assert admin_client.get("/api/admin/access").status_code == 401


def test_tasks_readonly(admin_client):
    from app import api
    from conftest import make_png

    site = TestClient(app)
    site.cookies.update(admin_client.cookies)  # 后台凭证也能看用户站文件
    ids = [site.post("/api/uploads", files={"file": ("a.png", make_png(8 + i), "image/png")}).json()["file_id"] for i in range(2)]
    task_id = site.post("/api/tasks", json={"photo_file_ids": ids}).json().get("task_id")
    items = admin_client.get("/api/admin/tasks").json()["items"]
    assert task_id and items[0]["task_id"] == task_id
    detail = admin_client.get(f"/api/admin/tasks/{task_id}").json()
    assert detail["images"]["photos"] and all(url.startswith("/files/") for url in detail["images"]["photos"])
    assert admin_client.get("/api/admin/tasks/t_missing").status_code == 404


def test_admin_responses_noindex(admin_client):
    r = admin_client.get("/api/admin/status")
    assert r.headers["x-robots-tag"].startswith("noindex") and r.headers["cache-control"] == "no-store"
