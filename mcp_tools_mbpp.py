import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mbpp-tools")


@mcp.tool()
def run_tests(code: str, test_list: list[str]) -> str:
    """Run candidate Python code against assert statements.

    Returns a JSON string: {"success": bool, "output": str}.
    """
    #  assembler code + tests, exécuter, renvoyer le JSON


if __name__ == "__main__":
    mcp.run(transport="stdio")