from copy import deepcopy
from pathlib import Path

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review import check, retouch
from app.modules.review import node
from app.modules.review.batch_eval import evaluate_cases


def test_fake_check_passes_and_picks_best(load_state):
    update = check(load_state("after_generation"))
    assert update["passed"] is True
    assert update["best_image_id"] == "img_1"
    assert len(update["scores"]) == 4
    for score in update["scores"]:
        assert {"image_id", "face_sim", "body_ok", "hands_ok", "issues", "total"} <= score.keys()
        assert len(score["face_sim"]) == 2


def test_fail_first_check(load_state, monkeypatch):
    monkeypatch.setattr(settings, "fake_fail_first_check", True)
    update = check(load_state("after_generation"))
    assert update["passed"] is False
    assert update["best_image_id"] is None


@pytest.mark.parametrize(
    "reason, target",
    [("face", "generate"), ("hands", "generate"), ("body", "shot"), ("style", "look"), ("other", "prompt")],
)
def test_retouch_follows_user_reason(load_state, reason, target):
    state = load_state("after_generation")
    state["user_feedback"] = {"image_id": "img_2", "reason": reason, "note": "不太满意"}
    plan = retouch(state)["retouch_plan"]
    assert plan["target"] == target
    assert plan["patch"] == "不太满意"


def test_retouch_without_feedback_regenerates(load_state):
    assert retouch(load_state("after_generation"))["retouch_plan"]["target"] == "generate"


@pytest.fixture
def scored_state(load_state):
    state = load_state("after_generation")
    return {**state, **check(state)}


@pytest.mark.parametrize("index", [0, 1])
def test_either_face_below_threshold_fails(scored_state, monkeypatch, index):
    scores = scored_state["scores"]
    for score in scores:
        score["face_sim"][index] = settings.face_sim_threshold - 0.01
    monkeypatch.setattr(node, "_fake_scores", lambda *_: scores)
    result = check(scored_state)
    assert result["passed"] is False
    assert result["best_image_id"] is None
    assert retouch({**scored_state, **result})["retouch_plan"]["target"] == "generate"


def test_threshold_is_inclusive(scored_state, monkeypatch):
    scores = scored_state["scores"]
    for score in scores:
        score["face_sim"] = [settings.face_sim_threshold] * 2
    monkeypatch.setattr(node, "_fake_scores", lambda *_: scores)
    assert check(scored_state)["passed"] is True


@pytest.mark.parametrize(
    "changes, target",
    [
        ({"body_ok": False}, "shot"),
        ({"hands_ok": False}, "generate"),
        ({"issues": ["多余人物"]}, "generate"),
        ({"issues": ["乱码文字"]}, "prompt"),
        ({"issues": ["风格与需求不符"]}, "look"),
        ({"issues": ["身高比例不正确"]}, "shot"),
    ],
)
def test_defects_block_check_and_route_retouch(scored_state, monkeypatch, changes, target):
    scores = scored_state["scores"]
    for score in scores:
        score.update(deepcopy(changes))
    monkeypatch.setattr(node, "_fake_scores", lambda *_: scores)
    result = check(scored_state)
    assert result["passed"] is False
    assert result["best_image_id"] is None
    plan = retouch({**scored_state, **result})["retouch_plan"]
    assert plan["target"] == target
    assert plan["image_id"] is None
    assert plan["patch"]


def test_higher_total_does_not_override_failed_quality(scored_state, monkeypatch):
    scores = scored_state["scores"]
    scores[0].update(total=1.0, issues=["乱码文字"])
    monkeypatch.setattr(node, "_fake_scores", lambda *_: scores)
    assert check(scored_state)["best_image_id"] == "img_2"


def test_retouch_can_reuse_qualified_candidate(scored_state):
    plan = retouch(scored_state)["retouch_plan"]
    assert plan["target"] == "none"
    assert plan["image_id"] == "img_1"


def test_user_feedback_takes_priority_over_old_scores(scored_state):
    scored_state["user_feedback"] = {"image_id": "img_1", "reason": "style", "note": "换中式风格"}
    plan = retouch(scored_state)["retouch_plan"]
    assert plan == {"target": "look", "patch": "换中式风格", "image_id": None}


@pytest.mark.parametrize("function", [check, retouch])
def test_does_not_mutate_input(scored_state, function):
    original = deepcopy(scored_state)
    function(scored_state)
    assert scored_state == original


@pytest.mark.parametrize("candidates", [[], None, [{}]])
@pytest.mark.parametrize("function", [check, retouch])
def test_invalid_candidates_raise_module_error(function, candidates):
    with pytest.raises(ModuleError) as caught:
        function({"candidates": candidates})
    assert caught.value.code == "GENERATION_FAILED"


def test_duplicate_candidates_are_rejected(scored_state):
    scored_state["candidates"][1]["image_id"] = "img_1"
    with pytest.raises(ModuleError):
        check(scored_state)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_numeric_scores_are_rejected(scored_state, value):
    scored_state["scores"][0]["face_sim"][0] = value
    with pytest.raises(ModuleError):
        retouch(scored_state)


@pytest.mark.parametrize("invalid", ["stale", "duplicate", "missing", "one_face"])
def test_invalid_score_coverage_is_rejected(scored_state, monkeypatch, invalid):
    scores = scored_state["scores"]
    if invalid == "stale":
        scores[0]["image_id"] = "old_image"
    elif invalid == "duplicate":
        scores[1]["image_id"] = scores[0]["image_id"]
    elif invalid == "missing":
        scores.pop()
    else:
        scores[0]["face_sim"] = [0.9]
    monkeypatch.setattr(node, "_fake_scores", lambda *_: scores)
    with pytest.raises(ModuleError):
        check(scored_state)


def test_cannot_switch_to_stale_candidate(scored_state):
    scored_state["scores"][0]["image_id"] = "old_image"
    with pytest.raises(ModuleError):
        retouch(scored_state)


def test_invalid_feedback_image_is_rejected(scored_state):
    scored_state["user_feedback"] = {"image_id": "old_image", "reason": "face"}
    with pytest.raises(ModuleError):
        retouch(scored_state)


@pytest.mark.parametrize("feedback", ["invalid", {"image_id": "img_1", "reason": "unknown"}, {"image_id": "img_1", "reason": ["face"]}, {"image_id": "img_1", "reason": "face", "note": ["invalid"]}])
def test_invalid_feedback_is_reported_as_module_error(scored_state, feedback):
    scored_state["user_feedback"] = feedback
    with pytest.raises(ModuleError):
        retouch(scored_state)


def test_skipped_note_uses_target_specific_patch(scored_state):
    scored_state["user_feedback"] = {"image_id": "img_1", "reason": "body", "note": ""}
    plan = retouch(scored_state)["retouch_plan"]
    assert plan["target"] == "shot"
    assert "身高差" in plan["patch"]


def test_fake_never_calls_services(load_state, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("fake 模式不能访问模型或图片")

    monkeypatch.setattr("app.common.llm.get_llm", forbidden)
    monkeypatch.setattr("app.modules.assets.load_image", forbidden)
    state = load_state("after_generation")
    check(state)
    retouch(state)


def test_fail_first_recovers_after_retry(load_state, monkeypatch):
    monkeypatch.setattr(settings, "fake_fail_first_check", True)
    state = load_state("after_generation")
    state["retry_count"] = 1
    assert check(state)["passed"] is True


@pytest.mark.parametrize("function", [check, retouch])
def test_real_mode_reports_not_ready(load_state, monkeypatch, function):
    monkeypatch.setattr(settings, "real_modules", ["review"])
    with pytest.raises(ModuleError) as caught:
        function(load_state("after_generation"))
    assert caught.value.code == "GENERATION_FAILED"
    if function is check:
        assert "尚未接入" in caught.value.message
    else:
        assert "质检" in caught.value.message


def test_batch_fixture_outputs_scores_without_photo_urls():
    fixture = Path(__file__).resolve().parents[3] / "tests/fixtures/after_generation.json"
    reports, failed = evaluate_cases([fixture])
    assert failed is False
    assert reports[0]["mode"] == "fake"
    assert len(reports[0]["result"]["scores"]) == 4
    assert "photo_urls" not in str(reports)


def test_batch_continues_after_invalid_case(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    valid = Path(__file__).resolve().parents[3] / "tests/fixtures/after_generation.json"
    reports, failed = evaluate_cases([invalid, valid])
    assert failed is True
    assert reports[0]["error"]["code"] == "FILE_INVALID"
    assert reports[1]["result"]["passed"] is True
