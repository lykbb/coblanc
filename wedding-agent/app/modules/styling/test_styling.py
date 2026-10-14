from __future__ import annotations

from app.modules.styling import style
from app.modules.styling import node


def state(description: str = "", answers: list[dict] | None = None, **extra) -> dict:
    return {
        "brief": {"keep_features": ["女生的眼镜"], "beautify": "none", "heights_cm": [175, 162]},
        "description": description,
        "answers": answers or [],
        **extra,
    }


def answer(question_id: str, value=None, *, skipped: bool = False) -> dict:
    return {"question_id": question_id, "value": value, "skipped": skipped, "asker": "styling", "round": 1}


def test_first_call_only_asks_style_and_returns_both_people_draft():
    update = style(state())
    assert [q["question_id"] for q in update["questions"]] == ["q_style"]
    assert update["questions"][0]["allow_skip"] is True
    assert "新娘" in update["look"]["text"] and "新郎" in update["look"]["text"]
    assert "女生的眼镜" in update["look"]["text"]


def test_clear_description_skips_style_and_asks_look_set():
    update = style(state("想要韩式影棚风"))
    assert [q["question_id"] for q in update["questions"]] == ["q_look_set"]
    assert update["look"]["style"] == "korean_studio"


def test_two_answers_stop_questions():
    answers = [answer("q_style", "retro"), answer("q_look_set", "look_set_retro_wave")]
    update = style(state(answers=answers))
    assert "questions" not in update
    assert update["look"]["style"] == "retro"
    assert "复古红唇" in update["look"]["text"]


def test_skipping_style_still_moves_to_second_round():
    update = style(state(answers=[answer("q_style", skipped=True)]))
    assert [q["question_id"] for q in update["questions"]] == ["q_look_set"]


def test_retouch_and_candidates_never_ask():
    for extra in (
        {"candidates": [{"image_id": "x", "url": "u", "seed": 1}]},
        {"retouch_plan": {"target": "look", "patch": "改为低盘发", "image_id": None}},
    ):
        update = style(state(**extra))
        assert "questions" not in update
        if "retouch_plan" in extra:
            assert "改为低盘发" in update["look"]["text"]


def test_asset_style_and_look_set_options_and_references(monkeypatch):
    def fake_search(kind, tags=None):
        if kind == "style":
            return [{"asset_id": "style_korean_studio", "name": "韩式影棚", "url": "style.png"}]
        if kind == "look_set":
            return [{"asset_id": "look_set_korean_studio_satin", "name": "缎面套系", "description": "新娘缎面婚纱与低盘发；新郎黑色西装与利落短发。", "url": "look.png"}]
        raise AssertionError(kind)

    monkeypatch.setattr(node, "search_assets", fake_search)
    first = style(state())
    assert first["questions"][0]["options"] == [{"value": "korean_studio", "label": "韩式影棚", "image": "style.png"}]
    second = style(state(answers=[answer("q_style", "korean_studio")]))
    assert second["questions"][0]["question_id"] == "q_look_set"
    assert second["questions"][0]["options"][0]["value"] == "look_set_korean_studio_satin"
    final = style(state(answers=[answer("q_style", "korean_studio"), answer("q_look_set", "look_set_korean_studio_satin")]))
    assert final["look"]["references"] == [{"url": "look.png", "role": "outfit"}, {"url": "style.png", "role": "style"}]
    assert "新娘缎面婚纱" in final["look"]["text"]


def test_look_set_asset_error_falls_back(monkeypatch):
    def broken_search(kind, tags=None):
        if kind == "style":
            return [{"asset_id": "style_korean_studio", "name": "韩式影棚", "url": "style.png"}]
        raise RuntimeError("look_set unsupported")

    monkeypatch.setattr(node, "search_assets", broken_search)
    update = style(state(answers=[answer("q_style", "korean_studio")]))
    options = update["questions"][0]["options"]
    assert 2 <= len(options) <= 3
    assert all(item["image"] is None for item in options)
    assert "新娘" in update["look"]["text"] and "新郎" in update["look"]["text"]


def test_no_placeholders_in_style_templates():
    for style_id in node.available_styles():
        description = "想要韩式影棚风" if style_id == "korean_studio" else f"想要{style_id}风"
        update = style(state(description))
        assert "{" not in update["look"]["text"] and "}" not in update["look"]["text"]
