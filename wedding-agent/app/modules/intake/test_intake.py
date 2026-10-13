from app.modules.intake import intake, reveal


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


def test_skipped_answers_use_recommended(load_state):
    state = load_state("new_task")
    state["answers"] = [
        {"question_id": "q_style", "skipped": True, "round": 1},
        {"question_id": "q_height", "skipped": True, "round": 1},
    ]
    brief = intake(state)["brief"]
    assert brief["style"] == "korean_studio"
    assert brief["heights_cm"] == []


def test_reveal_message_is_short(load_state):
    message = reveal(load_state("after_generation"))["message"]
    assert 0 < len(message) <= 50
