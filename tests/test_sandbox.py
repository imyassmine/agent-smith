import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from models import SandboxConfig
from sandbox import McpConnection, Sandbox

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def sandbox(tmp_path):
    config = SandboxConfig(allowed_directories=[str(tmp_path)],
                           max_execution_time_seconds=2, max_memory_mb=256)
    with Sandbox(config) as box:
        yield box


def test_allowed_import_and_state_persists(sandbox):
    assert sandbox.execute("import math\nx = math.sqrt(16)").output == ""
    assert sandbox.execute("print(x + 1)").output == "5.0\n"


@pytest.mark.parametrize("code", [
    "import os",
    "import subprocess",
    "from socket import socket",
    "exec('import os', {})",
    "print.__self__.__import__('_posixsubprocess')",
    "print.__self__.__import__('subprocess').run(['ls'])",
    "print.__self__.__import__('socket').socket()",
])
def test_imports_outside_allowlist_are_refused(sandbox, code):
    assert "ImportError" in sandbox.execute(code).output


@pytest.mark.parametrize("code, event", [
    ("import random\nrandom._os.system('echo hacked')", "os.system"),
])
def test_dangerous_actions_are_blocked(sandbox, code, event):
    output = sandbox.execute(code).output
    assert "PermissionError" in output and event in output
    assert "hacked" not in output


def test_filesystem_restricted_to_allowed_directories(sandbox, tmp_path):
    assert "PermissionError" in sandbox.execute("open('/etc/passwd')").output
    assert "PermissionError" in sandbox.execute(
        "print.__self__.open('/etc/passwd')").output
    out = sandbox.execute(f"open({str(tmp_path / 'a.txt')!r}, 'w').write('hi')\n"
                          "print(open('a.txt').read())")
    assert out.output == "hi\n"


def test_no_secrets_in_environment(sandbox, monkeypatch):
    out = sandbox.execute("import random\nprint(sorted(random._os.environ))").output
    assert "KEY" not in out


def test_timeout_gives_partial_output_and_restarts(sandbox):
    result = sandbox.execute("print('started')\nwhile True: pass")
    assert result.timed_out
    assert "started" in result.output and "timeout" in result.output
    assert "NameError" not in sandbox.execute("print(1)").output


def test_memory_limit(sandbox):
    result = sandbox.execute("chunks = []\nfor _ in range(12):\n"
                             "    chunks.append(b'x' * (100 * 1024 * 1024))\n"
                             "print('allocated')")
    assert "allocated" not in result.output
    assert "MemoryError" in result.output


def test_final_answer(sandbox):
    result = sandbox.execute("print('bye')\nfinal_answer('def f(): return 1')")
    assert result.final_answer == "def f(): return 1" and "bye" in result.output
    result = sandbox.execute("try:\n    final_answer('x')\nexcept Exception:\n    pass")
    assert result.final_answer == "x"
    assert "TypeError" in sandbox.execute("final_answer(3)").output


def test_system_exit_and_keyboard_interrupt_propagate(sandbox):
    with pytest.raises(SystemExit):
        sandbox.execute("raise SystemExit(2)")
    with pytest.raises(KeyboardInterrupt):
        sandbox.execute("raise KeyboardInterrupt")


def test_syntax_error_feedback(sandbox):
    assert "SyntaxError" in sandbox.execute("def f(:\n    pass").output


class FakeMcp:
    tools = [{"name": "add", "description": "Add two numbers.",
              "input_schema": {"properties": {"a": {"type": "integer"},
                                              "b": {"type": "integer"}},
                               "required": ["a", "b"]}}]

    def call_tool(self, name, arguments):
        return str(arguments["a"] + arguments["b"])


def test_unknown_mcp_server_tools_are_discovered(tmp_path):
    config = SandboxConfig(allowed_directories=[str(tmp_path)])
    with Sandbox(config, FakeMcp()) as box:
        assert "add(a: int, b: int) -> str" in box.manual()
        assert box.execute("print(add(2, b=3))").output == "5\n"


def test_real_mbpp_mcp_server(tmp_path):
    config = SandboxConfig(allowed_directories=[str(tmp_path)])
    with McpConnection.stdio(f"python {ROOT / 'mcp_tools_mbpp.py'}") as mcp:
        with Sandbox(config, mcp) as box:
            assert "run_tests(code: str, test_list: list[str])" in box.manual()
            out = box.execute("print(run_tests(code='def f(): return 1', "
                              "test_list=['assert f() == 1']))").output
            assert json.loads(out)["success"] is True


def test_agent_loop_with_scripted_llm(tmp_path):
    from agent_mbpp.loop import SYSTEM_PROMPT, run_agent
    from llm.client import LLMResponse
    from models import MBPP_LIMITS, ModelConfig

    replies = iter([
        "Thought: write and test.\n```python\nsol = 'def f():\\n    return 1\\n'\n"
        "print(run_tests(code=sol, test_list=['assert f() == 1']))\n```\n",
        "Thought: tests pass.\n```python\nfinal_answer(sol)\n```\n",
    ])

    class FakeLLM:
        provider = SimpleNamespace(base_url="https://fake/v1")
        model = ModelConfig(name="fake-model")

        def complete(self, messages, max_tokens, timeout):
            return LLMResponse(text=next(replies), input_tokens=10, output_tokens=5,
                               request_time_ms=1.0, model_name="fake-model")

    config = SandboxConfig(allowed_directories=[str(tmp_path)])
    with McpConnection.stdio(f"python {ROOT / 'mcp_tools_mbpp.py'}") as mcp:
        with Sandbox(config, mcp) as box:
            out = run_agent(FakeLLM(), box, SYSTEM_PROMPT, "task", MBPP_LIMITS, task_id="1")
    assert out.success and out.solution == "def f():\n    return 1\n"
    assert '"success": true' in out.steps[0].sandbox_output
    assert "run_tests(" in out.system_prompt
    assert (out.iterations, out.total_input_tokens) == (2, 20)
