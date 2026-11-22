import argparse
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from pydantic import ValidationError
from agent_mbpp.loop import run_agent
from llm.client import LLMClient
from models import SWEBENCH_LIMITS, SandboxConfig, SolutionOutput, SWEBenchTaskInput
from sandbox import McpConnection, Sandbox
from .container import copy_eval_script, remove_container, start_container

ROOT = Path(__file__).resolve().parents[2]  # configs + mcp server
MCP_SERVER = ROOT / "mcp_tools_swebench.py"
SANDBOX_CONFIG = ROOT / "sandbox_template.json"
MODELS_CONFIG = ROOT / "models.json"
MAX_FEEDBACK_CHARS = 4000  # test logs and file excerpts are long: ~1k tokens per observation

SYSTEM_PROMPT = """You fix a bug in a Python repository by writing Python code.
The repository is at /testbed inside a Docker container: it is NOT on your filesystem,
so open() cannot read it. Use ONLY the tool functions from the sandbox manual below.
Reply with a short thought, then ONE code block:
```python
# your code
```
<end_code>
Your code runs in a sandbox and you receive what it printed as feedback.

Work in this order, one or two tools per step:
1. Find the code: search_function_or_class_definition_in_code, search_code, find_references.
2. Read only the lines you need: read_file(path, start_line, end_line).
3. If possible, reproduce the bug: run_command('python -c "..."').
4. Fix it with edit_file. old_str must be copied exactly from the file, with its indentation.
5. Check with run_tests(). Its output is long: print only the end. exit_code can be 0
   even when tests fail, so read the test summary (passed / failed / error).
6. When the fix works, submit it: final_answer(get_patch()).
Rules: never edit test files, make the smallest change that fixes the issue,
never print a whole file.

Example:
```python
print(search_function_or_class_definition_in_code("parse_date"))
```
<end_code>
```python
print(read_file("/testbed/pkg/dates.py", 42, 60))
```
<end_code>
```python
old = "    return int(day)\\n"
new = "    return int(day.strip())\\n"
print(edit_file("/testbed/pkg/dates.py", old, new))
import json
result = json.loads(run_tests())
print(result["stdout"][-2000:])
```
<end_code>
Then, once the tests pass:
```python
final_answer(get_patch())
```
<end_code>
"""


def build_task_prompt(task: SWEBenchTaskInput) -> str:
    parts = [f"Repository: {task.repo}", "Issue to fix:", task.problem_statement]
    if task.hints_text:
        parts += ["Hints:", task.hints_text]
    return "\n".join(parts)


def solve(task: SWEBenchTaskInput, args: argparse.Namespace) -> SolutionOutput:
    llm = LLMClient.from_config(MODELS_CONFIG, args.provider_url, args.model_name)
    limits = SWEBENCH_LIMITS.model_copy(update={"max_iterations": args.max_iterations})
    config = SandboxConfig.from_json_file(SANDBOX_CONFIG)
    container = start_container(task.docker_image)
    try:
        copy_eval_script(container, task.eval_script)
        server = f'"{sys.executable}" "{MCP_SERVER}" {container}'
        with McpConnection.stdio(server) as mcp, Sandbox(config, mcp) as sandbox:
            return run_agent(llm, sandbox, SYSTEM_PROMPT, build_task_prompt(task), limits,
                             task.instance_id, "swebench", MAX_FEEDBACK_CHARS)
    finally:
        remove_container(container)  # always, even if the agent crashed


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="SWE-bench code agent")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--max-iterations", default=SWEBENCH_LIMITS.max_iterations, type=int)
    args = parser.parse_args()
    try:
        task = SWEBenchTaskInput.model_validate_json(Path(args.task_file).read_text())
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 1
    except ValidationError as e:
        print(f"Validation of task file failed: {e}", file=sys.stderr)
        return 1
    start = time.perf_counter()
    try:
        output = solve(task, args)
    except (Exception, SystemExit) as e:  # a crash = failed task: always write the output
        output = SolutionOutput(
            task_id=task.instance_id, benchmark="swebench", success=False, solution="",
            iterations=0, total_requests=0, total_input_tokens=0, total_output_tokens=0,
            total_time_seconds=time.perf_counter() - start,
            error=f"{type(e).__name__}: {e}",
        )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
