import json
from pathlib import Path
from typing import List, Union

from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    authorized_imports: List[str] = Field(default_factory=lambda: [
        "math", "math.*",
        "collections", "collections.*",
        "itertools", "re", "json",
        "typing", "typing.*",
        "functools", "operator",
        "heapq", "bisect", "copy",
        "string", "random",
        "datetime", "datetime.*",
        "array", "cmath",
    ])
    allowed_directories: List[str] = Field(default_factory=lambda: [
        "/testbed", "/tmp/agent"
    ])
    max_execution_time_seconds: int = 30
    max_memory_mb: int = 512

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> "SandboxConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)
