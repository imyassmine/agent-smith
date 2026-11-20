import time
from dataclasses import dataclass
from pathlib import Path
import httpx
from models import ModelConfig, ModelsConfig, ProviderConfig


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    request_time_ms: float
    model_name: str
    retries: int = 0


def provider_for_url(path: str | Path, url: str) -> ProviderConfig:
    config = ModelsConfig.from_json_file(path)
    for provider in config.providers.values():
        if provider.base_url.rstrip("/") == url.rstrip("/"):
            return provider
    raise ValueError(f"no provider with base_url '{url}' in {path}")


def pick_model(path: str, model_name: str | None = None) -> tuple[ProviderConfig, ModelConfig]:
    config = ModelsConfig.from_json_file(path)
    name = model_name or config.default_model
    for provider_name in [config.default_provider, *config.fallback_order]:
        provider = config.providers[provider_name]
        model = provider.get_model(name)
        if model is not None:
            return provider, model
    raise ValueError(f"model '{name}' not found in {path}")


class KeyRotator:
    def __init__(self, provider: ProviderConfig) -> None:
        self.keys = provider.load_api_keys()
        if not self.keys:
            raise ValueError(f"no keys found in {provider.api_key_env}")
        self.index = 0

    def current(self) -> str:
        return self.keys[self.index]

    def next(self) -> str:
        self.index = (self.index + 1) % len(self.keys)
        return self.current()


class LLMClient:
    """Calls an OpenAI-compatible /chat/completions API, with retries and key rotation."""

    def __init__(self, provider: ProviderConfig, model: ModelConfig) -> None:
        self.provider, self.model = provider, model
        self.keys = KeyRotator(provider)

    @classmethod
    def from_config(cls, path: str | Path, provider_url: str, model_name: str) -> "LLMClient":
        provider = provider_for_url(path, provider_url)
        # models not listed in models.json still work, with the default settings
        model = provider.get_model(model_name) or ModelConfig(name=model_name)
        return cls(provider, model)

    def complete(self, messages: list[dict], max_tokens: int, timeout: float) -> LLMResponse:
        last_error = None
        for retry in range(self.provider.max_retries + 1):
            if retry:
                time.sleep(2 ** (retry - 1))
            try:
                response = self._request(messages, max_tokens, timeout)
                response.retries = retry
                return response
            except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError) as error:
                last_error = error
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
                    self.keys.next()  # rate limited: try the next key
        raise LLMError(f"LLM call failed after {self.provider.max_retries} retries: {last_error}")

    def _request(self, messages: list[dict], max_tokens: int, timeout: float) -> LLMResponse:
        start = time.perf_counter()
        response = httpx.post(
            f"{self.provider.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.keys.current()}"},
            json={
                "model": self.model.name,
                "messages": messages,
                "stop": self.model.stop,
                "max_tokens": max_tokens,
                "temperature": self.model.temperature,
                "reasoning_effort": "low",
            },
            timeout=min(timeout, self.provider.request_timeout_seconds),
        )
        request_time_ms = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=data["usage"]["prompt_tokens"],
            output_tokens=data["usage"]["completion_tokens"],
            request_time_ms=request_time_ms,
            model_name=data["model"],
        )
