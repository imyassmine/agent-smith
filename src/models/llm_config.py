import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator


class ModelConfig(BaseModel):
    name: str
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens_per_call: int = Field(default=1024, gt=0)
    stop: List[str] = Field(default_factory=lambda: ["<end_code>", "Observation:"])


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key_env: str
    models: List[ModelConfig] = Field(default_factory=list)
    max_retries: int = Field(default=3, ge=0)
    request_timeout_seconds: float = Field(default=60.0, gt=0)

    def load_api_keys(self) -> List[str]:
        raw = os.environ.get(self.api_key_env, "")
        return [key.strip() for key in raw.split(",") if key.strip()]

    def get_model(self, name: str) -> Optional[ModelConfig]:
        return next((m for m in self.models if m.name == name), None)


class ModelsConfig(BaseModel):
    providers: Dict[str, ProviderConfig]
    default_provider: str
    default_model: str
    fallback_order: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self) -> "ModelsConfig":
        names = [self.default_provider, *self.fallback_order]
        unknown = [n for n in names if n not in self.providers]
        if unknown:
            raise ValueError(f"unknown provider(s) in models.json: {unknown}")
        if self.providers[self.default_provider].get_model(self.default_model) is None:
            raise ValueError(
                f"default_model '{self.default_model}' is not listed "
                f"under provider '{self.default_provider}'"
            )
        return self

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> "ModelsConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)
