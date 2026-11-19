from pydantic import BaseModel, Field


class AgentLimits(BaseModel):
    max_iterations: int = Field(..., gt=0)
    max_input_tokens: int = Field(..., gt=0)
    max_output_tokens: int = Field(..., gt=0)
    timeout_seconds: float = Field(..., gt=0)


MBPP_LIMITS = AgentLimits(
    max_iterations=10, max_input_tokens=6_000, max_output_tokens=1_500, timeout_seconds=120
)
SWEBENCH_LIMITS = AgentLimits(
    max_iterations=30, max_input_tokens=300_000, max_output_tokens=10_000, timeout_seconds=900
)
