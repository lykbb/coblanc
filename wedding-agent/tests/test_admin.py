"""内部站点：后台 = IP 白名单 + 账号密码登录；图墙只认 IP；CSRF、审计、邀请码管理、任务只读、会话超时。"""
import time

from fastapi.testclient import TestClient

from app import access
from app.api import app
from app.common.config import settings
from app.portal import read_audit
from conftest import TEST_PASSWORD, portal_login


def test_gallery_member_cannot_use_admin_without_login(gallery_client):
    assert gallery_client.get("/api/gallery/refs").status_code == 200
    for path in ("/api/admin/access", "/api/admin/tasks", "/api/admin/audit"):
        assert gallery_client.get(path).status_code == 401  # IP 在白名单，但没有后台登录会话


def test_admin_login_wrong_password(portal_env):
    client = portal_login("gallery", "lyk")
    r = client.post("/auth/admin/login", data={"username": "lyk", "password": "nope"}, follow_redirects=False)
    assert r.status_code == 401 and "账号或密码不对" in r.text and "set-cookie" not in r.headers
    assert read_audit(1)[0] | {"site": "admin", "action": "login_failed"} == read_audit(1)[0]
    assert client.get("/api/admin/tasks").status_code == 401


def test_removed_from_allowlist_is_forbidden(admin_client, monkeypatch):
    assert admin_client.get("/api/admin/access").status_code == 200
    monkeypatch.setattr(settings, "admin_holders", ["someone_else"])
    monkeypatch.setattr(settings, "gallery_members", [])
    access._ip_cache.clear()
    assert admin_client.get("/api/admin/access").status_code == 403
    assert admin_client.get("/api/admin/status").json()["authorized"] is False
    assert read_audit(5)[0]["action"] == "forbidden"


def test_site_cookie_cannot_use_admin(admin_client):
    site = TestClient(app, headers={"X-Portal-CSRF": "1", "X-Real-IP": admin_client.headers["x-real-ip"]})
    [(_, code)] = access.create(["lyk"])
    site.post("/api/access/redeem", json={"code": code})
    assert site.get("/api/admin/tasks").status_code == 401


def test_csrf_required(admin_client, gallery_client):
    for client, path, body in ((admin_client, "/api/admin/access/codes", {"holders": ["x"]}),
                               (gallery_client, "/api/gallery/refs/x", None)):
        ip = {"X-Real-IP": client.headers["x-real-ip"]}
        bare = TestClient(app, cookies=dict(client.cookies), headers=ip)
        r = bare.post(path, json=body) if body else bare.delete(path)
        assert r.status_code == 403 and r.json()["error"]["code"] == "PORTAL_CSRF"
        evil = TestClient(app, cookies=dict(client.cookies), headers={**ip, "X-Portal-CSRF": "1", "Origin": "http://evil.example"})
        assert (evil.post(path, json=body) if body else evil.delete(path)).status_code == 403
        assert read_audit(1)[0]["action"] == "csrf_rejected"


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
    r = admin_client.post("/auth/admin/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
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
    from app.common import trace, usage
    trace.add("image", {"prompt": "完整提示词", "api_key": "x"}, task_id=task_id)
    usage.record("seedream", "doubao-seedream-5-0-flash-260915", "image", images=1, task_id=task_id, step="generate")
    detail = admin_client.get(f"/api/admin/tasks/{task_id}").json()
    assert detail["trace"][-1]["prompt"] == "完整提示词" and detail["trace"][-1]["api_key"] == "***"
    assert detail["usage"]["total"]["cost"] >= 0.12 and {"chat", "fields", "pending_questions"} <= set(detail)
    listing = admin_client.get("/api/admin/outputs").json()["items"]
    assert listing[0]["task_id"] == task_id and listing[0]["counts"]["uploads"] == len(detail["images"]["photos"])
    out = admin_client.get(f"/api/admin/outputs/{task_id}").json()
    assert out["uploads"] == detail["images"]["photos"] and {"candidates", "deliverables", "prompts", "review"} <= set(out)
    assert admin_client.get("/api/admin/tasks/t_missing").status_code == 404


def test_portal_responses_noindex(admin_client):
    for path in ("/api/admin/status", "/api/gallery/status"):
        r = admin_client.get(path)
        assert r.headers["x-robots-tag"].startswith("noindex") and r.headers["cache-control"] == "no-store"


def test_path_mode_login_cookie_scoped_and_referer_checked(portal_env):
    """path 模式：nginx 传 X-Forwarded-Prefix；Cookie Path 限定前缀；改动请求的 Referer 必须来自本站前缀。"""
    host = "43.142.59.166"
    ip = portal_login("gallery", "lyk").headers["x-real-ip"]
    base = {"Host": host, "X-Forwarded-Prefix": "/abordadmin/", "X-Portal-CSRF": "1", "Origin": f"http://{host}", "X-Real-IP": ip}
    client = TestClient(app, headers=base)
    r = client.post("/auth/admin/login", data={"username": "lyk", "password": TEST_PASSWORD, "next": "//evil.example/"}, follow_redirects=False)
    cookie = r.headers["set-cookie"]
    assert r.status_code == 303 and r.headers["location"] == "/abordadmin/"
    assert "Path=/abordadmin;" in cookie and "SameSite=strict" in cookie and "HttpOnly" in cookie
    body = {"holders": ["x"]}
    client = TestClient(app, headers=base, cookies={"xx_admin": r.cookies.get("xx_admin") or client.cookies.get("xx_admin")})  # 模拟浏览器在 /abordadmin 下带 Cookie
    assert client.post("/api/admin/access/codes", json=body, headers={"Referer": f"http://{host}/"}).status_code == 403
    assert client.post("/api/admin/access/codes", json=body, headers={"Referer": f"http://{host}/gallery/"}).status_code == 403
    assert client.post("/api/admin/access/codes", json=body, headers={"Referer": f"http://{host}/abordadmin/"}).status_code == 200


def test_task_operator_recorded(admin_client):
    from conftest import make_png

    site = TestClient(app)
    [(_, code)] = access.create(["何选"])
    site.post("/api/access/redeem", json={"code": code})
    ids = [site.post("/api/uploads", files={"file": ("a.png", make_png(8 + i), "image/png")}).json()["file_id"] for i in range(2)]
    task_id = site.post("/api/tasks", json={"photo_file_ids": ids}).json()["task_id"]
    item = next(i for i in admin_client.get("/api/admin/tasks").json()["items"] if i["task_id"] == task_id)
    assert item["operator"] == "何选" and item["operator_source"] is None


def test_real_ip_trusted_only_from_local_proxy_and_audit_user(admin_client):
    from fastapi.testclient import TestClient
    from app.api import app
    from app.portal import read_audit
    spoof = TestClient(app, client=("203.0.113.9", 1234))
    spoof.post("/auth/admin/login", data={"username": "nobody", "password": "x"}, headers={"X-Real-IP": "10.9.9.9"})
    local = TestClient(app, client=("127.0.0.1", 1234))
    local.post("/auth/admin/login", data={"username": "nobody", "password": "x"}, headers={"X-Real-IP": "198.51.100.7"})
    ips = [e["ip"] for e in read_audit(10) if e["action"] in ("login_failed", "login_locked")][:2]
    assert ips == ["198.51.100.7", "203.0.113.9"]
    ip = admin_client.headers["x-real-ip"]
    entry = next(e for e in read_audit(50) if e["ip"] == ip)
    assert entry["user"] and entry["user_source"] in ("device", "ip")
