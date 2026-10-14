"""用合成双人示意图通过六个真实接口验证 review 的 fake 流程。"""

import struct
import json
import time
import zlib

import pytest
from fastapi.testclient import TestClient

from app import runner
from app.api import app
from app.common.config import settings
from app.modules.review import node


@pytest.fixture
def couple_png() -> bytes:
    """内存绘制两位几何人物，无真人照片；只用于接口及流程测试。"""
    width, height = 256, 192
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            color = (235, 228, 220)
            for center, clothes in [(85, (40, 48, 65)), (170, (255, 255, 255))]:
                if ((x - center) / 20) ** 2 + ((y - 65) / 24) ** 2 <= 1:
                    color = (215, 173, 145)
                if 92 <= y <= 180 and abs(x - center) < 28:
                    color = clothes
                if y in (61, 62) and abs(abs(x - center) - 7) < 2:
                    color = (40, 40, 40)
            row.extend(color)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


@pytest.fixture
def api_client(monkeypatch):
    # 隔离真实模块开关，避免此流程测试意外访问收费服务。
    monkeypatch.setattr(settings, "fake", True)
    monkeypatch.setattr(settings, "real_modules", [])
    monkeypatch.setattr(settings, "fake_delay_seconds", 0)
    with TestClient(app) as client:
        yield client


def _wait(client: TestClient, task_id: str, *statuses: str) -> dict:
    deadline = time.monotonic() + 10
    data = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in statuses:
            return data
        assert data["status"] != "failed", data["error"]
        time.sleep(0.01)
    pytest.fail(f"任务未进入预期状态 {statuses}，当前状态 {data.get('status')}")


def _upload_and_answer(client: TestClient, image: bytes) -> tuple[str, dict]:
    upload = client.post("/api/uploads", files={"file": ("synthetic_couple.png", image, "image/png")})
    assert upload.status_code == 200
    created = client.post("/api/tasks", json={"photo_file_ids": [upload.json()["file_id"]], "description": "韩式影棚风，保留两人原有特征"})
    assert created.status_code == 200
    task_id = created.json()["task_id"]
    speakers = []
    for _ in range(3 * settings.max_question_rounds + 1):
        data = _wait(client, task_id, "waiting_user", "preview_ready", "failed")
        if data["status"] != "waiting_user":
            assert speakers == ["intake", "styling", "framing"]
            return task_id, data
        speakers.append(data["step"])
        assert data["step_text"] and data["questions"]
        answers = []
        for question in data["questions"]:
            value = question.get("recommended")
            answers.append({"question_id": question["question_id"], "value": value if value is not None else "175 / 162"})
        response = client.post(f"/api/tasks/{task_id}/answers", json={"answers": answers})
        assert response.status_code == 200
    pytest.fail("对话轮数超过框架规定上限")


def _deliver(client: TestClient, task_id: str, previews: dict) -> None:
    # 故意确认第二张，验证最终交付遵从用户选择，而非默认推荐。
    selected = previews["previews"][1]["image_id"]
    response = client.post(f"/api/tasks/{task_id}/review", json={"action": "confirm", "image_id": selected})
    assert response.status_code == 200
    _wait(client, task_id, "awaiting_payment")
    assert client.post(f"/api/tasks/{task_id}/pay", json={"method": "mock"}).status_code == 200
    done = _wait(client, task_id, "done")
    assert runner.values(task_id)["best_image_id"] == selected
    assert set(done["deliverables"]) == {"photo", "invitation", "welcome_poster", "led_screen", "moments"}
    assert done["message"] and len(done["message"]) <= 50
    for url in done["deliverables"].values():
        image = client.get(url.replace(settings.public_base_url, "", 1))
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("reason,target", [("face", "generate"), ("hands", "generate"), ("body", "shot"), ("style", "look"), ("other", "prompt")])
def test_upload_redo_and_deliver(api_client, couple_png, reason, target):
    task_id, preview = _upload_and_answer(api_client, couple_png)
    assert preview["status"] == "preview_ready"
    assert len(preview["previews"]) == 4
    before = runner.values(task_id)
    original_photos = list(before["photo_urls"])
    original_answers = list(before["answers"])
    response = api_client.post(f"/api/tasks/{task_id}/review", json={"action": "redo", "image_id": preview["previews"][0]["image_id"], "reason": reason, "note": "模拟返工：保留本人特征"})
    assert response.status_code == 200
    renewed = _wait(api_client, task_id, "preview_ready", "waiting_user")
    assert renewed["status"] == "preview_ready"  # 返工不再追问。
    after = runner.values(task_id)
    assert after["retouch_plan"]["target"] == target
    assert after["photo_urls"] == original_photos
    assert after["answers"] == original_answers
    assert not {item["image_id"] for item in before["candidates"]} & {item["image_id"] for item in after["candidates"]}
    if target == "look":
        assert after["shot"] == before["shot"]
    if target == "shot":
        assert after["look"] == before["look"]
    _deliver(api_client, task_id, renewed)


def test_automatic_retouch_then_delivery(api_client, couple_png, monkeypatch):
    monkeypatch.setattr(settings, "fake_fail_first_check", True)
    task_id, preview = _upload_and_answer(api_client, couple_png)
    values = runner.values(task_id)
    assert values["retry_count"] == 1
    assert values["retouch_plan"]["target"] == "generate"
    assert values["passed"] is True
    _deliver(api_client, task_id, preview)


def test_persistent_defect_stops_at_retry_limit(api_client, couple_png, monkeypatch):
    original = node._fake_scores

    def always_bad(state, candidates):
        scores = original(state, candidates)
        for score in scores:
            score["hands_ok"] = False
            score["issues"] = ["手部结构异常"]
        return scores

    monkeypatch.setattr(node, "_fake_scores", always_bad)
    task_id, failed = _upload_and_answer(api_client, couple_png)
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "GENERATION_FAILED"
    assert runner.values(task_id)["retry_count"] == settings.max_retouch
    assert failed["previews"] == [] and failed["deliverables"] is None


def _real_models(monkeypatch, *, initial_hands_failure=False, broken_vision=False, broken_agent=False):
    """走真实 review 分支，但图片特征与模型调用用明确的测试替身。"""
    from app.modules.review import real, model_calls
    monkeypatch.setattr(settings, "real_modules", ["review"])
    monkeypatch.setattr(real, "compare_faces", lambda *_: [0.9, 0.9])
    calls = {"vision": 0, "agent": 0}

    class Model:
        max_retries = 1

        def __init__(self, kind):
            self.kind = kind

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def invoke(self, messages):
            calls[self.kind] += 1
            if self.kind == "vision":
                ids = [block["text"].removeprefix("候选 image_id=") for block in messages[1][1] if block.get("type") == "text" and block["text"].startswith("候选 image_id=")]
                if broken_vision:
                    ids.pop()
                hands_ok = not (initial_hands_failure and calls["vision"] == 1)
                return self.schema.model_validate({"findings": [{"image_id": image_id, "body_ok": True, "hands_ok": hands_ok, "subject_count_ok": True, "text_ok": True, "requirements_ok": True, "assessable": True, "issues": []} for image_id in ids]})
            payload = json.loads(messages[1][1])
            feedback = payload["user_feedback"]
            reason = feedback.get("reason", "hands")
            target = {"face": "generate", "hands": "generate", "body": "shot", "style": "look", "other": "prompt"}[reason]
            return self.schema.model_validate({"target": "none" if broken_agent else target, "patch": "修正手部并保留原图身份", "image_id": "old" if broken_agent else None})

    monkeypatch.setattr(model_calls, "get_llm", lambda kind: Model(kind))
    return calls


def test_real_review_branch_retouches_and_delivers_with_test_services(api_client, couple_png, monkeypatch):
    calls = _real_models(monkeypatch, initial_hands_failure=True)
    task_id, preview = _upload_and_answer(api_client, couple_png)
    assert preview["status"] == "preview_ready"
    assert runner.values(task_id)["retry_count"] == 1
    assert calls == {"vision": 2, "agent": 1}
    _deliver(api_client, task_id, preview)


def test_incomplete_visual_batch_blocks_only_missing_candidate(api_client, couple_png, monkeypatch):
    _real_models(monkeypatch, broken_vision=True)
    task_id, data = _upload_and_answer(api_client, couple_png)
    assert data["status"] == "preview_ready"
    scores = runner.values(task_id)["scores"]
    assert "无法质检" in "；".join(scores[-1]["issues"])
    assert runner.values(task_id)["best_image_id"] != scores[-1]["image_id"]
    _deliver(api_client, task_id, data)


def test_invalid_agent_switch_is_corrected_and_delivers(api_client, couple_png, monkeypatch):
    _real_models(monkeypatch, broken_agent=True)
    task_id, preview = _upload_and_answer(api_client, couple_png)
    response = api_client.post(f"/api/tasks/{task_id}/review", json={"action": "redo", "image_id": preview["previews"][0]["image_id"], "reason": "hands"})
    assert response.status_code == 200
    preview = _wait(api_client, task_id, "preview_ready")
    assert runner.values(task_id)["retouch_plan"]["target"] == "generate"
    _deliver(api_client, task_id, preview)


def test_parallel_tasks_do_not_share_photos_or_delivery(api_client, couple_png):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_upload_and_answer, api_client, couple_png) for _ in range(2)]
        completed = [future.result(timeout=15) for future in futures]
    first, second = [runner.values(task_id) for task_id, _ in completed]
    assert completed[0][0] != completed[1][0]
    assert first["photo_urls"] != second["photo_urls"]
    assert {candidate["url"] for candidate in first["candidates"]}.isdisjoint(candidate["url"] for candidate in second["candidates"])
    for task_id, preview in completed:
        _deliver(api_client, task_id, preview)


def test_two_redos_then_limit_preserves_preview(api_client, couple_png, monkeypatch):
    monkeypatch.setattr(settings, "max_user_redo", 2)
    task_id, preview = _upload_and_answer(api_client, couple_png)
    for reason in ("body", "hands"):
        response = api_client.post(f"/api/tasks/{task_id}/review", json={"action": "redo", "image_id": preview["previews"][0]["image_id"], "reason": reason})
        assert response.status_code == 200
        preview = _wait(api_client, task_id, "preview_ready", "waiting_user")
        assert preview["status"] == "preview_ready"
    response = api_client.post(f"/api/tasks/{task_id}/review", json={"action": "redo", "image_id": preview["previews"][0]["image_id"], "reason": "style"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "REDO_LIMIT"
    assert api_client.get(f"/api/tasks/{task_id}").json()["status"] == "preview_ready"
    _deliver(api_client, task_id, preview)
