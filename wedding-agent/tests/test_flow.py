"""全流程测试：fake 模式下通过 6 个接口从上传走到交付。"""

import time

import pytest
from fastapi.testclient import TestClient

from app import runner
from app.api import app
from app.common.config import settings

client = TestClient(app)


def wait_for(task_id: str, *statuses: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/tasks/{task_id}").json()
        if data["status"] in statuses:
            return data
        assert data["status"] != "failed", data["error"]
        time.sleep(0.05)
    raise AssertionError(f"等了 {timeout} 秒还没到 {statuses}，现在是 {data['status']}")


def start_task(png_bytes: bytes) -> str:
    ids = []
    for name in ("couple.png", "couple2.png"):  # 两张不同的上传（同一张传两次只算一张）
        upload = client.post("/api/uploads", files={"file": (name, png_bytes, "image/png")})
        assert upload.status_code == 200
        ids.append(upload.json()["file_id"])
    created = client.post("/api/tasks", json={"photo_file_ids": ids, "description": "想要韩式影棚风"})
    assert created.json()["status"] == "running"
    return created.json()["task_id"]


def start_grouped_task(png_bytes: bytes) -> str:
    uploads_for_roles = []
    for name in ("groom.png", "bride.png"):
        upload = client.post("/api/uploads", files={"file": (name, png_bytes, "image/png")})
        assert upload.status_code == 200
        uploads_for_roles.append(upload.json()["file_id"])
    created = client.post(
        "/api/tasks",
        json={
            "groom_photo_file_ids": [uploads_for_roles[0]],
            "bride_photo_file_ids": [uploads_for_roles[1]],
            "description": "想要法式 editorial 风格",
        },
    )
    assert created.json()["status"] == "running"
    return created.json()["task_id"]


def answer_questions(task_id: str) -> tuple[dict, list[str]]:
    """依次回答小囍、妆造师、摄影师的提问，直到出预览；返回预览数据和提问人的顺序。"""
    speakers = []
    while True:
        data = wait_for(task_id, "waiting_user", "preview_ready")
        if data["status"] == "preview_ready":
            return data, speakers
        speakers.append(data["step"])
        assert data["step_text"] and data["questions"]
        answers = [
            {"question_id": q["question_id"], "value": q.get("recommended") or "175 / 162"} for q in data["questions"]
        ]
        assert client.post(f"/api/tasks/{task_id}/answers", json={"answers": answers}).json() == {"status": "running"}


def test_full_flow_with_one_redo(png_bytes):
    task_id = start_task(png_bytes)
    data, speakers = answer_questions(task_id)
    # 按出场顺序去重：每位 agent 可以问多轮（例如妆造师先问风格、再问套系）
    assert list(dict.fromkeys(speakers)) == ["intake", "styling", "framing"]  # 小囍、妆造师、摄影师依次和用户对话
    assert len(data["previews"]) == 1
    assert data["generation"]["stage"] == "sample"
    assert data["previews"][0]["is_best"]

    redo = {"action": "redo", "image_id": data["previews"][0]["image_id"], "reason": "face", "note": "男生不太像"}
    assert client.post(f"/api/tasks/{task_id}/review", json=redo).json() == {"status": "running"}
    data = wait_for(task_id, "preview_ready")
    assert data["previews"][0]["image_id"] == "img_2"

    confirm = {"action": "confirm", "image_id": data["previews"][0]["image_id"]}
    assert client.post(f"/api/tasks/{task_id}/review", json=confirm).json() == {"status": "running"}
    data = wait_for(task_id, "preview_ready")
    assert len(data["previews"]) == 9
    assert data["generation"]["stage"] == "set"
    confirm = {"action": "confirm", "image_id": data["previews"][0]["image_id"]}
    assert client.post(f"/api/tasks/{task_id}/review", json=confirm).json() == {"status": "awaiting_payment"}
    wait_for(task_id, "awaiting_payment")
    assert client.post(f"/api/tasks/{task_id}/pay", json={"method": "mock"}).json() == {"status": "delivering"}

    data = wait_for(task_id, "done")
    assert set(data["deliverables"]) == {"photo", "photos", "invitation", "welcome_poster", "led_screen", "moments"}
    assert len(data["deliverables"]["photos"]) == 9
    assert data["message"]
    assert client.get(data["deliverables"]["invitation"].replace(settings.public_base_url, "")).status_code == 200

    values = runner.values(task_id)  # 小囍把妆造师和摄影师跟用户确认的结果写进了提示词
    assert "清透韩妆" in values["prompt"] or "自然淡妆" in values["prompt"]
    assert values["look"]["text"] in values["prompt"]
    assert values["shot"]["text"] in values["prompt"]
    assert {item["asker"] for item in values["answers"]} == {"intake", "styling", "framing"}


def test_grouped_photo_flow_records_counts_and_consent(png_bytes):
    task_id = start_grouped_task(png_bytes)
    data, speakers = answer_questions(task_id)
    assert list(dict.fromkeys(speakers)) == ["intake", "styling", "framing"]
    status = client.get(f"/api/tasks/{task_id}").json()
    assert status["photo_counts"] == {"groom": 1, "bride": 1, "legacy": 0}
    # plan：前端画布用的只读方案进度，不带提示词等内部字段
    plan = status["plan"]
    assert len(plan["photos"]["groom"]) == 1 and len(plan["photos"]["bride"]) == 1
    assert plan["look"]["text"] and plan["shot"]["text"] and len(plan["shots"]) == settings.set_candidates
    assert set(plan["brief"]) == {"heights_cm", "materials", "invitation", "keep_features", "beautify"}
    assert "prompt" not in plan
    values = runner.values(task_id)
    assert values["consent"]["confirmed"] is True


@pytest.mark.parametrize("reason", ["face", "body", "style", "other"])
def test_redo_goes_back_to_the_right_module_without_asking_again(png_bytes, reason):
    task_id = start_task(png_bytes)
    data, _ = answer_questions(task_id)
    redo = {"action": "redo", "image_id": data["previews"][0]["image_id"], "reason": reason, "note": "再改改"}
    client.post(f"/api/tasks/{task_id}/review", json=redo)
    data = wait_for(task_id, "preview_ready", "waiting_user")
    assert data["status"] == "preview_ready"  # 修图阶段不会再问用户
    assert data["previews"][0]["image_id"] == "img_2"
    values = runner.values(task_id)
    if reason == "style":
        assert "再改改" in values["look"]["text"] and "再改改" in values["prompt"]
    if reason == "body":
        assert "再改改" in values["shot"]["text"] and "再改改" in values["prompt"]
    if reason == "other":
        assert "再改改" in values["prompt"]


def test_failed_check_goes_through_retouch(png_bytes, monkeypatch):
    monkeypatch.setattr(settings, "fake_fail_first_check", True)
    task_id = start_task(png_bytes)
    data, _ = answer_questions(task_id)
    assert data["previews"][0]["image_id"] == "img_2"


def test_each_agent_asks_at_most_max_rounds(png_bytes):
    task_id = start_task(png_bytes)
    asked = []
    while True:
        data = wait_for(task_id, "waiting_user", "preview_ready")
        if data["status"] == "preview_ready":
            break
        asked.append(data["step"])
        client.post(f"/api/tasks/{task_id}/answers", json={"answers": []})  # 什么都不答
    rounds = settings.max_question_rounds
    assert asked == ["intake"] * rounds + ["styling"] * rounds + ["framing"] * rounds


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
    data, _ = answer_questions(task_id)
    redo = {"action": "redo", "image_id": data["previews"][0]["image_id"], "reason": "style"}
    response = client.post(f"/api/tasks/{task_id}/review", json=redo)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REDO_LIMIT"


@pytest.mark.parametrize("content", [b"not an image", b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024)])
def test_bad_uploads_are_rejected(content):
    response = client.post("/api/uploads", files={"file": ("bad.png", content, "image/png")})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_INVALID"


def test_upload_answer_gets_urls(png_bytes, monkeypatch):
    """回答补传题时，框架把上传编号换成地址，附在这条回答的 urls 里。"""
    from app import api

    upload = client.post("/api/uploads", files={"file": ("new.png", png_bytes, "image/png")}).json()["file_id"]
    question = {"question_id": "q_groom_photos", "type": "upload", "title": "补传", "allow_skip": False}
    monkeypatch.setattr(api.runner, "values", lambda task_id: {"questions": [question, {"question_id": "q_height", "type": "text", "title": "身高"}]})
    monkeypatch.setattr(api, "_task", lambda task_id: None)
    answers = api._attach_upload_urls("t_x", [
        {"question_id": "q_groom_photos", "value": [upload], "skipped": False},
        {"question_id": "q_height", "value": "175 / 162", "skipped": False},
    ])
    assert answers[0]["urls"] == [api.uploads[upload]] and answers[0]["value"] == [upload]
    assert "urls" not in answers[1]
    single = api._attach_upload_urls("t_x", [{"question_id": "q_groom_photos", "value": upload, "skipped": False}])
    assert single[0]["urls"] == [api.uploads[upload]]
    with pytest.raises(api.ApiError):
        api._attach_upload_urls("t_x", [{"question_id": "q_groom_photos", "value": ["f_missing"], "skipped": False}])


def test_sample_only_skips_set_and_delivers_sample(png_bytes):
    task_id = start_grouped_task(png_bytes)
    data, _ = answer_questions(task_id)
    assert data["generation"]["stage"] == "sample"
    choice = {"action": "sample_only", "image_id": data["previews"][0]["image_id"]}
    assert client.post(f"/api/tasks/{task_id}/review", json=choice).json() == {"status": "awaiting_payment"}
    wait_for(task_id, "awaiting_payment")
    assert client.post(f"/api/tasks/{task_id}/pay", json={"method": "mock"}).json() == {"status": "delivering"}
    data = wait_for(task_id, "done")
    assert data["generation"]["stage"] == "sample" and data["generation"]["total_images"] == 1
    assert {"photo", "invitation", "welcome_poster", "led_screen", "moments"} <= set(data["deliverables"])


def test_sample_only_rejected_in_set_stage(png_bytes):
    task_id = start_grouped_task(png_bytes)
    data, _ = answer_questions(task_id)
    confirm = {"action": "confirm", "image_id": data["previews"][0]["image_id"]}
    client.post(f"/api/tasks/{task_id}/review", json=confirm)
    data = wait_for(task_id, "preview_ready")
    assert data["generation"]["stage"] == "set"
    choice = {"action": "sample_only", "image_id": data["previews"][0]["image_id"]}
    response = client.post(f"/api/tasks/{task_id}/review", json=choice)
    assert response.status_code == 409 and response.json()["error"]["code"] == "WRONG_STATUS"


def test_set_shots_have_distinct_prompts(png_bytes):
    task_id = start_grouped_task(png_bytes)
    answer_questions(task_id)
    values = runner.values(task_id)
    shots, prompts = values["shots"], values["shot_prompts"]
    assert [item["slot"] for item in shots] == list(range(settings.set_candidates))
    assert len({item["text"] for item in shots}) == len(shots)
    assert len({item["prompt"] for item in prompts}) == len(prompts) == len(shots)
    assert all(item["prompt"].startswith(values["prompt"]) for item in prompts)


def test_single_upload_box_accepts_one_to_ten(png_bytes):
    ids = [client.post("/api/uploads", files={"file": ("p.png", png_bytes, "image/png")}).json()["file_id"]
           for _ in range(11)]
    for bad in ([], ids):
        response = client.post("/api/tasks", json={"photo_file_ids": bad})
        assert response.status_code == 400 and response.json()["error"]["code"] == "PHOTO_INVALID"
    assert client.post("/api/tasks", json={"photo_file_ids": ids[:10]}).json()["status"] == "running"


def test_grouped_create_rejects_more_than_ten(png_bytes):
    ids = [client.post("/api/uploads", files={"file": ("p.png", png_bytes, "image/png")}).json()["file_id"]
           for _ in range(11)]
    response = client.post("/api/tasks", json={"groom_photo_file_ids": ids, "bride_photo_file_ids": ids[:1]})
    assert response.status_code == 400 and response.json()["error"]["code"] == "PHOTO_INVALID"
