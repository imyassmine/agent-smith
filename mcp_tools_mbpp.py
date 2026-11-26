import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from models import SandboxConfig
from sandbox import Sandbox

mcp = FastMCP("mbpp-tools")
SANDBOX_CONFIG = Path(__file__).resolve().with_name("sandbox_template.json")


@mcp.tool(
    description="Run candidate Python code against assert statements. "
    'Returns a JSON string: {"success": bool, "output": str}.'
)
def run_tests(code: str, test_list: list[str]) -> str:
    config = SandboxConfig()
    if SANDBOX_CONFIG.exists():
        config = SandboxConfig.from_json_file(SANDBOX_CONFIG)
    # the tested code comes from the model: it runs in the sandbox, like all its code
    with Sandbox(config) as sandbox:
        result = sandbox.execute(code + "\n" + "\n".join(test_list))
    success = not (result.failed or result.timed_out or result.crashed or result.exited)
    return json.dumps({"success": success, "output": result.output})


if __name__ == "__main__":
    mcp.run(transport="stdio")
