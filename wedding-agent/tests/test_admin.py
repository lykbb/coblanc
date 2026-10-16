"""内部站点：后台只给管理员、图墙只给成员；凭证互不通用；CSRF、审计、邀请码管理、任务只读、会话超时。"""
import time

from fastapi.testclient import TestClient

from app import access
from app.api import app
from app.common.config import settings
from app.portal import read_audit
from conftest import portal_login


def test_gallery_member_cannot_use_admin(portal_env):
    member = portal_login("gallery", "刘静")
    assert member.get("/api/gallery/status").json() == {"authorized": True, "holder": "刘静"}
    assert member.get("/api/gallery/refs").status_code == 200
    for path in ("/api/admin/access", "/api/admin/tasks", "/api/admin/audit"):
        assert member.get(path).status_code == 401  # 图墙凭证在后台无效
    # 成员拿自己的码去后台登录：不在名单，拒绝且码不作废
    client = TestClient(app, headers={"X-Portal-CSRF": "1"})
    [(_, code)] = access.create(["刘静"])
    assert client.post("/api/admin/redeem", json={"code": code}).status_code == 403
    assert read_audit(1)[0] == read_audit(1)[0] | {"site": "admin", "action": "login_failed"}
    assert client.post("/api/gallery/redeem", json={"code": code}).status_code == 200


def test_admin_can_open_gallery_but_member_list_enforced(admin_client, monkeypatch):
    assert portal_login("gallery", "lyk").get("/api/gallery/refs").status_code == 200
    member = portal_login("gallery", "何选")
    monkeypatch.setattr(settings, "gallery_members", [])
    r = member.get("/api/gallery/refs")
    assert r.status_code == 403 and read_audit(1)[0]["action"] == "forbidden"


def test_admin_generates_gallery_login_code(admin_client):
    code = admin_client.post("/api/admin/access/codes", json={"holders": ["何选"]}).json()["codes"][0]["code"]
    member = TestClient(app, headers={"X-Portal-CSRF": "1"})
    assert member.post("/api/gallery/redeem", json={"code": code}).status_code == 200
    assert member.post("/api/gallery/logout").status_code == 200
    assert member.get("/api/gallery/refs").status_code == 401


def test_removed_from_allowlist_is_forbidden(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_holders", ["someone_else"])
    assert admin_client.get("/api/admin/access").status_code == 403
    assert admin_client.get("/api/admin/status").json()["authorized"] is False
    assert read_audit(5)[0]["action"] == "forbidden"


def test_site_cookie_cannot_use_admin(admin_client):
    site = TestClient(app, headers={"X-Portal-CSRF": "1"})
    [(_, code)] = access.create(["lyk"])
    site.post("/api/access/redeem", json={"code": code})
    assert site.get("/api/admin/tasks").status_code == 401


def test_csrf_required(admin_client, gallery_client):
    for client, path, body in ((admin_client, "/api/admin/access/codes", {"holders": ["x"]}),
                               (gallery_client, "/api/gallery/logout", None)):
        bare = TestClient(app, cookies=dict(client.cookies))
        r = bare.post(path, json=body)
        assert r.status_code == 403 and r.json()["error"]["code"] == "PORTAL_CSRF"
        evil = TestClient(app, cookies=dict(client.cookies), headers={"X-Portal-CSRF": "1", "Origin": "http://evil.example"})
        assert evil.post(path, json=body).status_code == 403
        assert read_audit(1)[0]["action"] == "csrf_rejected"
    assert TestClient(app, cookies=dict(admin_client.cookies)).get("/api/admin/access").status_code == 200


def test_codes_revoke_and_audit(admin_client):
    r = admin_client.post("/api/admin/access/codes", json={"holders": ["小王"], "count": 3, "prefix": "公测"})
    codes = r.json()["codes"]
    assert [c["holder"] for c in codes] == ["小王", "公测-1", "公测-2", "公测-3"]
    TestClient(app).post("/api/access/redeem", json={"code": codes[0]["code"]})
    overview = admin_client.get("/api/admin/access").json()
    device = next(d for d in overview["devices"] if d["holder"] == "小王")
    assert "hash" not in str(overview) and overview["admins"] == ["lyk"] and overview["members"] == ["刘静", "何选"]
    assert admin_client.delete(f"/api/admin/access/devices/{device['id']}").json()["revoked"] is True
    assert admin_client.post("/api/admin/access/revoke", json={"holder": "公测-1"}).json()["revoked"] == 1
    actions = [e["action"] for e in admin_client.get("/api/admin/audit").json()["items"]]
    assert actions[:4] == ["holder_revoked", "device_revoked", "codes_created", "login"]
    assert read_audit(1)[0]["holder"] == "lyk"


def test_gallery_actions_visible_in_admin_audit(admin_client, gallery_client):
    gallery_client.get("/api/gallery/refs/export")
    entry = admin_client.get("/api/admin/audit").json()["items"][0]
    assert entry["site"] == "gallery" and entry["holder"] == "刘静" and entry["action"] == "refs_exported"


def test_idle_session_expires(admin_client, monkeypatch):
    assert admin_client.get("/api/admin/status").json()["authorized"] is True
    monkeypatch.setattr(time, "time", lambda real=time.time: real() + settings.admin_session_hours * 3600 + 120)
    assert admin_client.get("/api/admin/access").status_code == 401


def test_logout(admin_client):
    assert admin_client.post("/api/admin/logout").status_code == 200
    assert admin_client.get("/api/admin/access").status_code == 401


def test_tasks_readonly(admin_client):
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


def test_portal_responses_noindex(admin_client):
    for path in ("/api/admin/status", "/api/gallery/status"):
        r = admin_client.get(path)
        assert r.headers["x-robots-tag"].startswith("noindex") and r.headers["cache-control"] == "no-store"
