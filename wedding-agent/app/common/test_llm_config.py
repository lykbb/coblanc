from app.common import llm
from app.common.config import settings


def test_deepseek_preferred_when_key_present(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-flash")
    monkeypatch.setattr(settings, "deepseek_model_vision", "vision-x")
    assert llm.llm_config("agent")["provider"] == "deepseek"
    assert llm.model_name("agent") == "deepseek-flash"
    assert llm.model_name("vision") == "vision-x"
    assert llm.get_llm("cheap").openai_api_base == settings.deepseek_base_url


def test_falls_back_to_ark_without_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert llm.llm_config("agent")["provider"] == "ark"
    assert not llm.llm_ready("agent")
