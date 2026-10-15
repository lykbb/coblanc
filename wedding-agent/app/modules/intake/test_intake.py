import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.intake import compose, intake
from app.modules.intake import node


def test_first_round_asks_only_intake_facts(load_state):
    update = intake(load_state("new_task"))
    assert [q["question_id"] for q in update["questions"]] == [
        "q_consent", "q_height", "q_materials", "q_invitation"
    ]
    assert all(q["question_id"] not in {"q_style", "q_makeup", "q_scene", "q_lighting", "q_pose"} for q in update["questions"])
    assert len(update["questions"]) <= 4


def test_grouped_and_legacy_use_same_questions(load_state):
    legacy = load_state("new_task")
    grouped = load_state("new_task")
    grouped["groom_photo_urls"] = ["g1"]
    grouped["bride_photo_urls"] = ["b1"]
    assert [q["question_id"] for q in intake(legacy)["questions"]] == [q["question_id"] for q in intake(grouped)["questions"]]


def test_answers_create_only_supported_brief_fields(load_state):
    state = load_state("new_task")
    state["answers"] = [
        {"question_id": "q_consent", "value": "keep_photos", "asker": "intake", "round": 1},
        {"question_id": "q_height", "value": "175 / 162", "asker": "intake", "round": 1},
        {"question_id": "q_materials", "value": ["invitation", "led_screen"], "asker": "intake", "round": 1},
        {"question_id": "q_invitation", "value": "张三 & 李四，2026-12-20，杭州", "asker": "intake", "round": 1},
    ]
    update = intake(state)
    assert update["questions"] == []
    assert update["consent"]["delete_original"] is False
    assert update["brief"]["heights_cm"] == [175, 162]
    assert update["brief"]["materials"] == ["invitation", "led_screen"]
    assert update["brief"]["invitation"] == {"names": "张三 & 李四", "date": "2026-12-20", "place": "杭州"}
    for key in ("style", "background", "makeup", "outfit_bride", "outfit_groom", "expression", "pose"):
        assert update["brief"][key] == "undecided"


def test_empty_answers_default_unanswered_consent(load_state, monkeypatch):
    state = load_state("new_task")
    monkeypatch.setattr(settings, "max_question_rounds", 1)
    state["question_rounds"] = {"intake": 1}
    update = intake(state)
    assert update["questions"] == []
    assert update["consent"] == node.DEFAULT_CONSENT


def test_description_skips_facts(load_state):
    state = load_state("new_task")
    state["description"] = "两人身高 175 / 162，需要请柬、迎宾海报和婚礼大屏；张三 & 李四，2026-12-20，杭州"
    questions = intake(state)["questions"]
    assert [q["question_id"] for q in questions] == ["q_consent"]


def test_compose_prefix_and_single_patch(load_state):
    state = load_state("after_generation")
    state["look"] = {"text": "新娘和新郎各自妆造清晰", "style": "korean_studio", "references": []}
    state["shot"] = {"text": "摄影师构图清晰", "pose": "pose_a", "references": []}
    state["retouch_plan"] = {"target": "prompt", "patch": "两人靠近", "image_id": None}
    update = compose(state)
    opening = node.load_section(node.IMAGE_PROMPT, "identity")
    assert update["prompt"].startswith(opening)
    assert update["prompt"].count("两人靠近") == 1


def _real_llm(monkeypatch, results, calls):
    class Chain:
        def __init__(self, kind): self.kind = kind
        def with_structured_output(self, _schema): return self
        def invoke(self, _messages):
            if self.kind == "vision":
                calls.append(1)
                return {"results": results}
            return {"heights_cm": [], "body_types": [], "keep_features": [], "beautify": "none", "materials": ["invitation", "welcome_poster", "led_screen"], "invitation": {}}
    monkeypatch.setattr(settings, "real_modules", ["intake"])
    monkeypatch.setattr(node, "_get_llm", lambda kind: Chain(kind))


def test_bad_photos_return_upload_and_replacement(monkeypatch):
    state = {
        "task_id": "t", "photo_urls": ["g1", "g2", "b1"],
        "groom_photo_urls": ["g1", "g2"], "bride_photo_urls": ["b1"],
        "description": "", "answers": [], "question_rounds": {"intake": 0},
        "consent": node.DEFAULT_CONSENT,
    }
    calls = []
    results = [
        {"index": 1, "people_count": 1, "clear": True, "front_facing": True, "unobstructed": True},
        {"index": 2, "people_count": 1, "clear": False, "front_facing": True, "unobstructed": True, "reason": "有遮挡"},
    ]
    _real_llm(monkeypatch, results, calls)
    # 真实模型返回相同结果给每组，故新娘先被判定不合格；只验证补传题契约。
    update = intake(state)
    assert update["questions"][0]["type"] == "upload"
    assert update["questions"][0]["allow_skip"] is False
    assert update["questions"][0]["question_id"] in {"q_groom_photos", "q_bride_photos"}
    node._cached_photo_check.cache_clear()


def test_photo_check_cache_is_group_scoped(monkeypatch):
    state = {
        "task_id": "t", "photo_urls": ["g1", "b1"],
        "groom_photo_urls": ["g1"], "bride_photo_urls": ["b1"],
        "description": "", "answers": [], "question_rounds": {"intake": 0},
        "consent": node.DEFAULT_CONSENT,
    }
    calls = []
    good = [{"index": 1, "people_count": 1, "clear": True, "front_facing": True, "unobstructed": True}]
    _real_llm(monkeypatch, good, calls)
    intake(state)
    intake(state)
    assert len(calls) == 2
    node._cached_photo_check.cache_clear()


def test_photo_invalid_after_max_rounds(monkeypatch):
    state = {
        "task_id": "t", "photo_urls": ["g1", "b1"],
        "groom_photo_urls": ["g1"], "bride_photo_urls": ["b1"],
        "description": "", "answers": [], "question_rounds": {"intake": settings.max_question_rounds},
        "consent": node.DEFAULT_CONSENT,
    }
    calls = []
    _real_llm(monkeypatch, [{"index": 1, "people_count": 0, "clear": False, "front_facing": False, "unobstructed": False, "reason": "模糊"}], calls)
    with pytest.raises(ModuleError, match="模糊"):
        intake(state)
    node._cached_photo_check.cache_clear()


def test_prompt_sections_load():
    for path, name in [(node.DIALOGUE, "brief"), (node.DIALOGUE, "reveal"), (node.PHOTO_SORT, "check"),
                       (node.IMAGE_PROMPT, "identity"), (node.IMAGE_PROMPT, "compose")]:
        assert node.load_section(path, name)
    node.load_section(node.PHOTO_SORT, "check").format(label="合照", expected=2)
