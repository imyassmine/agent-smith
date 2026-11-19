import json
import subprocess
import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mbpp-tools")


@mcp.tool(
    description="Run candidate Python code against assert statements. "
    'Returns a JSON string: {"success": bool, "output": str}.'
)
def run_tests(code: str, test_list: list[str]) -> str:
    script = code + "\n" + "\n".join(test_list)
    try:
        completed_process = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "output": "Timeout after 30s"})
    return json.dumps(
        {
            "success": completed_process.returncode == 0,
            "output": completed_process.stdout + completed_process.stderr,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
