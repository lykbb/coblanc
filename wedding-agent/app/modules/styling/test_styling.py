import pytest

from app.modules.styling import style
from app.modules.styling.node import available_styles


@pytest.mark.parametrize("style_id", available_styles())
def test_every_style_fills_all_placeholders(load_state, style_id):
    state = load_state("after_intake")
    state["brief"]["style"] = style_id
    look = style(state)["look"]
    assert "{" not in look["text"] and "}" not in look["text"]
    assert look["style"] == style_id


def test_keeps_features_and_applies_patch(load_state):
    state = load_state("after_intake")
    state["retouch_plan"] = {"target": "look", "patch": "换成缎面鱼尾婚纱", "image_id": None}
    text = style(state)["look"]["text"]
    assert "女生的眼镜" in text
    assert "换成缎面鱼尾婚纱" in text


def test_unknown_style_falls_back_to_default(load_state):
    state = load_state("after_intake")
    state["brief"]["style"] = "no_such_style"
    assert style(state)["look"]["style"] == "keep_original"
