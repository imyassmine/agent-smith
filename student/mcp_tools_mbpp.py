import sys, json
from subprocess import run, TimeoutExpired, CalledProcessError
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("mbpp-tools")  # crée un serveur MCP


@mcp.tool()  # enregistre la fonction run_test comme outil MCP
def run_tests(code: str, test_list: list[str]) -> str:
    """Run candidate Python code against assert statements.

    Returns a JSON string: {"success": bool, "output": str}.
    """
    script = code + "\n" + "\n".join(test_list)
    try:
        completed_process = run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except TimeoutExpired:
        return json.dumps({"success": False, "output": f"Timeout after 30s"})
    return json.dumps(
        {
            "success": completed_process.returncode == 0,
            "output": completed_process.stdout + completed_process.stderr,
        }
    )
