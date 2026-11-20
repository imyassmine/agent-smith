import pytest
from llm.config import pick_model
from llm.keys import KeyRotator


def test_rotation(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEYS", "a,b")
    provider, _ = pick_model("models.json")
    rotator = KeyRotator(provider)
    assert rotator.current() == "a"
    assert rotator.next() == "b"
    assert rotator.next() == "a"


def test_no_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    provider, _ = pick_model("models.json")
    with pytest.raises(ValueError):
        KeyRotator(provider)
