"""全流程测试：fake 模式下通过 6 个接口从上传走到交付。"""

import time

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.common.config import settings

client = TestClient(app)


def wait_for(task_id: str, status: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/tasks/{task_id}").json()
        if data["status"] == status:
            return data
        assert data["status"] != "failed", data["error"]
        time.sleep(0.05)
    raise AssertionError(f"等了 {timeout} 秒还没到 {status}，现在是 {data['status']}")


def start_task(png_bytes: bytes) -> str:
    upload = client.post("/api/uploads", files={"file": ("couple.png", png_bytes, "image/png")})
    assert upload.status_code == 200
    created = client.post("/api/tasks", json={"photo_file_ids": [upload.json()["file_id"]], "description": "想要韩式影棚风"})
    assert created.json()["status"] == "running"
    return created.json()["task_id"]


def answer_questions(task_id: str) -> dict:
    data = wait_for(task_id, "waiting_user")
    assert [q["question_id"] for q in data["questions"]] == ["q_style", "q_height"]
    answers = [{"question_id": "q_style", "value": "korean_studio"}, {"question_id": "q_height", "value": "175 / 162"}]
    assert client.post(f"/api/tasks/{task_id}/answers", json={"answers": answers}).json() == {"status": "running"}
    return wait_for(task_id, "preview_ready")


def test_full_flow_with_one_redo(png_bytes):
    task_id = start_task(png_bytes)
    data = answer_questions(task_id)
    assert len(data["previews"]) == 4
    assert data["previews"][0]["is_best"]

    redo = {"action": "redo", "image_id": data["previews"][1]["image_id"], "reason": "face", "note": "男生不太像"}
    assert client.post(f"/api/tasks/{task_id}/review", json=redo).json() == {"status": "running"}
    data = wait_for(task_id, "preview_ready")
    assert data["previews"][0]["image_id"] == "img_5"

    confirm = {"action": "confirm", "image_id": data["previews"][0]["image_id"]}
    assert client.post(f"/api/tasks/{task_id}/review", json=confirm).json() == {"status": "awaiting_payment"}
    wait_for(task_id, "awaiting_payment")
    assert client.post(f"/api/tasks/{task_id}/pay", json={"method": "mock"}).json() == {"status": "delivering"}

    data = wait_for(task_id, "done")
    assert set(data["deliverables"]) == {"photo", "invitation", "welcome_poster", "led_screen", "moments"}
    assert data["message"]
    assert client.get(data["deliverables"]["invitation"].replace(settings.public_base_url, "")).status_code == 200


def test_failed_check_goes_through_retouch(png_bytes, monkeypatch):
    monkeypatch.setattr(settings, "fake_fail_first_check", True)
    task_id = start_task(png_bytes)
    data = answer_questions(task_id)
    assert [p["image_id"] for p in data["previews"]][0] == "img_5"


def test_wrong_status_and_unknown_task(png_bytes):
    task_id = start_task(png_bytes)
    wait_for(task_id, "waiting_user")
    response = client.post(f"/api/tasks/{task_id}/pay", json={"method": "mock"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "WRONG_STATUS"
    response = client.get("/api/tasks/t_nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_redo_limit(png_bytes, monkeypatch):
    monkeypatch.setattr(settings, "max_user_redo", 0)
    task_id = start_task(png_bytes)
    data = answer_questions(task_id)
    redo = {"action": "redo", "image_id": data["previews"][0]["image_id"], "reason": "style"}
    response = client.post(f"/api/tasks/{task_id}/review", json=redo)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REDO_LIMIT"


@pytest.mark.parametrize("content", [b"not an image", b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024)])
def test_bad_uploads_are_rejected(content):
    response = client.post("/api/uploads", files={"file": ("bad.png", content, "image/png")})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_INVALID"
