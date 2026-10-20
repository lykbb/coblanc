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


def test_clear_description_skips_style_and_asks_makeup_and_outfit():
    update = style(state("想要韩式影棚风"))
    questions = update["questions"]
    assert [q["question_id"] for q in questions] == ["q_makeup", "q_outfit"]
    assert update["look"]["style"] == "korean_studio"
    makeup, outfit = questions
    assert makeup["recommended"] == "makeup_korean_dewy" and len(makeup["options"]) == 3
    assert all(set(o) == {"value", "label", "image", "description"} for q in questions for o in q["options"])
    assert makeup["options"][0]["description"].startswith("新娘") and "新郎" in makeup["options"][0]["description"]
    assert outfit["options"][0]["description"].startswith("婚纱：") and "西装：" in outfit["options"][0]["description"]


def test_answers_stop_questions_and_shape_both_people():
    answers = [answer("q_style", "retro"), answer("q_makeup", "makeup_noble"), answer("q_outfit", "outfit_retro_classic")]
    update = style(state(answers=answers))
    assert "questions" not in update
    text = update["look"]["text"]
    assert update["look"]["style"] == "retro"
    assert "贵气千金" in text and "经典礼服" in text and "黑色礼服配白色胸花" in text


def test_old_look_set_answer_still_works():
    answers = [answer("q_style", "retro"), answer("q_look_set", "look_set_retro_wave")]
    update = style(state(answers=answers))
    assert "questions" not in update
    assert "复古剪裁婚纱" in update["look"]["text"]


def test_skipping_style_still_moves_to_second_round():
    update = style(state(answers=[answer("q_style", skipped=True)]))
    assert [q["question_id"] for q in update["questions"]] == ["q_makeup", "q_outfit"]


def test_skipping_makeup_and_outfit_uses_recommended():
    answers = [answer("q_style", "forest"), answer("q_makeup", skipped=True), answer("q_outfit", skipped=True)]
    picked = node.selections(state(answers=answers))
    assert picked["makeup"]["value"] == node.choices.STYLE_MAKEUPS["forest"][0]
    assert picked["outfit"]["value"] == picked["outfit_options"][0]["value"]


def test_retouch_and_candidates_never_ask():
    for extra in (
        {"candidates": [{"image_id": "x", "url": "u", "seed": 1}]},
        {"retouch_plan": {"target": "look", "patch": "改为低盘发", "image_id": None}},
    ):
        update = style(state(**extra))
        assert "questions" not in update
        if "retouch_plan" in extra:
            assert "改为低盘发" in update["look"]["text"]


def test_makeup_data_is_text_only_and_skips_held_cases():
    for makeup_id in node.choices.MAKEUPS:
        detail = node.choices.makeup_detail(makeup_id)
        assert detail["bride"] and detail["groom"]
        assert not any("http" in note or ".jpg" in note for note in detail["bride_notes"] + detail["groom_notes"])


def test_asset_style_and_outfit_options_and_references(monkeypatch):
    def fake_search(kind, tags=None):
        if kind == "style":
            return [{"asset_id": "style_korean_studio", "name": "韩式影棚", "url": "style.png"}]
        if kind == "outfit":
            return [{"asset_id": "outfit_satin_set", "name": "缎面套装", "description": "缎面婚纱与黑色西装", "url": "outfit.png"}]
        raise AssertionError(kind)

    monkeypatch.setattr(node, "search_assets", fake_search)
    first = style(state())
    assert next(o for o in first["questions"][0]["options"] if o["value"] == "korean_studio") == {"value": "korean_studio", "label": "韩式影棚", "image": "style.png",
                                                   "description": node.choices.STYLES["korean_studio"][1]}
    second = style(state(answers=[answer("q_style", "korean_studio")]))
    outfit = next(q for q in second["questions"] if q["question_id"] == "q_outfit")
    assert outfit["options"][0]["value"] == "outfit_satin_set" and outfit["options"][0]["image"] == "outfit.png"
    final = style(state(answers=[answer("q_style", "korean_studio"), answer("q_makeup", "makeup_soft_matte"),
                                 answer("q_outfit", "outfit_satin_set")]))
    assert final["look"]["references"] == [{"url": "outfit.png", "role": "outfit"}, {"url": "style.png", "role": "style"}]
    assert "缎面婚纱与黑色西装" in final["look"]["text"]


def test_asset_error_falls_back_to_text_outfits(monkeypatch):
    def broken_search(kind, tags=None):
        raise RuntimeError("asset library down")

    monkeypatch.setattr(node, "search_assets", broken_search)
    update = style(state(answers=[answer("q_style", "korean_studio")]))
    options = next(q for q in update["questions"] if q["question_id"] == "q_outfit")["options"]
    assert 2 <= len(options) <= 3
    assert all(item["image"] is None for item in options)
    assert "新娘" in update["look"]["text"] and "新郎" in update["look"]["text"]


def test_no_placeholders_in_style_templates():
    for style_id in node.available_styles():
        description = "想要韩式影棚风" if style_id == "korean_studio" else f"想要{style_id}风"
        update = style(state(description))
        assert "{" not in update["look"]["text"] and "}" not in update["look"]["text"]


def test_plan_choices_follow_look_and_answers():
    from app.api import _choices

    values = {"look": {"style": "forest", "text": "x"}, "shot": {"text": "y"},
              "answers": [{"asker": "styling", "question_id": "q_makeup", "value": "makeup_mood"},
                          {"asker": "framing", "question_id": "q_scene", "value": "lawn"}]}
    picked = _choices(values)
    assert picked["style"]["label"] == node.choices.STYLES["forest"][0]
    assert picked["makeup"]["label"] == "氛围感" and picked["scene"]["label"] == "草坪"
    assert picked["outfit"]["bride"] and picked["outfit"]["groom"]
