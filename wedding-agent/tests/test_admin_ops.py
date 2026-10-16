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
from app.common.log import current_step, current_task
from app.portal import read_audit
from conftest import make_png


def test_usage_empty_then_recorded(admin_client):
    r = admin_client.get("/api/admin/usage?period=today").json()
    assert r["total"]["calls"] == 0 and r["prices"]["currency"] == "CNY"
    assert {m["kind"] for m in r["models"]} == {"agent", "cheap", "vision", "image"}  # 已接入的模型都列出，用量 0
    assert all(m["calls"] == 0 for m in r["models"])
    task, step = current_task.set("t_abc"), current_step.set("style")
    try:
        msg = AIMessage("ok", usage_metadata={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200,
                                              "input_token_details": {"cache_read": 400}})
        usage.UsageCallback("chat", "deepseek-flash", "agent").on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]))
        current_step.set("generate")
        usage.record("seedream", "doubao-seedream-5-0-flash-260915", "image", images=2)
        usage.record("runninghub", "wf1", "image", images=1)
    finally:
        current_task.reset(task)
        current_step.reset(step)
    r = admin_client.get("/api/admin/usage?period=7d").json()
    chat = next(m for m in r["models"] if m["model"] == "deepseek-flash" and m["calls"])
    assert chat["input"] == 1000 and chat["cached"] == 400 and chat["output"] == 200
    entry = usage.read(task_id="t_abc")[0]
    tier = usage.price_for("chat", "deepseek-flash")["tiers"]["peak" if usage.is_peak(entry["at"]) else "offpeak"]
    assert chat["cost"] == pytest.approx((600 * tier["input"] + 400 * tier["cache_hit"] + 200 * tier["output"]) / 1e6)
    steps = {s["step"]: s for s in r["steps"]}
    assert steps["style"]["label"] == "妆造师" and steps["generate"]["cost"] == pytest.approx(0.24)
    assert steps["generate"]["unpriced"] == 1  # RunningHub 没有可核实的官方单价，不估
    assert r["tasks"][0]["task_id"] == "t_abc" and r["total"]["images"] == 3
    assert admin_client.get("/api/admin/usage?period=1y").status_code == 400


def test_prices_file_and_peak():
    table = usage.price_table()
    assert table["currency"] == "CNY" and table["version"]
    for item in table["models"]:
        assert item["source"].startswith("https://") and item["checked"] and "verified" in item
    # 北京时间 周三 10:00 高峰；周三 13:00、周六 10:00 空闲
    from datetime import datetime
    at = lambda *a: datetime(*a, tzinfo=usage.BEIJING).timestamp()
    assert usage.is_peak(at(2026, 10, 14, 10)) and not usage.is_peak(at(2026, 10, 14, 13)) and not usage.is_peak(at(2026, 10, 17, 10))
    assert usage.cost({"provider": "chat", "model": "deepseek-flash", "at": at(2026, 10, 17, 10), "input": 1_000_000, "cached": 0, "output": 0}) == pytest.approx(1.0)


def test_trace_masks_secrets(admin_client):
    from app.common import trace
    trace.add("image", {"api_key": "sk-abcdefghijklmnop", "prompt": "hi Bearer abc", "image": "data:image/png;base64," + "A" * 4000}, task_id="t_m")
    item = trace.read("t_m")[0]
    assert item["api_key"] == "***" and "abc" not in item["prompt"] and item["image"].startswith("[image/png")


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


def test_usage_backfilled_and_daily_models(admin_client):
    usage.record("seedream", "seedream-x", "image", images=3, task_id="t_old", backfilled=True)
    usage.record("chat", "deepseek-chat", "agent", 10, 5)
    r = admin_client.get("/api/admin/usage?period=7d").json()
    assert r["total"]["backfilled"] == 1 and r["total"]["images"] == 3
    assert {(d["model"], d["total"], d["images"]) for d in r["daily_models"]} == {("seedream-x", 0, 3), ("deepseek-chat", 15, 0)}


def test_deepseek_import_replaces_day_and_supersedes_live(admin_client):
    from datetime import datetime
    day = datetime.fromtimestamp(__import__("time").time(), usage.BEIJING).strftime("%Y-%m-%d")
    usage.record("chat", "deepseek-flash", "agent", 100, 10, task_id="t_live", step="style")
    csv = f"日期,模型,请求次数,输入(缓存命中) tokens,输入(缓存未命中) tokens,输出 tokens,金额(元)\n{day},deepseek-v4.1-flash,3,400,600,200,0.0021\n"
    r = admin_client.post("/api/admin/usage/import", files={"file": ("u.csv", csv.encode(), "text/csv")}, headers={"X-Portal-CSRF": "1"})
    assert r.status_code == 200 and r.json()["rows"] == 1
    admin_client.post("/api/admin/usage/import", files={"file": ("u.csv", csv.encode(), "text/csv")}, headers={"X-Portal-CSRF": "1"})
    data = admin_client.get("/api/admin/usage?period=7d").json()  # 账单按北京时间正午记，测试机时区不同
    assert data["total"]["input"] == 1000 and data["total"]["cached"] == 400 and data["total"]["calls"] == 3  # 重复导入不重复计
    assert data["total"]["cost"] == pytest.approx(0.0021) and data["total"]["superseded"] == 1
    assert {s["step"] for s in data["steps"]} == {"style"} and day in data["imports"]  # 明细仍是自己记的
    bad = admin_client.post("/api/admin/usage/import", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}, headers={"X-Portal-CSRF": "1"})
    assert bad.status_code == 400


def test_backfill_attempt_line_parses():
    from app.scripts.backfill_history import ATTEMPT
    line = ('2026-10-16T10:18:30+08:00 VM uvicorn[1]: 2026-10-16 10:18:30,774 INFO [t_0f88a601] wedding.generation: generation_attempt '
            '{"engine": "seedream", "status": "succeeded", "response": {"usage": {"generated_images": 1, "output_tokens": 16428}, "request_id": "r1"}}')
    m = ATTEMPT.match(line)
    assert m and m.group(2) == "t_0f88a601" and json.loads(m.group(3))["response"]["usage"]["output_tokens"] == 16428
