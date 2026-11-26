import time
from llm.client import LLMClient, LLMError
from models import AgentLimits, MBPPTaskInput, SolutionOutput, StepMetrics
from sandbox import Sandbox

MAX_FEEDBACK_CHARS = 1000
TIME_MARGIN_SECONDS = 20
CHARS_PER_TOKEN = 3  # cautious: real tokenizers average about 4 characters per token
NO_CODE_FEEDBACK = (
    "No valid code block was found in the model's response. "
    "Reply with a ```python block ending with <end_code>."
)

SYSTEM_PROMPT = """You solve tasks by writing Python code.
Reply with a short thought, then ONE code block:
```python
# your code
```
<end_code>
Your code is executed in a sandbox and you receive what it printed as feedback.
Use print() to see values. When you have the answer, call final_answer(answer)
where answer is a string containing the solution code.
Example:
```python
solution = '''
def add(a, b):
    return a + b
'''
print(run_tests(code=solution, test_list=["assert add(1, 2) == 3"]))
```
<end_code>
Then, once the tests pass:
```python
final_answer(solution)
```
<end_code>
"""


def build_task_prompt(task: MBPPTaskInput) -> str:
    parts = [
        f"Task definition: {task.task_definition}",
        f"Function definition: {task.function_definition}",
        "Imports needed by the tests: ",
        *task.test_imports,
        "Tests that must pass: ",
        *task.test_list,
        "Run these tests in your code before calling final_answer.",
    ]
    return "\n".join(parts)


def extract_code(text: str) -> tuple[str | None, str]:
    text = text.split("<end_code>")[0]
    parts = text.split("```python\n", 1)
    if len(parts) < 2:
        return None, ""
    feedback = (
        "code block was malformed (closing ``` missing) but was interpreted anyway\n"
        if "```" not in parts[1]
        else ""
    )
    return parts[1].split("```")[0], feedback


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\nTool output was truncated due to size limits\n" + text[-half:]


def execute(
    sandbox: Sandbox, llm_output: str, max_chars: int, time_left: float
) -> tuple[str, str, str | None]:
    """Runs the code of one LLM reply: returns (code, feedback, final answer or None)."""
    code, feedback = extract_code(llm_output)
    if code is None:
        return "", NO_CODE_FEEDBACK, None
    result = sandbox.execute(code, time_limit=time_left)
    if result.final_answer is not None:
        return code, feedback + result.output + "final_answer() called", result.final_answer
    output = result.output or "(no output, use print() to see values)"
    return code, truncate(feedback + output, max_chars), None


def estimate_next_input(messages: list[dict], steps: list[StepMetrics]) -> int:
    """Input tokens of the next call: the whole conversation is sent again each time."""
    if not steps:
        return sum(len(m["content"]) for m in messages) // CHARS_PER_TOKEN
    new = messages[-2:]  # the last reply and its feedback, added since the last call
    return steps[-1].input_tokens + sum(len(m["content"]) for m in new) // CHARS_PER_TOKEN


def budget_exhausted(
    steps: list[StepMetrics], limits: AgentLimits, deadline: float, next_input: int
) -> str | None:
    if time.perf_counter() >= deadline:
        return "time budget exhausted"
    if sum(s.input_tokens for s in steps) + next_input > limits.max_input_tokens:
        return "input token budget exhausted (the next call would go over the limit)"
    if sum(s.output_tokens for s in steps) >= limits.max_output_tokens:
        return "output token budget exhausted"
    return None


def run_agent(
    llm: LLMClient,
    sandbox: Sandbox,
    system_prompt: str,
    task: str,
    limits: AgentLimits,
    task_id: str,
    benchmark: str = "mbpp",
    max_feedback_chars: int = MAX_FEEDBACK_CHARS,
) -> SolutionOutput:
    """The Thought -> Code -> Observation loop."""
    start = time.perf_counter()
    deadline = start + limits.timeout_seconds - TIME_MARGIN_SECONDS
    system_prompt = system_prompt + "\n" + sandbox.manual()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    steps: list[StepMetrics] = []
    solution, error = None, "max_iterations reached"

    for i in range(1, limits.max_iterations + 1):
        problem = budget_exhausted(steps, limits, deadline, estimate_next_input(messages, steps))
        if problem:
            error = problem
            break
        output_left = limits.max_output_tokens - sum(s.output_tokens for s in steps)
        try:
            reply = llm.complete(
                messages,
                max_tokens=min(llm.model.max_tokens_per_call, output_left),
                timeout=deadline - time.perf_counter(),
            )
        except LLMError as e:
            error = str(e)
            break
        code, feedback, answer = execute(
            sandbox, reply.text, max_feedback_chars, deadline - time.perf_counter()
        )
        steps.append(
            StepMetrics(
                step=i,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                request_time_ms=reply.request_time_ms,
                api_url=llm.provider.base_url,
                model_name=reply.model_name,
                llm_output=reply.text,
                sandbox_input=code,
                sandbox_output=feedback,
                retries=reply.retries,
            )
        )
        if answer is not None:
            solution, error = answer, None
            break
        messages.append({"role": "assistant", "content": reply.text})
        messages.append({"role": "user", "content": f"'feedback': {feedback}"})

    return SolutionOutput.from_steps(
        steps,
        task_id=task_id,
        benchmark=benchmark,
        success=solution is not None,
        solution=solution or "",
        total_time_seconds=time.perf_counter() - start,
        system_prompt=system_prompt,
        error=error,
    )
