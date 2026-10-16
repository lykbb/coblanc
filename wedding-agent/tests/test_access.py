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
