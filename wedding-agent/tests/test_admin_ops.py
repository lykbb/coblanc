"""后台运维页：模型用量、服务器、项目文件（只读、限定项目根、敏感文件拒绝、记审计）。"""
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app import admin_ops
from app.api import app
from app.common import usage
from app.common.config import settings
from app.common.log import current_task
from app.portal import read_audit
from conftest import make_png


def test_usage_empty_then_recorded(admin_client):
    r = admin_client.get("/api/admin/usage?period=today").json()
    assert r["models"] == [] and r["total"]["calls"] == 0
    token = current_task.set("t_abc")
    try:
        msg = AIMessage("ok", usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})
        usage.UsageCallback("chat", "deepseek-chat", "agent").on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]))
        usage.record("seedream", "seedream-x", "image", images=1)
    finally:
        current_task.reset(token)
    r = admin_client.get("/api/admin/usage?period=7d").json()
    chat = next(m for m in r["models"] if m["model"] == "deepseek-chat")
    assert chat["input"] == 100 and chat["output"] == 20 and chat["cost"] is None
    assert r["tasks"][0]["task_id"] == "t_abc" and r["total"]["images"] == 1
    (settings.state_dir / "token_prices.json").write_text(json.dumps({"deepseek-chat": {"input_per_million": 2, "output_per_million": 8}}))
    chat = next(m for m in admin_client.get("/api/admin/usage?period=30d").json()["models"] if m["model"] == "deepseek-chat")
    assert chat["cost"] == pytest.approx((100 * 2 + 20 * 8) / 1e6)
    assert admin_client.get("/api/admin/usage?period=1y").status_code == 400


def test_server_info(admin_client):
    r = admin_client.get("/api/admin/server").json()
    assert r["cpu"]["cores"] and r["disk"]["total"] > 0 and set(r["services"]) == {"wedding-backend", "nginx", "fail2ban"}
    assert r["references"]["cap"] == int(settings.reference_cap_gb * 1024**3)


@pytest.fixture
def project(tmp_path, monkeypatch, admin_client):
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "a.py").write_text("print('hi')\n")
    (root / "app" / "p.png").write_bytes(make_png())
    (root / ".env").write_text("X=1")
    (root / ".env.local").write_text("X=1")
    (root / "k.pem").write_text("x")
    (root / "state").mkdir()
    (root / "state" / "access.json").write_text("{}")
    (root / "outside.txt").symlink_to(tmp_path / "secret.txt")
    (tmp_path / "secret.txt").write_text("no")
    monkeypatch.setattr(admin_ops, "PROJECT_ROOT", root)
    return admin_client


def test_files_list_hides_blocked(project):
    names = [i["name"] for i in project.get("/api/admin/files/list").json()["items"]]
    assert names == ["app", "state"]
    assert [i["name"] for i in project.get("/api/admin/files/list?path=state").json()["items"]] == []


def test_files_view_and_audit(project):
    r = project.get("/api/admin/files/view?path=app/a.py").json()
    assert r["kind"] == "text" and "print" in r["text"]
    assert read_audit(1)[0]["action"] == "file_viewed"
    assert project.get("/api/admin/files/view?path=app/p.png").json()["kind"] == "image"
    img = project.get("/api/admin/files/raw?path=app/p.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    dl = project.get("/api/admin/files/raw?path=app/a.py&download=1")
    assert "attachment" in dl.headers["content-disposition"] and read_audit(1)[0]["action"] == "file_downloaded"


@pytest.mark.parametrize("path", [".env", ".env.local", "k.pem", "state/access.json", "../secret.txt", "app/../../secret.txt",
                                  "outside.txt", "/etc/passwd", "app/%2e%2e/%2e%2e/secret.txt"])
def test_files_blocked(project, path):
    for endpoint in ("view", "raw"):
        r = project.get(f"/api/admin/files/{endpoint}", params={"path": path})
        assert r.status_code in (403, 404), (path, r.status_code)
        assert "X=1" not in r.text and "no" != r.text


def test_ops_need_admin_session(portal_env):
    from conftest import portal_login
    member = portal_login("gallery", "刘静")
    for path in ("/api/admin/usage", "/api/admin/server", "/api/admin/files/list", "/api/admin/files/view?path=app/a.py"):
        assert member.get(path).status_code == 401
        assert TestClient(app, headers={"X-Real-IP": "8.8.8.8"}).get(path).status_code == 403
