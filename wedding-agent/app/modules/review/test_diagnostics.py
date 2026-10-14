from copy import deepcopy
import stat

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review import diagnostics, model_calls
from app.modules.review.diagnostics import diagnose, readiness
from app.modules.review.live_batch import run_batch
from app.modules.review.reporting import save_report


@pytest.fixture
def entry(load_state):
    return {"sample_id": "anonymous_sample", "state": load_state("after_generation")}


def test_mock_diagnostic_uses_no_photos_or_paid_models(entry, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("mock 不应读取真实照片或调用模型")
    monkeypatch.setattr(diagnostics, "load_image", forbidden)
    monkeypatch.setattr(model_calls, "get_llm", forbidden)
    before = deepcopy(entry)
    result = diagnose(entry)
    assert result["result"]["passed"] is True
    assert result["source"] == "synthetic_fixture"
    assert result["timing"]["simulated_invocations"] == 1
    assert result["timing"]["model_invocations"] == 0
    assert result["timing"]["face_comparisons"] == 0
    assert result["timing"]["simulated_face_comparisons"] == 4
    assert result["started_at"] and result["finished_at"]
    assert "photo_urls" not in str(result) and "base64" not in str(result)
    assert entry == before


@pytest.mark.parametrize("stage,key", [("face", "face_scores"), ("vision", "visual_findings")])
def test_single_image_diagnostic(entry, stage, key):
    result = diagnose(entry, stage=stage, image_id="img_2")
    assert len(result[key]) == 1
    assert result[key][0]["image_id"] == "img_2"


def test_unknown_image_cannot_be_diagnosed(entry):
    with pytest.raises(ModuleError):
        diagnose(entry, image_id="old_image")


def test_live_needs_consent_before_reading_or_calling(entry, monkeypatch):
    monkeypatch.setattr(diagnostics, "load_image", lambda *_: pytest.fail("不能读图"))
    with pytest.raises(ModuleError, match="授权"):
        diagnose(entry, mode="live", stage="vision")


def test_live_requires_approved_service(entry):
    entry["consent"] = {"both_people_authorized": True, "evidence_reference": "private_ref", "approved_services": []}
    with pytest.raises(ModuleError, match="获准服务"):
        diagnose(entry, mode="live", stage="vision")


def test_live_face_reports_provider_not_connected(entry, monkeypatch):
    monkeypatch.setattr(settings, "real_modules", ["review"])
    entry["consent"] = {"both_people_authorized": True, "evidence_reference": "private_ref"}
    with pytest.raises(ModuleError, match="尚未接入"):
        diagnose(entry, mode="live", stage="face")


def test_mock_batch_runs_retouch_when_check_fails(entry, monkeypatch):
    monkeypatch.setattr(settings, "face_sim_threshold", 0.95)
    report = run_batch({"dataset_version": "synthetic_v1", "samples": [entry]})
    result = report["predictions"][0]
    assert result["result"]["passed"] is False
    assert result["retouch_plan"]["target"] == "generate"
    assert result["timing"]["simulated_invocations"] == 2
    assert result["timing"]["model_invocations"] == 0
    assert report["summary"] == {"samples": 1, "succeeded": 1, "failed": 0}


def test_batch_continues_after_bad_state(entry):
    report = run_batch({"dataset_version": "synthetic_v1", "samples": [{"sample_id": "bad", "state": {}}, entry]})
    assert report["summary"] == {"samples": 2, "succeeded": 1, "failed": 1}
    assert report["predictions"][0]["failed_stage"] == "preflight"


def test_duplicate_sample_ids_rejected_before_processing(entry):
    with pytest.raises(ModuleError, match="重复"):
        run_batch({"dataset_version": "synthetic_v1", "samples": [entry, entry]})


def test_save_report_is_private_and_never_overwrites(tmp_path):
    output = tmp_path / "report.json"
    save_report(output, {"mode": "mock"})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_text()
    with pytest.raises(ModuleError):
        save_report(output, {"mode": "changed"})
    assert output.read_text() == before


def test_report_rejects_nonfinite_values(tmp_path):
    output = tmp_path / "bad.json"
    with pytest.raises(ModuleError):
        save_report(output, {"score": float("nan")})
    assert not output.exists()


def test_readiness_does_not_expose_secrets(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "secret-value")
    monkeypatch.setattr(settings, "llm_model_vision", "configured")
    report = readiness()
    assert report["vision_configured"] is True
    assert "secret" not in str(report)


@pytest.mark.parametrize("fail", [False, True])
def test_live_vision_path_uses_asset_library_with_test_model(entry, monkeypatch, fail):
    monkeypatch.setattr(settings, "real_modules", ["review"])
    monkeypatch.setattr(settings, "llm_api_key", "do_not_echo")
    monkeypatch.setattr(settings, "llm_model_vision", "test_model")
    entry["consent"] = {"both_people_authorized": True, "evidence_reference": "test_only", "approved_services": [settings.llm_base_url]}
    calls = []

    class Model:
        max_retries = 0

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def invoke(self, messages):
            calls.append(messages)
            if fail:
                raise TimeoutError("do_not_echo")
            return self.schema.model_validate({"findings": [{"image_id": "img_1", "body_ok": True, "hands_ok": True, "subject_count_ok": True, "text_ok": True, "requirements_ok": True, "assessable": True, "issues": []}]})

    monkeypatch.setattr(model_calls, "get_llm", lambda _: Model())
    report = diagnose(entry, mode="live", stage="vision", image_id="img_1")
    assert len(calls) == 1
    assert report["source"] == "asset_library"
    assert report["timing"]["model_invocations"] == 1
    assert ("error" in report) is fail
    assert "do_not_echo" not in str(report)


def test_batch_live_preflight_does_not_pay_when_agent_missing(entry, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test_only")
    monkeypatch.setattr(settings, "llm_model_agent", "")
    monkeypatch.setattr(model_calls, "get_llm", lambda *_: pytest.fail("agent 未配置不能先消费视觉请求"))
    report = run_batch({"dataset_version": "test_v1", "samples": [entry]}, mode="live")
    assert report["summary"]["failed"] == 1
    assert report["predictions"][0]["failed_stage"] == "preflight"


def test_live_face_error_is_sanitized(entry, monkeypatch):
    monkeypatch.setattr(settings, "real_modules", ["review"])
    entry["consent"] = {"both_people_authorized": True, "evidence_reference": "test_only"}
    monkeypatch.setattr(diagnostics, "provider_metadata", lambda: {"connected": True})
    def broken(*args, **kwargs):
        raise TimeoutError("private photo address")
    monkeypatch.setattr(diagnostics, "compare_faces", broken)
    report = diagnose(entry, mode="live", stage="face")
    assert report["error"]["code"] == "GENERATION_FAILED"
    assert "private photo address" not in str(report)
    assert report["timing"]["face_comparisons"] == 1


def test_explicit_live_cannot_bypass_global_fake(entry, monkeypatch):
    monkeypatch.setattr(settings, "fake", True)
    monkeypatch.setattr(settings, "real_modules", [])
    monkeypatch.setattr(settings, "llm_api_key", "test_only")
    monkeypatch.setattr(settings, "llm_model_vision", "test_only")
    entry["consent"] = {"both_people_authorized": True, "evidence_reference": "test_only", "approved_services": [settings.llm_base_url]}
    monkeypatch.setattr(model_calls, "get_llm", lambda *_: pytest.fail("全局 fake 不能付费调用"))
    with pytest.raises(ModuleError, match="fake 模式"):
        diagnose(entry, mode="live", stage="vision")
