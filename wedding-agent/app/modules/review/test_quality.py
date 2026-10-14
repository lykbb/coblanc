import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review import check
from app.modules.review.model_calls import structured_call
from app.modules.review import model_calls
from app.modules.review.quality import passes
from app.contracts import RetouchPlan


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1, True, "0.5"])
def test_invalid_face_threshold_stops_before_check(load_state, monkeypatch, value):
    monkeypatch.setattr(settings, "face_sim_threshold", value)
    with pytest.raises(ModuleError, match="阈值"):
        check(load_state("after_generation"))


@pytest.mark.parametrize("field,value", [("max_agent_steps", True), ("max_agent_steps", float("nan")), ("llm_timeout_seconds", float("nan")), ("llm_timeout_seconds", -1), ("llm_timeout_seconds", True)])
def test_bad_budget_configuration_never_calls_model(monkeypatch, field, value):
    monkeypatch.setattr(settings, field, value)
    monkeypatch.setattr(model_calls, "get_llm", lambda *_: pytest.fail("无效配置不应访问模型"))
    with pytest.raises(ModuleError):
        structured_call("agent", RetouchPlan, [])


def test_runtime_and_threshold_rescore_share_gate():
    score = {"face_sim": [0.8, 0.8], "body_ok": True, "hands_ok": True, "issues": ["原图人物 A 与候选人脸相似度不足"]}
    assert not passes(score, 0.7)
    assert passes(score, 0.7, rescore=True)
    score["issues"].append("乱码文字")
    assert not passes(score, 0.7, rescore=True)


@pytest.mark.parametrize("field,value", [("image_timeout_seconds", float("nan")), ("image_timeout_seconds", True), ("max_agent_steps", float("nan")), ("candidates_per_round", True)])
def test_bad_face_adapter_configuration_never_extracts(monkeypatch, field, value):
    from types import SimpleNamespace
    from app.modules.review.face_compare import compare_batch_with_extractor
    monkeypatch.setattr(settings, field, value)
    extractor = SimpleNamespace(extract=lambda *args, **kwargs: pytest.fail("无效配置不能提取人脸"))
    with pytest.raises(ModuleError):
        compare_batch_with_extractor(b"source", [("img_1", b"candidate")], extractor)


@pytest.mark.parametrize("retries", [None, True, -1])
def test_invalid_sdk_retry_configuration_never_invokes(monkeypatch, retries):
    from types import SimpleNamespace
    monkeypatch.setattr(model_calls, "get_llm", lambda _: SimpleNamespace(max_retries=retries))
    with pytest.raises(ModuleError, match="重试配置"):
        structured_call("agent", RetouchPlan, [])
