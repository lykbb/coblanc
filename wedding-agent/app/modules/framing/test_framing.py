from app.modules.framing import frame
from app.modules.framing.node import height_band


def answered(state, **choices):
    state["answers"] = [{"question_id": qid, "value": value, "asker": "framing", "round": 1} for qid, value in choices.items()]
    return state


def test_first_call_asks_user_and_gives_draft(load_state):
    update = frame(load_state("after_intake"))
    assert [q["question_id"] for q in update["questions"]] == ["q_interaction", "q_light"]
    assert update["shot"]["pose"] == "keep_original"
    assert update["step_text"].startswith("我是摄影师")


def test_answers_shape_the_shot_and_stop_asking(load_state):
    update = frame(answered(load_state("after_intake"), q_interaction="hug", q_light="backlight"))
    assert "questions" not in update
    shot = update["shot"]
    assert "相拥微笑" in shot["text"] and "傍晚逆光" in shot["text"]
    assert "175cm" in shot["text"] and "162cm" in shot["text"]
    assert shot["references"] == []


def test_height_bands():
    assert height_band([170, 168]) == "close"
    assert height_band([175, 162]) == "medium"
    assert height_band([185, 160]) == "large"
    assert height_band([]) is None


def test_pose_from_assets_becomes_reference(load_state, asset_catalog):
    state = load_state("after_intake")
    state["brief"]["pose"] = "medium_a"
    shot = frame(state)["shot"]
    assert shot["pose"] == "medium_a"
    assert shot["references"][0]["role"] == "pose"
    assert shot["references"][0]["url"].endswith("poses/medium_a.png")


def test_missing_pose_falls_back(load_state, asset_catalog):
    state = load_state("after_intake")
    state["brief"]["pose"] = "large_a"  # 登记了但文件还没放
    shot = frame(state)["shot"]
    assert shot["pose"] == "keep_original"
    assert shot["references"] == []


def test_retouch_applies_patch_without_asking(load_state):
    state = load_state("after_generation")
    state["retouch_plan"] = {"target": "shot", "patch": "两人站近一些", "image_id": None}
    update = frame(state)
    assert "questions" not in update
    assert update["shot"]["pose"] == "keep_original"
    assert "两人站近一些" in update["shot"]["text"]

