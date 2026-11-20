import pytest
from llm.client import LLMClient, provider_for_url


def test_provider_for_url_ignores_trailing_slash():
    assert provider_for_url("models.json", "https://openrouter.ai/api/v1/").name == "OpenRouter"


def test_unknown_provider_url():
    with pytest.raises(ValueError):
        provider_for_url("models.json", "https://not-a-provider.example/v1")


def test_model_settings_come_from_models_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "k")
    url = "https://generativelanguage.googleapis.com/v1beta/openai"
    listed = LLMClient.from_config("models.json", url, "gemini-2.5-flash")
    unlisted = LLMClient.from_config("models.json", url, "unlisted-model")
    assert listed.model.max_tokens_per_call == 2048
    assert unlisted.model.max_tokens_per_call == 400
