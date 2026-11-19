import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[2] / "mcp_tools_mbpp.py"
params = StdioServerParameters(
    command=sys.executable, args=[str(SERVER)]
)


def call_tool(name: str, arguments: dict) -> str:
    async def _call():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return result.content[0].text

    return asyncio.run(_call())


def list_tools():
    async def _list():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools

    return asyncio.run(_list())

if __name__ == "__main__":
    for tool in list_tools():
        print(tool.name, list(tool.inputSchema["properties"]))
