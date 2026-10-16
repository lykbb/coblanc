"""邀请码：一次性兑换、设备凭证、拦截、作废、开关。"""
import pytest
from fastapi.testclient import TestClient

from app import access
from app.api import app
from app.common.config import settings


@pytest.fixture
def gated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", tmp_path)
    monkeypatch.setattr(settings, "access_required", True)
    access._fails.clear()
    return TestClient(app)


def test_blocked_without_code(gated):
    assert gated.get("/api/tasks/t_x").status_code == 401
    assert gated.get("/files/upload/a.png").status_code == 401
    assert gated.get("/api/access/status").json()["authorized"] is False


def test_code_is_single_use_and_binds_device(gated):
    [(_, code)] = access.create(["小王"])
    r = gated.post("/api/access/redeem", json={"code": code.lower().replace("-", " ")})
    assert r.status_code == 200 and r.json()["holder"] == "小王"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert gated.get("/api/access/status").json() == {"authorized": True, "holder": "小王"}
    assert gated.get("/api/tasks/t_x").status_code == 404  # 放行到业务层
    other = TestClient(app)
    assert other.post("/api/access/redeem", json={"code": code}).status_code == 403
    assert code.replace("-", "") not in (settings.state_dir / "access.json").read_text()


def test_revoke_kicks_device(gated):
    [(_, code)] = access.create(["小李"])
    gated.post("/api/access/redeem", json={"code": code})
    assert access.revoke("小李") == 1
    assert gated.get("/api/tasks/t_x").status_code == 401


def test_bruteforce_limited(gated):
    for _ in range(access.MAX_FAILS):
        assert gated.post("/api/access/redeem", json={"code": "WRONG"}).status_code == 403
    assert gated.post("/api/access/redeem", json={"code": "WRONG"}).status_code == 429


def test_switch_off_opens_site(gated, monkeypatch):
    monkeypatch.setattr(settings, "access_required", False)
    assert gated.get("/api/access/status").json()["authorized"] is True
    assert gated.get("/api/tasks/t_x").status_code == 404


def test_bulk_cli(gated, capsys):
    assert access.main(["bulk", "12", "公测"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 12 and lines[0].startswith("公测-01\t")


def test_portal_ip_allowlist_follows_site_devices(gated, monkeypatch):
    from app.common.config import settings as s

    check = lambda ip: gated.get("/internal/gate/team", headers={"X-Original-IP": ip}).status_code
    monkeypatch.setattr(s, "gallery_members", ["小赵"])
    monkeypatch.setattr(s, "admin_holders", ["lyk"])
    assert check("127.0.0.1") == 204 and check("1.2.3.4") == 403
    [(_, code)] = access.create(["小赵"])
    gated.post("/api/access/redeem", json={"code": code}, headers={"X-Real-IP": "1.2.3.4"})
    assert check("1.2.3.4") == 204
    gated.get("/api/tasks/t_x", headers={"X-Real-IP": "5.6.7.8"})  # 换了网络：记最近 IP
    assert check("5.6.7.8") == 204 and check("1.2.3.4") == 403
    access.revoke("小赵")
    assert check("5.6.7.8") == 403
    (s.state_dir / "portal-extra-ips.txt").write_text("9.9.9.9  # 手工补充\n")
    assert check("9.9.9.9") == 204


def test_public_holder_never_unlocks_portals(gated, monkeypatch):
    """公开邀请的新持有人：兑换前台码能用前台，但 IP 不进白名单，也登不了图墙/后台。"""
    from app.common.config import settings as s

    monkeypatch.setattr(s, "gallery_members", ["刘静"])
    monkeypatch.setattr(s, "admin_holders", ["lyk"])
    [(_, code)] = access.create(["公测-001"])
    assert gated.post("/api/access/redeem", json={"code": code}, headers={"X-Real-IP": "7.7.7.7"}).status_code == 200
    assert gated.get("/internal/gate/team", headers={"X-Original-IP": "7.7.7.7"}).status_code == 403
    outsider = TestClient(app, headers={"X-Portal-CSRF": "1", "X-Real-IP": "7.7.7.7"})
    assert outsider.get("/api/gallery/refs").status_code == 403 and outsider.get("/api/admin/tasks").status_code == 403
