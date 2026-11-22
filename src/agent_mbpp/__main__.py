import argparse
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from pydantic import ValidationError
from llm.client import LLMClient
from models import MBPP_LIMITS, MBPPTaskInput, SandboxConfig, SolutionOutput
from sandbox import McpConnection, McpError, Sandbox
from .loop import SYSTEM_PROMPT, build_task_prompt, run_agent

ROOT = Path(__file__).resolve().parents[2]  # configs + mcp server
MCP_SERVER = ROOT / "mcp_tools_mbpp.py"
SANDBOX_CONFIG = ROOT / "sandbox_template.json"
MODELS_CONFIG = ROOT / "models.json"


def connect_mcp() -> McpConnection | None:
    try:
        return McpConnection.stdio(f'"{sys.executable}" "{MCP_SERVER}"').start()
    except (McpError, OSError) as error:  # no tools, but the agent still runs
        print(f"warning: MCP server unavailable, running without tools: {error}",
              file=sys.stderr)
        return None


def solve(task: MBPPTaskInput, args: argparse.Namespace) -> SolutionOutput:
    llm = LLMClient.from_config(MODELS_CONFIG, args.provider_url, args.model_name)
    limits = MBPP_LIMITS.model_copy(update={"max_iterations": args.max_iterations})
    config = SandboxConfig()
    if SANDBOX_CONFIG.exists():
        config = SandboxConfig.from_json_file(SANDBOX_CONFIG)
    mcp = connect_mcp()
    try:
        with Sandbox(config, mcp) as sandbox:
            return run_agent(llm, sandbox, SYSTEM_PROMPT, build_task_prompt(task), limits,
                             str(task.task_id))
    finally:
        if mcp is not None:
            mcp.close()


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="MBPP code agent")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--max-iterations", default=MBPP_LIMITS.max_iterations, type=int)
    args = parser.parse_args()
    try:
        task = MBPPTaskInput.model_validate_json(Path(args.task_file).read_text())
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
            task_id=str(task.task_id), benchmark="mbpp", success=False, solution="",
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
