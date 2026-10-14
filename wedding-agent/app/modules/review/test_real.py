from copy import deepcopy

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review import check, retouch
from app.modules.review import model_calls, real
from app.modules.review.face_compare import compare_faces, compare_with_extractor, match_embeddings
from app.modules.review.vision import image_block


@pytest.fixture
def real_state(load_state, monkeypatch):
    state = load_state("after_generation")
    state.update(check(state))
    monkeypatch.setattr(settings, "real_modules", ["review"])
    return state


def stub_model(monkeypatch, output=None, error=None):
    calls = []

    class Model:
        max_retries = 1

        def with_structured_output(self, schema, **kwargs):
            assert kwargs == {"method": "function_calling"}
            self.schema = schema
            return self

        def invoke(self, messages):
            calls.append(messages)
            if error:
                raise error
            return self.schema.model_validate(output)

    monkeypatch.setattr(model_calls, "get_llm", lambda kind: Model())
    return calls


def visual_output(state, **changes):
    return {"findings": [{"image_id": candidate["image_id"], "body_ok": True, "hands_ok": True, "subject_count_ok": True, "text_ok": True, "requirements_ok": True, "assessable": True, "issues": [], **changes} for candidate in state["candidates"]]}


def test_face_matching_handles_swap_and_preserves_source_order():
    assert match_embeddings([[1, 0], [0, 1]], [[0, 1], [1, 0]]) == [1.0, 1.0]
    assert match_embeddings([[1, 0], [0, 1]], [[1, 0], [1, 0]]) == [1.0, 0.0]


@pytest.mark.parametrize("vectors", [[], [[1, 0]], [[0, 0], [1, 0]], [[float("nan"), 0], [0, 1]], [[1], [0, 1]], [[True, 0], [0, 1]]])
def test_bad_face_features_are_rejected(vectors):
    with pytest.raises(ModuleError):
        match_embeddings(vectors, [[1, 0], [0, 1]])


def test_extractor_is_task_local():
    calls = []

    def extractor(data):
        calls.append(data)
        return [[1, 0], [0, 1]]

    assert compare_with_extractor(b"source", b"candidate", extractor) == [1.0, 1.0]
    assert calls == [b"source", b"candidate"]
    with pytest.raises(ModuleError):
        compare_faces(b"source", b"candidate")


def test_real_check_uses_asset_bytes_and_one_visual_call(real_state, monkeypatch):
    monkeypatch.setattr(real, "compare_faces", lambda *_: [0.9, 0.85])
    calls = stub_model(monkeypatch, visual_output(real_state))
    original = deepcopy(real_state)
    result = check(real_state)
    assert result["passed"] and result["best_image_id"] == "img_1"
    assert result["scores"][0]["face_sim"] == [0.9, 0.85]
    assert len(calls) == 1
    human = calls[0][1][1]
    assert len([block for block in human if block["type"] == "image_url"]) == 5
    assert "示例酒店" not in str(calls)
    assert "data:image/png;base64," in str(calls)
    assert real_state == original


@pytest.mark.parametrize("flag", ["body_ok", "hands_ok", "subject_count_ok", "text_ok", "requirements_ok", "assessable"])
def test_visual_false_flag_blocks_even_without_issue_text(real_state, monkeypatch, flag):
    monkeypatch.setattr(real, "compare_faces", lambda *_: [0.9, 0.9])
    stub_model(monkeypatch, visual_output(real_state, **{flag: False}))
    result = check(real_state)
    assert result["passed"] is False
    assert all(score["issues"] for score in result["scores"])


def test_one_bad_face_blocks_and_reports_person(real_state, monkeypatch):
    monkeypatch.setattr(real, "compare_faces", lambda *_: [0.9, 0.1])
    stub_model(monkeypatch, visual_output(real_state))
    result = check(real_state)
    assert result["passed"] is False
    assert "人物 B" in result["scores"][0]["issues"][0]


@pytest.mark.parametrize("kind", ["missing", "duplicate", "stale", "wrong_type"])
def test_invalid_visual_results_raise_module_error(real_state, monkeypatch, kind):
    monkeypatch.setattr(real, "compare_faces", lambda *_: [0.9, 0.9])
    output = visual_output(real_state)
    if kind == "missing":
        output["findings"].pop()
    elif kind == "duplicate":
        output["findings"][1]["image_id"] = "img_1"
    elif kind == "stale":
        output["findings"][0]["image_id"] = "old"
    else:
        output["findings"][0]["hands_ok"] = "true"
    stub_model(monkeypatch, output)
    with pytest.raises(ModuleError):
        check(real_state)


def test_missing_face_service_prevents_paid_vision_call(real_state, monkeypatch):
    calls = stub_model(monkeypatch, visual_output(real_state))
    with pytest.raises(ModuleError):
        check(real_state)
    assert calls == []


@pytest.mark.parametrize("value", [[0.9], [0.9, float("nan")], [0.9, 2], [True, 0.9]])
def test_invalid_face_response_blocks_paid_vision(real_state, monkeypatch, value):
    monkeypatch.setattr(real, "compare_faces", lambda *_: value)
    calls = stub_model(monkeypatch, visual_output(real_state))
    with pytest.raises(ModuleError):
        check(real_state)
    assert calls == []


@pytest.mark.parametrize("reason,target", [("face", "generate"), ("hands", "generate"), ("body", "shot"), ("style", "look"), ("other", "prompt")])
def test_real_retouch_uses_structured_agent(real_state, monkeypatch, reason, target):
    real_state["user_feedback"] = {"image_id": "img_1", "reason": reason, "note": "按意见修改"}
    calls = stub_model(monkeypatch, {"target": target, "patch": "保留人物特征并按意见修改", "image_id": None})
    assert retouch(real_state)["retouch_plan"]["target"] == target
    assert len(calls) == 1


@pytest.mark.parametrize("plan", [
    {"target": "none", "patch": "换图", "image_id": "old"},
    {"target": "generate", "patch": "修手", "image_id": "img_1"},
    {"target": "generate", "patch": " ", "image_id": None},
    {"target": "invalid", "patch": "修手", "image_id": None},
])
def test_invalid_agent_plan_is_rejected(real_state, monkeypatch, plan):
    stub_model(monkeypatch, plan)
    with pytest.raises(ModuleError):
        retouch(real_state)


def test_agent_can_choose_current_qualified_candidate(real_state, monkeypatch):
    stub_model(monkeypatch, {"target": "none", "patch": "选择已合格候选", "image_id": "img_2"})
    assert retouch(real_state)["retouch_plan"]["image_id"] == "img_2"


def test_agent_cannot_override_feedback(real_state, monkeypatch):
    real_state["user_feedback"] = {"image_id": "img_1", "reason": "body"}
    stub_model(monkeypatch, {"target": "look", "patch": "换婚纱", "image_id": None})
    with pytest.raises(ModuleError):
        retouch(real_state)


@pytest.mark.parametrize("limit", [0, 1])
def test_call_budget_is_checked_before_invoke(real_state, monkeypatch, limit):
    monkeypatch.setattr(settings, "max_agent_steps", limit)
    calls = stub_model(monkeypatch, {"target": "none", "patch": "换图", "image_id": "img_1"})
    with pytest.raises(ModuleError):
        retouch(real_state)
    assert calls == []


def test_model_error_is_sanitized_and_not_retried(real_state, monkeypatch):
    calls = stub_model(monkeypatch, error=TimeoutError("secret payload"))
    with pytest.raises(ModuleError) as caught:
        retouch(real_state)
    assert len(calls) == 1
    assert "secret" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_image_mime_detection(png_bytes):
    assert "data:image/png" in str(image_block(png_bytes))
    with pytest.raises(ModuleError):
        image_block(b"invalid")


@pytest.mark.parametrize("changes,wrong_target", [
    ({"face_sim": [0.1, 0.9], "issues": ["原图人物 A 与候选人脸相似度不足"]}, "look"),
    ({"hands_ok": False, "issues": ["手部结构异常"]}, "prompt"),
    ({"body_ok": False, "issues": ["身材比例不正确"]}, "generate"),
    ({"issues": ["风格不符合需求"]}, "shot"),
    ({"issues": ["主体人数不正确"]}, "look"),
])
def test_automatic_retouch_cannot_ignore_quality_gate(real_state, monkeypatch, changes, wrong_target):
    for score in real_state["scores"]:
        score.update(changes)
    stub_model(monkeypatch, {"target": wrong_target, "patch": "错误的修改建议", "image_id": None})
    with pytest.raises(ModuleError, match="方向"):
        retouch(real_state)


@pytest.mark.parametrize("issue", ["手部结构异常", "身材比例错误", "存在乱码", "主体人数不正确"])
def test_contradictory_vision_flags_fail_closed(real_state, monkeypatch, issue):
    monkeypatch.setattr(real, "compare_faces", lambda *_: [0.9, 0.9])
    stub_model(monkeypatch, visual_output(real_state, issues=[issue]))
    with pytest.raises(ModuleError, match="矛盾"):
        check(real_state)


def test_concurrent_retouch_isolates_user_opinions(load_state, monkeypatch):
    import json
    from threading import Barrier
    from concurrent.futures import ThreadPoolExecutor

    states = []
    for note in ("任务A保留眼镜", "任务B修正手部"):
        state = load_state("after_generation")
        state.update(check(state))
        state["user_feedback"] = {"image_id": "img_1", "reason": "hands", "note": note}
        states.append(state)
    original = deepcopy(states)
    monkeypatch.setattr(settings, "real_modules", ["review"])
    barrier = Barrier(2)

    class Model:
        max_retries = 1

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def invoke(self, messages):
            note = json.loads(messages[1][1])["user_feedback"]["note"]
            barrier.wait(timeout=5)
            return self.schema.model_validate({"target": "generate", "patch": note, "image_id": None})

    monkeypatch.setattr(model_calls, "get_llm", lambda _: Model())
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(retouch, states))
    assert [result["retouch_plan"]["patch"] for result in results] == [state["user_feedback"]["note"] for state in states]
    assert states == original
