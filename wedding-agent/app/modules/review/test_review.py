import pytest

from app.common.config import settings
from app.modules.review import check, retouch


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
