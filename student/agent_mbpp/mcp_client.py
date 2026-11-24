import sys, asyncio, signal
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent.parent / "mcp_tools_mbpp.py"
params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
TYPE_NAMES = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "object": "dict",
}

def call_tool(name: str, arguments: dict) -> str:
    return asyncio.run(_call())

async def _call(name: str, arguments: dict):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return "".join(
                    c.text for c in result.content if hasattr(c, "text")
                )

def list_tools():
    return asyncio.run(_list())

async def _list():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools




def _type_name(schema: dict) -> str:
    kind = schema.get("type", "any")
    if kind == "array":
        return f"list[{_type_name(schema.get('items', {}))}]"
    return TYPE_NAMES.get(kind, kind)


def build_manual(tools) -> str:
    """Manuel des outils, généré depuis les schémas du serveur MCP."""
    if not tools:
        return "No tool is available."
    lines = ["Tools (call them like normal Python functions):"]
    for tool in tools:
        props = tool.inputSchema.get("properties", {})
        signature = ", ".join(
            f"{name}: {_type_name(schema)}" for name, schema in props.items()
        )
        description = " ".join((tool.description or "").split())
        lines.append(f"- {tool.name}({signature}): {description}")
    return "\n".join(lines)


def build_tool_wrappers(tools) -> dict:
    """Une fonction Python par outil MCP, à mettre dans le namespace."""
    wrappers = {}
    for tool in tools:
        param_names = list(tool.inputSchema.get("properties", {}))

        def wrapper(*args, _name=tool.name, _params=param_names, **kwargs):
            arguments = {**dict(zip(_params, args)), **kwargs}
            # L'outil s'exécute hors sandbox : il n'est pas soumis au timeout
            # d'exécution, on met donc l'alarme en pause pendant l'appel.
            paused = signal.setitimer(signal.ITIMER_REAL, 0)
            try:
                return call_tool(_name, arguments)
            finally:
                signal.setitimer(signal.ITIMER_REAL, paused[0])

        wrapper.__name__ = tool.name
        wrappers[tool.name] = wrapper
    return wrappers
