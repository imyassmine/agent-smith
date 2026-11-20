import pytest
from llm.config import pick_model


def test_default_model():
    provider, model = pick_model("models.json")
    assert provider.name == "OpenRouter"
    assert model.name == "qwen/qwen3-coder:free"


def test_unknown_model():
    with pytest.raises(ValueError):
        pick_model("models.json", "not-a-model")
