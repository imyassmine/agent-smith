import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from models import SandboxConfig
from sandbox.manual import build_manual, functions_from_tools

WORKER = Path(__file__).resolve().with_name("worker.py")
STARTUP_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 100_000


@dataclass
class ExecutionResult:
    output: str
    final_answer: str | None = None
    timed_out: bool = False
    crashed: bool = False


class SandboxError(RuntimeError):
    pass


class Sandbox:
    def __init__(self, config: SandboxConfig | None = None, mcp: Any = None) -> None:
        self.config = config or SandboxConfig()
        self.mcp = mcp
        self.functions = functions_from_tools(mcp.tools) if mcp is not None else []
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._messages: queue.Queue = queue.Queue()

    def __enter__(self) -> "Sandbox":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def start(self) -> None:
        workdir = self._prepare_directories()
        env = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}  # no api keys in the child
        self._proc = subprocess.Popen(
            [sys.executable, "-I", "-S", str(WORKER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=workdir, env=env,
        )
        # a thread reads the worker's messages, so _recv can wait with a timeout
        self._messages = queue.Queue()
        self._reader = threading.Thread(
            target=_read_messages, args=(self._proc.stdout, self._messages), daemon=True)
        self._reader.start()
        self._send({"type": "init", "config": self.config.model_dump(),
                    "functions": self.functions})
        message = self._recv(time.monotonic() + STARTUP_TIMEOUT_SECONDS)
        if not message or message.get("type") != "ready":
            self.close()
            raise SandboxError("the sandbox worker did not start")

    def close(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc.wait()
            if self._reader is not None:
                self._reader.join(timeout=1)  # it stops at EOF
            for pipe in (self._proc.stdin, self._proc.stdout):
                if pipe:
                    pipe.close()
            self._proc = None

    def manual(self) -> str:
        return build_manual(self.config, self.functions)

    def _prepare_directories(self) -> str:
        existing = []
        temp_roots = {os.path.realpath(tempfile.gettempdir()), os.path.realpath("/tmp")}
        for directory in self.config.allowed_directories:
            real = os.path.realpath(directory)
            if any(real.startswith(root + os.sep) for root in temp_roots):
                try:
                    os.makedirs(directory, exist_ok=True)
                except OSError:
                    pass
            if os.path.isdir(directory):
                existing.append(directory)
        return existing[0] if existing else tempfile.gettempdir()

    def execute(self, code: str) -> ExecutionResult:
        notes = []
        if self._proc is None or self._proc.poll() is not None:
            if self._proc is not None:
                notes.append("[sandbox restarted: variables from previous blocks are lost]\n")
            self.close()
            self.start()
        self._send({"type": "exec", "code": code})
        output: list[str] = []
        size = 0
        timeout = self.config.max_execution_time_seconds
        deadline = time.monotonic() + timeout

        def text(extra: str = "") -> str:
            body = "".join(notes + output)
            if size > MAX_OUTPUT_CHARS:
                body += "\n[output cut: more than %d characters]\n" % MAX_OUTPUT_CHARS
            return body + extra

        while True:
            try:
                message = self._recv(deadline)
            except EOFError:
                code_ = self._proc.wait() if self._proc else None
                self.close()
                return ExecutionResult(text(
                    f"\n[sandbox process crashed (exit code {code_}), probably out of "
                    f"memory. Variables are lost.]\n"), crashed=True)
            if message is None:
                self.close()
                return ExecutionResult(text(
                    f"\n[Execution hit the timeout ({timeout}s) and output is partial. "
                    f"The code was stopped and the sandbox restarted: variables "
                    f"defined before are lost.]\n"), timed_out=True)
            kind = message.get("type")
            if kind == "output":
                data = message.get("data", "")
                if size < MAX_OUTPUT_CHARS:
                    output.append(data[: MAX_OUTPUT_CHARS - size])
                size += len(data)
            elif kind == "call":
                started = time.monotonic()
                self._send(self._handle_call(message))
                deadline += time.monotonic() - started  # mcp time doesn't count
            elif kind == "final_answer":
                return ExecutionResult(text(), final_answer=message.get("value"))
            elif kind == "done":
                return ExecutionResult(text())
            elif kind == "memory_exceeded":
                self.close()
                return ExecutionResult(text(
                    f"\n[MemoryError: the code used more than "
                    f"{message.get('limit_mb')} MB and was stopped. The sandbox "
                    f"restarted: variables are lost.]\n"), crashed=True)
            elif kind == "system_exit":
                self.close()
                raise SystemExit(message.get("code"))
            elif kind == "keyboard_interrupt":
                self.close()
                raise KeyboardInterrupt

    def _handle_call(self, message: dict[str, Any]) -> dict[str, Any]:
        if self.mcp is None:
            return {"type": "reply", "ok": False, "error": "no MCP server connected"}
        args = message.get("arguments") or {}
        try:
            kind, name = message.get("kind"), message.get("name")
            if kind == "tool":
                result = self.mcp.call_tool(name, args)
            elif kind == "list_resources":
                result = self.mcp.list_resources()
            elif kind == "read_resource":
                result = self.mcp.read_resource(**args)
            elif kind == "list_prompts":
                result = self.mcp.list_prompts()
            elif kind == "get_prompt":
                result = self.mcp.get_prompt(**args)
            else:
                return {"type": "reply", "ok": False, "error": f"unknown call {kind}"}
        except Exception as error:
            return {"type": "reply", "ok": False, "error": f"{type(error).__name__}: {error}"}
        return {"type": "reply", "ok": True, "result": result}

    def _send(self, message: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except BrokenPipeError:
            pass

    def _recv(self, deadline: float) -> dict[str, Any] | None:
        """Next message from the worker, or None if the deadline passes first."""
        try:
            message = self._messages.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            return None
        if message is None:  # the worker closed its stdout: it died
            raise EOFError
        return message


def _read_messages(stdout: Any, messages: queue.Queue) -> None:
    for line in stdout:
        messages.put(json.loads(line))
    messages.put(None)
