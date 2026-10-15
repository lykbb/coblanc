from app.common import llm
from app.common.config import settings


def test_chat_preferred_when_key_present(monkeypatch):
    monkeypatch.setattr(settings, "chat_api_key", "k")
    monkeypatch.setattr(settings, "chat_model", "deepseek-flash")
    monkeypatch.setattr(settings, "chat_model_vision", "vision-x")
    assert llm.llm_config("agent")["provider"] == "chat"
    assert llm.model_name("agent") == "deepseek-flash"
    assert llm.model_name("vision") == "vision-x"
    assert llm.get_llm("cheap").openai_api_base == settings.chat_base_url


def test_falls_back_to_ark_without_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert llm.llm_config("agent")["provider"] == "ark"
    assert not llm.llm_ready("agent")


def test_legacy_deepseek_env_names(monkeypatch):
    from app.common import config
    monkeypatch.delenv("CHAT_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "old")
    monkeypatch.setenv("CHAT_MODEL", "new-model")
    assert config._chat("API_KEY") == "old"
    assert config._chat("MODEL", "x") == "new-model"
    monkeypatch.setenv("CHAT_API_KEY", "new")
    assert config._chat("API_KEY") == "new"
