import json
import select
import subprocess
import sys
import time
from pathlib import Path

from .mcp_client import build_manual, call_tool, list_tools

WORKER = Path(__file__).with_name("sandbox_worker.py")
EXEC_TIMEOUT = 30  # secondes


class Sandbox:
    """Exécute le code du modèle dans un processus worker séparé.

    Le worker garde ses variables d'une étape à l'autre. Les outils MCP sont
    appelés ici, côté agent, donc hors du timeout de la sandbox.
    """

    def __init__(self, extra_namespace: dict):
        tools = list_tools()
        self.manual = build_manual(tools)
        self._init_message = {
            "type": "init",
            "tools": {
                t.name: list(t.inputSchema.get("properties", {}))
                for t in tools
            },
            "namespace": extra_namespace,
        }
        self._start()

    def _start(self) -> None:
        self._worker = subprocess.Popen(
            [sys.executable, "-I", str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env={},  # le worker n'hérite pas des clés API de l'agent
        )
        self._send(self._init_message)

    def _send(self, message: dict) -> None:
        self._worker.stdin.write(json.dumps(message) + "\n")
        self._worker.stdin.flush()

    def close(self) -> None:
        self._worker.kill()
        self._worker.wait()

    def _restart(self) -> None:
        self.close()
        self._start()

    @staticmethod
    def _run_tool(message: dict) -> dict:
        try:
            result = call_tool(message["name"], message["arguments"])
        except Exception as e:
            return {"type": "tool_result", "error": f"{type(e).__name__}: {e}"}
        return {"type": "tool_result", "result": result}

    def execute_safe_code(self, code: str) -> tuple[str, str | None]:
        self._send({"type": "exec", "code": code})
        remaining = EXEC_TIMEOUT
        while True:
            started = time.monotonic()
            ready, _, _ = select.select(
                [self._worker.stdout], [], [], max(remaining, 0)
            )
            if not ready:
                self._restart()
                return (
                    "Execution hit the timeout and output is partial "
                    "(not available). The sandbox was restarted: variables "
                    "defined in earlier steps are lost.",
                    None,
                )
            line = self._worker.stdout.readline()
            if not line:
                self._restart()
                return (
                    "The sandbox process stopped unexpectedly and was "
                    "restarted: variables defined in earlier steps are lost.",
                    None,
                )
            # Seul le temps passé à attendre le worker compte pour le timeout
            remaining -= time.monotonic() - started
            message = json.loads(line)
            if message["type"] == "tool_call":
                self._send(self._run_tool(message))
            else:
                return message["output"], message["answer"]
