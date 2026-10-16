"""服务重启后任务还在：任务进度 JSON + 流程检查点 SQLite 都落盘。"""
import os
import time

from app.common.progress import TaskStore, store
from app.common.config import settings


def test_task_survives_restart(tmp_path):
    before = TaskStore(tmp_path, ttl_days=7)
    before.create("t_keep")
    before.update("t_keep", status="reviewing", step="review", user_redo_count=1)
    after = TaskStore(tmp_path, ttl_days=7)  # 模拟重启：新的内存
    info = after.get("t_keep")
    assert info and info.status == "reviewing" and info.user_redo_count == 1
    assert after.transition("t_keep", "reviewing", "running")


def test_running_task_becomes_retryable_after_restart(tmp_path):
    TaskStore(tmp_path, ttl_days=7).create("t_run")
    TaskStore(tmp_path, ttl_days=7).update("t_run", status="running", step="framing")
    info = TaskStore(tmp_path, ttl_days=7).get("t_run")
    assert info.status == "failed" and info.error["retryable"] and info.error["category"] == "system"


def test_expired_task_is_dropped(tmp_path):
    s = TaskStore(tmp_path, ttl_days=7)
    s.create("t_old")
    old = time.time() - 8 * 86400
    os.utime(tmp_path / "t_old.json", (old, old))
    assert TaskStore(tmp_path, ttl_days=7).get("t_old") is None
    assert s.purge_expired() == ["t_old"] and not (tmp_path / "t_old.json").exists()


def test_flow_task_survives_restart(png_bytes):
    """真实接口（fake 模式）：建任务跑到等审片，清空内存模拟重启，任务和上传都还能查、还能继续审片。"""
    from app.api import uploads
    from app.graph import checkpointer
    from tests.test_flow import client, start_task, wait_for
    task_id = start_task(png_bytes)
    wait_for(task_id, "reviewing", "waiting_user", timeout=20)
    store._tasks.clear()
    uploads.clear()
    assert (settings.state_dir / "tasks" / f"{task_id}.json").exists()
    assert checkpointer.get_tuple({"configurable": {"thread_id": task_id}}) is not None
    data = client.get(f"/api/tasks/{task_id}")
    assert data.status_code == 200 and data.json()["status"] in ("reviewing", "waiting_user")


def test_legacy_error_is_normalized_on_load(tmp_path):
    """旧版本存下的「修了几次还是不够像，换一张更清晰的合照」不能再原样显示成「系统异常」。"""
    import json
    (tmp_path / "t_old2.json").write_text(json.dumps({"status": "failed", "step": "checking", "error": {
        "code": "GENERATION_FAILED", "message": "修了几次还是不够像，换一张更清晰的合照再试试吧"}}), encoding="utf-8")
    error = TaskStore(tmp_path, ttl_days=7).get("t_old2").error
    assert error["category"] == "system" and not error["retryable"]
    assert "合照" not in error["message"] and "重新开始" in error["message"]
    assert "合照" not in json.loads((tmp_path / "t_old2.json").read_text(encoding="utf-8"))["error"]["message"]
