"""账号密码登录页（前台、后台）和 nginx 把关接口 /internal/gate/*。"""
from fastapi.testclient import TestClient

from app import access
from app.api import app
from app.login import _apr1, check_password
from conftest import TEST_PASSWORD, portal_login


def gate(name, ip="1.1.1.1", cookies=None):
    return TestClient(app, cookies=cookies or {}).get(f"/internal/gate/{name}", headers={"X-Original-IP": ip}).status_code


def test_apr1_matches_htpasswd():
    assert _apr1(b"t\xc3\xa9st pw", b"abcdefgh") == "$apr1$abcdefgh$1H8uHGVuj7ytuSoWzgn9T0"  # openssl passwd -apr1


def test_front_login_flow(portal_env):
    client = TestClient(app)
    page = client.get("/auth/front/login")
    assert page.status_code == 200 and 'name="password"' in page.text and "www-authenticate" not in page.headers
    assert gate("front") == 401
    assert client.post("/auth/front/login", data={"username": "xiaoxi", "password": "x"}).status_code == 401
    r = client.post("/auth/front/login", data={"username": "xiaoxi", "password": TEST_PASSWORD, "next": "/coblanc-film/"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/coblanc-film/" and "Path=/;" in r.headers["set-cookie"]
    assert gate("front", cookies=dict(client.cookies)) == 204
    assert client.post("/auth/front/logout", follow_redirects=False).status_code == 303
    assert gate("front", cookies={"xx_login": r.cookies.get("xx_login") or ""}) == 401


def test_cross_site_login_rejected(portal_env):
    r = TestClient(app).post("/auth/front/login", data={"username": "xiaoxi", "password": TEST_PASSWORD},
                             headers={"Origin": "http://evil.example"}, follow_redirects=False)
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_login_lockout_after_many_fails(portal_env):
    client = TestClient(app)
    for _ in range(access.MAX_FAILS):
        assert client.post("/auth/front/login", data={"username": "xiaoxi", "password": "bad"}).status_code == 401
    assert client.post("/auth/front/login", data={"username": "xiaoxi", "password": TEST_PASSWORD}).status_code == 429


def test_gates(portal_env):
    ip = portal_login("gallery", "何选").headers["x-real-ip"]
    assert gate("team", ip) == 204 and gate("team", "9.9.9.9") == 403
    assert gate("admin", "9.9.9.9") == 403 and gate("admin", ip) == 401
    admin = portal_login("admin", "lyk")
    assert gate("admin", admin.headers["x-real-ip"], dict(admin.cookies)) == 204
    assert gate("front", cookies=dict(admin.cookies)) == 401  # 后台会话不当前台用
    assert gate("nope") == 404


def test_check_password_unknown_user_and_missing_file(portal_env, tmp_path):
    assert not check_password("admin", "nobody", TEST_PASSWORD)
    assert check_password("admin", "lyk", TEST_PASSWORD)


def test_api_docs_off_by_default():
    """线上不暴露接口说明页（API_DOCS 默认关）。"""
    client = TestClient(app)
    assert all(client.get(path).status_code == 404 for path in ("/docs", "/redoc", "/openapi.json"))
