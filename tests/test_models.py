from pathlib import Path
import pytest
from pydantic import ValidationError
from models import (
    MBPP_LIMITS,
    MBPPTaskInput,
    ModelsConfig,
    SandboxConfig,
    SolutionOutput,
    StepMetrics,
    SWEBenchTaskInput,
)

ROOT = Path(__file__).resolve().parent.parent


def test_mbpp_task_parses_and_defaults_are_not_shared():
    a = MBPPTaskInput(task_id=2, task_definition="t", function_definition="def f():")
    b = MBPPTaskInput(task_id=3, task_definition="t", function_definition="def f():")
    a.test_list.append("assert f() == 1")
    assert b.test_list == []


def test_swebench_task_requires_fields():
    with pytest.raises(ValidationError):
        SWEBenchTaskInput(instance_id="x")


def test_solution_totals_and_json_roundtrip():
    steps = [
        StepMetrics(step=1, input_tokens=100, output_tokens=20, request_time_ms=50.0, retries=2),
        StepMetrics(step=2, input_tokens=200, output_tokens=30, request_time_ms=40.0),
    ]
    out = SolutionOutput.from_steps(
        steps, task_id=str(2), benchmark="mbpp", success=True,
        solution="def f(): return 1", total_time_seconds=1.5,
    )
    assert (out.iterations, out.total_requests) == (2, 4)
    assert (out.total_input_tokens, out.total_output_tokens) == (300, 50)
    again = SolutionOutput.model_validate_json(out.model_dump_json())
    assert again == out


def test_config_files_load():
    sandbox = SandboxConfig.from_json_file(ROOT / "sandbox_template.json")
    assert "os" not in sandbox.authorized_imports
    models = ModelsConfig.from_json_file(ROOT / "models.json")
    assert models.default_provider in models.providers
    assert MBPP_LIMITS.max_iterations == 10



def test_models_json_typo_is_caught():
    with pytest.raises(ValidationError):
        ModelsConfig(providers={}, default_provider="nope", default_model="x")
