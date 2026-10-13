from app.modules.framing import frame
from app.modules.framing.node import height_band


def test_default_keeps_original_pose(load_state):
    shot = frame(load_state("after_intake"))["shot"]
    assert shot["pose"] == "keep_original"
    assert shot["pose_ref_url"] is None
    assert "175cm" in shot["text"] and "162cm" in shot["text"]


def test_height_bands():
    assert height_band([170, 168]) == "close"
    assert height_band([175, 162]) == "medium"
    assert height_band([185, 160]) == "large"
    assert height_band([]) is None


def test_missing_pose_template_falls_back(load_state):
    state = load_state("after_intake")
    state["brief"]["pose"] = "medium_a"
    shot = frame(state)["shot"]
    assert shot["pose"] == "keep_original"
    assert shot["pose_ref_url"] is None


def test_retouch_to_shot_applies_patch(load_state):
    state = load_state("after_intake")
    state["retouch_plan"] = {"target": "shot", "patch": "两人站近一些", "image_id": None}
    shot = frame(state)["shot"]
    assert shot["pose"] == "keep_original"
    assert "两人站近一些" in shot["text"]
