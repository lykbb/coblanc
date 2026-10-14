from types import SimpleNamespace

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review import face_compare, model_calls
from app.modules.review.face_compare import compare_batch_with_extractor
from app.modules.review.model_calls import CallStats, structured_call
from app.modules.review.smoke import run_smoke
from app.contracts import RetouchPlan


def test_mock_smoke_never_calls_model(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("mock 不能访问模型")

    monkeypatch.setattr(model_calls, "get_llm", forbidden)
    report = run_smoke()
    assert len(report["visual_findings"]) == 4
    assert report["retouch_plan"]["target"] == "generate"
    assert report["timing"]["model_invocations"] == 0
    assert report["timing"]["simulated_invocations"] == 2
    assert report["metadata"]["prompt_version"]
    assert "base64" not in str(report)


def test_live_smoke_checks_config_before_call(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(ModuleError):
        run_smoke("live")


@pytest.mark.parametrize("stage,key", [("vision", "visual_findings"), ("retouch", "retouch_plan")])
def test_smoke_can_run_single_stage(stage, key):
    report = run_smoke(stage=stage)
    assert key in report
    assert report["timing"]["simulated_invocations"] == 1


def test_stats_are_per_run_and_count_failed_invoke(monkeypatch):
    class Model:
        max_retries = 1

        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            raise TimeoutError("private payload")

    monkeypatch.setattr(model_calls, "get_llm", lambda _: Model())
    stats = CallStats()
    with pytest.raises(ModuleError):
        structured_call("agent", RetouchPlan, [], stats)
    assert stats.summary()["model_invocations"] == 1
    assert stats.summary()["request_budget_upper_bound"] == 2
    assert stats.calls[0]["success"] is False
    assert CallStats().summary()["model_invocations"] == 0
    assert "private" not in str(stats)


def test_face_batch_extracts_source_once_and_passes_timeout():
    calls = []

    class Extractor:
        def extract(self, image, *, timeout_seconds):
            assert timeout_seconds > 0
            calls.append(image)
            return [[1, 0], [0, 1]] if image == b"source" else [[0, 1], [1, 0]]

    result = compare_batch_with_extractor(b"source", [("one", b"candidate"), ("two", b"candidate")], Extractor())
    assert result == {"one": [1.0, 1.0], "two": [1.0, 1.0]}
    assert calls == [b"source", b"candidate", b"candidate"]


def test_face_timeout_does_not_return_scores(monkeypatch):
    times = iter([0, 0, settings.image_timeout_seconds + 1])
    monkeypatch.setattr(face_compare, "monotonic", lambda: next(times))
    extractor = SimpleNamespace(extract=lambda *args, **kwargs: [[1, 0], [0, 1]])
    with pytest.raises(ModuleError, match="超时"):
        compare_batch_with_extractor(b"source", [("one", b"candidate")], extractor)


def test_face_budget_checked_before_extraction(monkeypatch):
    monkeypatch.setattr(settings, "max_agent_steps", 1)
    def forbidden(*args, **kwargs):
        pytest.fail("超过预算不应提取")
    with pytest.raises(ModuleError):
        compare_batch_with_extractor(b"source", [("one", b"candidate")], SimpleNamespace(extract=forbidden))
