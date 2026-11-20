import pytest
from llm.client import KeyRotator, provider_for_url

OPENROUTER = "https://openrouter.ai/api/v1"


def test_rotation(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEYS", "a,b")
    rotator = KeyRotator(provider_for_url("models.json", OPENROUTER))
    assert rotator.current() == "a"
    assert rotator.next() == "b"
    assert rotator.next() == "a"


def test_no_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError):
        KeyRotator(provider_for_url("models.json", OPENROUTER))


def test_single_standard_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "solo")
    assert KeyRotator(provider_for_url("models.json", OPENROUTER)).current() == "solo"
