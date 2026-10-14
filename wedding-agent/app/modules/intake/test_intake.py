from app.common.config import settings
from app.modules.intake import compose, intake, reveal


def test_first_round_asks_questions(load_state):
    update = intake(load_state("new_task"))
    assert [q["question_id"] for q in update["questions"]] == ["q_style", "q_height"]
    assert set(update["brief"]["missing"]) == {"style", "heights_cm"}


def test_answers_complete_the_brief(load_state):
    state = load_state("new_task")
    state["answers"] = [
        {"question_id": "q_style", "value": "keep_original", "round": 1},
        {"question_id": "q_height", "value": "175 / 162", "round": 1},
    ]
    update = intake(state)
    assert update["questions"] == []
    assert update["brief"]["style"] == "keep_original"
    assert update["brief"]["background"] == "keep_original"
    assert update["brief"]["heights_cm"] == [175, 162]
    assert update["brief"]["missing"] == []


def test_ignores_answers_given_to_other_agents(load_state):
    state = load_state("new_task")
    state["answers"] = [{"question_id": "q_makeup", "value": "retro", "asker": "styling", "round": 1}]
    assert [q["question_id"] for q in intake(state)["questions"]] == ["q_style", "q_height"]


def test_skipped_answers_use_recommended(load_state):
    state = load_state("new_task")
    state["answers"] = [
        {"question_id": "q_style", "skipped": True, "round": 1},
        {"question_id": "q_height", "skipped": True, "round": 1},
    ]
    brief = intake(state)["brief"]
    assert brief["style"] == "korean_studio"
    assert brief["heights_cm"] == []


def test_compose_merges_look_and_shot(load_state):
    update = compose(load_state("after_generation"))
    assert update["prompt"].startswith("保持图中两人")
    assert "韩式婚纱照造型" in update["prompt"]
    assert "简洁的室内影棚" in update["prompt"]
    assert update["references"] == []


def test_compose_puts_pose_first_and_caps_references(load_state, monkeypatch):
    monkeypatch.setattr(settings, "max_reference_images", 2)
    state = load_state("after_generation")
    state["look"]["references"] = [{"url": "u/outfit", "role": "outfit"}, {"url": "u/makeup", "role": "makeup"}]
    state["shot"]["references"] = [{"url": "u/pose", "role": "pose"}]
    references = compose(state)["references"]
    assert [ref["role"] for ref in references] == ["pose", "outfit"]


def test_compose_applies_prompt_patch(load_state):
    state = load_state("after_generation")
    state["retouch_plan"] = {"target": "prompt", "patch": "两人靠得更近", "image_id": None}
    assert "两人靠得更近" in compose(state)["prompt"]


def test_reveal_message_is_short(load_state):
    message = reveal(load_state("after_generation"))["message"]
    assert 0 < len(message) <= 50


def test_grouped_photos_ask_for_style_materials_and_consent(load_state):
    state = load_state("new_task")
    state["groom_photo_urls"] = [state["photo_urls"][0]]
    state["bride_photo_urls"] = [state["photo_urls"][0]]
    update = intake(state)
    assert [q["question_id"] for q in update["questions"]] == ["q_style", "q_materials", "q_consent"]
    assert update["brief"]["missing"] == ["style", "materials"]


def test_grouped_answers_store_consent_and_materials(load_state):
    state = load_state("new_task")
    state["groom_photo_urls"] = [state["photo_urls"][0]]
    state["bride_photo_urls"] = [state["photo_urls"][0]]
    state["answers"] = [
        {"question_id": "q_style", "value": "french_editorial", "asker": "intake", "round": 1},
        {"question_id": "q_materials", "value": ["invitation", "moments"], "asker": "intake", "round": 1},
        {"question_id": "q_consent", "value": "standard", "asker": "intake", "round": 1},
    ]
    update = intake(state)
    assert update["questions"] == []
    assert update["brief"]["style"] == "french_editorial"
    assert update["brief"]["materials"] == ["invitation", "moments"]
    assert update["consent"]["confirmed"] is True


def test_grouped_skipped_style_uses_recommended(load_state):
    state = load_state("new_task")
    state["groom_photo_urls"] = [state["photo_urls"][0]]
    state["bride_photo_urls"] = [state["photo_urls"][0]]
    state["answers"] = [
        {"question_id": "q_style", "skipped": True, "asker": "intake", "round": 1},
        {"question_id": "q_materials", "skipped": True, "asker": "intake", "round": 1},
        {"question_id": "q_consent", "value": "standard", "asker": "intake", "round": 1},
    ]
    update = intake(state)
    assert update["brief"]["style"] == "korean_studio"
    assert update["brief"]["missing"] == []


def test_grouped_custom_consent_has_a_conservative_completion_path(load_state):
    state = load_state("new_task")
    state["groom_photo_urls"] = [state["photo_urls"][0]]
    state["bride_photo_urls"] = [state["photo_urls"][0]]
    state["answers"] = [
        {"question_id": "q_style", "value": "korean_studio", "asker": "intake", "round": 1},
        {"question_id": "q_materials", "value": ["invitation"], "asker": "intake", "round": 1},
        {"question_id": "q_consent", "value": "custom", "asker": "intake", "round": 1},
    ]
    update = intake(state)
    assert update["consent"]["confirmed"] is True
    assert update["consent"]["delete_original"] is False
