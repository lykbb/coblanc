import pytest

from app.modules.styling import style
from app.modules.styling.node import available_styles


def answered(state, **choices):
    state["answers"] = [{"question_id": qid, "value": value, "asker": "styling", "round": 1} for qid, value in choices.items()]
    return state


@pytest.mark.parametrize("style_id", available_styles())
def test_every_style_fills_all_placeholders(load_state, style_id):
    state = load_state("after_intake")
    state["brief"]["style"] = style_id
    look = style(state)["look"]
    assert "{" not in look["text"] and "}" not in look["text"]
    assert look["style"] == style_id


def test_first_call_asks_user_and_gives_draft(load_state):
    update = style(load_state("after_intake"))
    assert [q["question_id"] for q in update["questions"]] == ["q_makeup", "q_outfit"]
    assert "自然淡妆" in update["look"]["text"]  # 草稿用推荐选项
    assert update["step_text"].startswith("我是妆造师")


def test_answers_shape_the_look_and_stop_asking(load_state):
    update = style(answered(load_state("after_intake"), q_makeup="retro", q_outfit="mermaid"))
    assert "questions" not in update
    assert "复古红唇" in update["look"]["text"]
    assert "鱼尾拖尾婚纱" in update["look"]["text"]


def test_does_not_ask_during_retouch(load_state):
    state = load_state("after_generation")
    state["retouch_plan"] = {"target": "look", "patch": "换成缎面鱼尾婚纱", "image_id": None}
    update = style(state)
    assert "questions" not in update
    assert "换成缎面鱼尾婚纱" in update["look"]["text"]


def test_keeps_features(load_state):
    assert "女生的眼镜" in style(load_state("after_intake"))["look"]["text"]


def test_unknown_style_falls_back_to_default(load_state):
    state = load_state("after_intake")
    state["brief"]["style"] = "no_such_style"
    assert style(state)["look"]["style"] == "keep_original"


def test_asset_options_carry_pictures_and_become_references(load_state, asset_catalog):
    state = load_state("after_intake")
    outfit_question = style(state)["questions"][1]
    assert outfit_question["options"][0]["value"] == "outfit_korean_satin"
    assert outfit_question["options"][0]["image"].endswith("outfits/korean_satin.png")
    look = style(answered(state, q_outfit="outfit_korean_satin"))["look"]
    assert look["references"] == [{"url": outfit_question["options"][0]["image"], "role": "outfit"}]


def test_no_reference_when_assets_empty(load_state):
    assert style(load_state("after_intake"))["look"]["references"] == []
