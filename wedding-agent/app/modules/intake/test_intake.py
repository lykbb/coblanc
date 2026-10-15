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
    opening = node.binding_sentence(update["identity"], update["references"]) + node.load_section(node.IMAGE_PROMPT, "identity")
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
    node.load_section(node.PHOTO_SORT, "check").format(label="照片", expected="1 或 2")


def test_binding_sentence_order_and_merge():
    identity = [{"url": "c", "role": "couple"},
                {"url": "g1", "role": "groom"}, {"url": "g2", "role": "groom"}, {"url": "b1", "role": "bride"}]
    refs = [{"url": "p", "role": "pose"}, {"url": "o", "role": "outfit"}]
    text = node.binding_sentence(identity, refs)
    assert text.startswith("图1是新郎新娘的合照，男性为新郎，女性为新娘；图2、图3是新郎本人；图4是新娘本人；图5只参考两人的姿势和站位；图6只参考服装款式。")
    assert text.endswith("不要用他们的脸、发型和身材。")
    assert "{" not in text


def test_binding_without_couple_or_refs():
    identity = [{"url": "g", "role": "groom"}, {"url": "b", "role": "bride"}, {"url": "b2", "role": "bride"}]
    assert node.binding_sentence(identity, []) == "图1是新郎本人；图2、图3是新娘本人。"
    couples = [{"url": "c1", "role": "couple"}, {"url": "c2", "role": "couple"}]
    assert node.binding_sentence(couples, []) == "图1、图2是新郎新娘的合照，男性为新郎，女性为新娘。"


def test_identity_fallback_and_send_cap():
    state = {"groom_photo_urls": ["g1", "g2", "g3"], "bride_photo_urls": ["b1"]}
    assert [i["url"] for i in node._identity(state)] == ["g1", "g2", "b1"]
    full = node._identity({"photo_urls": [f"p{i}" for i in range(10)]})
    assert len(full) == 10 and all(i["role"] == "couple" for i in full)
    assert node._fit_references([{"url": "r", "role": "pose"}], full) == []

def test_mixed_couple_plus_solos_pass(monkeypatch):
    """1 张合照 + 男女单人照：不应要求补传，身份照合照在前。"""
    state = {
        "task_id": "t", "photo_urls": ["us.jpg", "man.jpg", "woman.jpg"],
        "description": "", "answers": [], "question_rounds": {"intake": 0},
        "consent": node.DEFAULT_CONSENT,
    }
    calls = []
    results = [
        {"index": 1, "people_count": 2, "clear": True, "front_facing": True, "unobstructed": True, "tag": "couple", "reason": ""},
        {"index": 2, "people_count": 1, "clear": True, "front_facing": True, "unobstructed": True, "tag": "groom", "reason": ""},
        {"index": 3, "people_count": 1, "clear": True, "front_facing": True, "unobstructed": True, "tag": "bride", "reason": ""},
    ]
    _real_llm(monkeypatch, results, calls)
    update = intake(state)
    assert not any(q.get("type") == "upload" for q in update.get("questions") or [])
    assert update.get("identity") == [
        {"url": "us.jpg", "role": "couple"},
        {"url": "man.jpg", "role": "groom"},
        {"url": "woman.jpg", "role": "bride"},
    ]
    node._cached_photo_check.cache_clear()


def test_mixed_upload_still_rejects_three_people(monkeypatch):
    state = {
        "task_id": "t", "photo_urls": ["crowd.jpg", "crowd2.jpg"],
        "description": "", "answers": [], "question_rounds": {"intake": 0},
        "consent": node.DEFAULT_CONSENT,
    }
    calls = []
    crowd = {"people_count": 3, "clear": True, "front_facing": True, "unobstructed": True, "tag": "unknown", "reason": "画面里有 3 个人"}
    _real_llm(monkeypatch, [{"index": 1, **crowd}, {"index": 2, **crowd}], calls)
    update = intake(state)
    assert update["questions"][0]["type"] == "upload"
    assert "q_photos" == update["questions"][0]["question_id"]
    node._cached_photo_check.cache_clear()


def _solo(i, tag, front=True, clear=True):
    return {"index": i, "people_count": 1, "clear": clear, "front_facing": front, "unobstructed": True, "tag": tag,
            "reason": "" if front and clear else "只有1个人，需要2人合照"}


def test_mixed_solo_photos_with_side_faces_pass(monkeypatch):
    node._cached_photo_check.cache_clear()
    urls = [f"p{i}" for i in range(1, 11)]
    results = [_solo(i, "groom" if i <= 5 else "bride", front=i not in (3, 4)) for i in range(1, 11)]
    results[0] = {**results[0], "people_count": 2, "tag": "couple"}
    _real_llm(monkeypatch, results, [])
    state = {"photo_urls": urls}
    assert node._photo_failures(state) == []
    identity = node._identity_from_mixed_checks(state)
    assert {p["role"] for p in identity} == {"couple", "groom", "bride"}
    assert identity[0]["url"] != "p3"
    node._cached_photo_check.cache_clear()


def test_mixed_missing_bride_never_says_couple(monkeypatch):
    node._cached_photo_check.cache_clear()
    results = [_solo(1, "groom"), _solo(2, "bride", clear=False)]
    _real_llm(monkeypatch, results, [])
    failures = node._photo_failures({"photo_urls": ["a", "b"]})
    assert failures and all("2人" not in f["reason"] and "合照第" not in f["reason"] for f in failures)
    node._cached_photo_check.cache_clear()


def _couple(i, pet=""):
    return {"index": i, "people_count": 2, "clear": True, "front_facing": True, "unobstructed": True,
            "tag": "couple", "has_pet": bool(pet), "pet_kind": pet, "reason": ""}


def _pet_only(i, kind="小狗"):
    return {"index": i, "people_count": 0, "clear": True, "front_facing": False, "unobstructed": True,
            "tag": "pet", "has_pet": True, "pet_kind": kind, "reason": ""}


def _check(monkeypatch, results, description=""):
    node._cached_photo_check.cache_clear()
    _real_llm(monkeypatch, results, [])
    state = {"photo_urls": [f"u{i}" for i in range(len(results))], "description": description, "answers": []}
    try:
        return node._photo_failures(state), state
    finally:
        pass


def test_rule_all_solo_asks_for_couple(monkeypatch):
    failures, _ = _check(monkeypatch, [_solo(1, "groom"), _solo(2, "bride")])
    assert [f["reason"] for f in failures] == ["还需要至少 1 张你们俩的合照"]
    node._cached_photo_check.cache_clear()


def test_rule_one_couple_plus_solos_ok(monkeypatch):
    failures, state = _check(monkeypatch, [_couple(1), _solo(2, "groom"), _solo(3, "bride", front=False)])
    assert failures == []
    assert node._identity_from_mixed_checks(state)[0]["role"] == "couple"
    node._cached_photo_check.cache_clear()


def test_rule_pet_without_consent_rejected(monkeypatch):
    failures, _ = _check(monkeypatch, [_couple(1), _pet_only(2), _couple(3, "小猫")])
    reasons = {f["index"]: f["reason"] for f in failures}
    assert reasons == {2: "这张是小狗，如需一起入镜请告诉我", 3: "这张里有小猫，如需一起入镜请告诉我"}
    node._cached_photo_check.cache_clear()


def test_rule_pet_with_consent_ok_and_recorded(monkeypatch):
    failures, state = _check(monkeypatch, [_couple(1, "小狗"), _solo(2, "groom")], description="想带我们家小狗一起拍")
    assert failures == []
    assert "小狗" in node._pet_keep_feature(state)
    node._cached_photo_check.cache_clear()


def test_rule_photo_count_bounds():
    for n in (1, 11):
        with pytest.raises(ModuleError):
            node._validate_photo_shape({"photo_urls": [f"u{i}" for i in range(n)]})
    node._validate_photo_shape({"photo_urls": ["a", "b"]})
