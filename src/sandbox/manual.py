from typing import Any
from models import SandboxConfig

JSON_TO_PYTHON = {"string": "str", "integer": "int", "number": "float",
                  "boolean": "bool", "object": "dict", "null": "None"}

MCP_EXTRAS = [
    {"name": "list_resources", "kind": "list_resources", "params": [],
     "signature": "list_resources() -> str",
     "doc": "JSON list of the MCP server's resources (uri, name, description)."},
    {"name": "read_resource", "kind": "read_resource", "params": ["uri"],
     "signature": "read_resource(uri: str) -> str",
     "doc": "Text content of one MCP resource."},
    {"name": "list_prompts", "kind": "list_prompts", "params": [],
     "signature": "list_prompts() -> str",
     "doc": "JSON list of the MCP server's prompts (name, description, arguments)."},
    {"name": "get_prompt", "kind": "get_prompt", "params": ["name", "arguments"],
     "signature": "get_prompt(name: str, arguments: dict = None) -> str",
     "doc": "Text of one MCP prompt, filled with `arguments`."},
]


def python_type(schema: dict[str, Any]) -> str:
    kind = schema.get("type")
    if kind == "array":
        return f"list[{python_type(schema.get('items', {}))}]"
    return JSON_TO_PYTHON.get(kind, "Any")


def functions_from_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    functions = []
    for tool in tools:
        schema = tool.get("input_schema") or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        params, shown = [], []
        for name, prop in properties.items():
            params.append(name)
            default = "" if name in required else f" = {prop.get('default')!r}"
            shown.append(f"{name}: {python_type(prop)}{default}")
        functions.append({
            "name": tool["name"], "kind": "tool", "params": params,
            "signature": f"{tool['name']}({', '.join(shown)}) -> str",
            "doc": (tool.get("description") or "").strip(),
        })
    return functions + MCP_EXTRAS


def build_manual(config: SandboxConfig, functions: list[dict[str, Any]]) -> str:
    lines = [
        "## Sandbox manual",
        "Your code runs in a restricted Python 3.10 sandbox. Variables, functions and "
        "imports persist from one code block to the next.",
        "",
        "Rules:",
        f"- Allowed imports ONLY: {', '.join(config.authorized_imports)}. "
        "Anything else (os, sys, subprocess, socket...) raises ImportError.",
        f"- Files can only be opened inside: {', '.join(config.allowed_directories)}.",
        "- No network access, no subprocesses.",
        f"- Each code block may run at most {config.max_execution_time_seconds} s and use "
        f"at most {config.max_memory_mb} MB of RAM. If it goes over, it is stopped, "
        "you get the partial output, and the variables are lost.",
        "- Use print() to see values: only what you print comes back to you.",
        "",
        "Functions you can call like normal Python functions:",
        "- final_answer(answer: str) -> None",
        "    Ends the task with `answer`. MBPP: the full solution code as a string. "
        "SWE-bench: final_answer(get_patch()).",
    ]
    for spec in functions:
        lines.append(f"- {spec['signature']}")
        for doc_line in (spec.get("doc") or "").splitlines():
            if doc_line.strip():
                lines.append(f"    {doc_line.strip()}")
    if functions:
        lines.append("Tool functions return strings (often JSON: use json.loads). "
                     "If a tool fails, it raises RuntimeError with the reason.")
    return "\n".join(lines)
