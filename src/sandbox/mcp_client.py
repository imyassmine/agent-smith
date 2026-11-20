import asyncio
import json
import shlex
import sys
import threading
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

CONNECT_TIMEOUT_SECONDS = 60
CALL_TIMEOUT_SECONDS = 900


class McpError(RuntimeError):
    pass


class McpConnection:
    def __init__(self, command: list[str] | None = None, url: str | None = None):
        if (command is None) == (url is None):
            raise ValueError("give exactly one of command (stdio) or url (HTTP)")
        self.command, self.url = command, url
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: ClientSession | None = None
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._error: BaseException | None = None
        self.tools: list[dict[str, Any]] = []

    @classmethod
    def stdio(cls, command_line: str) -> "McpConnection":
        parts = shlex.split(command_line)
        if parts and parts[0] in ("python", "python3"):
            parts[0] = sys.executable  # use the venv python
        return cls(command=parts)

    @classmethod
    def http(cls, url: str) -> "McpConnection":
        return cls(url=url)

    @property
    def description(self) -> str:
        return " ".join(self.command) if self.command else str(self.url)

    def start(self) -> "McpConnection":
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(CONNECT_TIMEOUT_SECONDS):
            raise McpError(f"MCP server {self.description} did not answer in time")
        if self._error is not None:
            raise McpError(f"cannot connect to MCP server {self.description}: "
                           f"{self._error}") from self._error
        self.tools = self._call(self._list_tools())
        return self

    def close(self) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._session = None

    def __enter__(self) -> "McpConnection":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._main())
        except BaseException as error:  # noqa: B036
            self._error = error
        finally:
            self._ready.set()
            self._loop.close()

    # everything opened and closed in one task, anyio needs that
    async def _main(self) -> None:
        self._stop = asyncio.Event()
        if self.command:
            params = StdioServerParameters(command=self.command[0], args=self.command[1:])
            transport = stdio_client(params)
        else:
            transport = streamablehttp_client(self.url)
        async with transport as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                self._ready.set()
                await self._stop.wait()

    def _call(self, coroutine: Any) -> Any:
        if self._loop is None or self._session is None:
            raise McpError("MCP connection is not open")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result(CALL_TIMEOUT_SECONDS)

    async def _list_tools(self) -> list[dict[str, Any]]:
        result = await self._session.list_tools()
        return [{"name": t.name, "description": t.description or "",
                 "input_schema": t.inputSchema or {}} for t in result.tools]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = self._call(self._session.call_tool(name, arguments))
        text = _content_to_text(result.content)
        if getattr(result, "isError", False):
            raise McpError(text or f"tool {name} failed")
        return text

    def list_resources(self) -> str:
        async def run() -> Any:
            return await self._session.list_resources()
        try:
            result = self._call(run())
        except Exception as error:
            return f"[] (resources not available: {error})"
        return json.dumps([{"uri": str(r.uri), "name": r.name,
                            "description": r.description or ""} for r in result.resources])

    def read_resource(self, uri: str) -> str:
        async def run() -> Any:
            return await self._session.read_resource(uri)
        result = self._call(run())
        return "\n".join(getattr(c, "text", "") or "" for c in result.contents)

    def list_prompts(self) -> str:
        async def run() -> Any:
            return await self._session.list_prompts()
        try:
            result = self._call(run())
        except Exception as error:
            return f"[] (prompts not available: {error})"
        return json.dumps([{"name": p.name, "description": p.description or "",
                            "arguments": [a.name for a in (p.arguments or [])]}
                           for p in result.prompts])

    def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> str:
        async def run() -> Any:
            return await self._session.get_prompt(name, arguments or {})
        result = self._call(run())
        return "\n".join(_content_to_text([m.content]) for m in result.messages)


def _content_to_text(content: list[Any]) -> str:
    parts = []
    for block in content:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else f"<{getattr(block, 'type', 'data')}>")
    return "\n".join(parts)
