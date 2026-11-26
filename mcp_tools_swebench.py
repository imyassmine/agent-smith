import json
import shlex
import subprocess
import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("swebench-tools")
# usage: python mcp_tools_swebench.py <container_id>
CONTAINER = sys.argv[1] if len(sys.argv) > 1 else ""
TESTBED = "/testbed"
EVAL_SCRIPT = "/eval.sh"  # copied into the container by the agent
COMMAND_TIMEOUT_SECONDS = 300
TESTS_TIMEOUT_SECONDS = 600


# docker

def docker(command: str, workdir: str = TESTBED, stdin: str = "",
                timeout: int = COMMAND_TIMEOUT_SECONDS) -> tuple[str, str, int]:
    """Runs a bash command in the container: returns (stdout, stderr, exit_code)."""
    if not CONTAINER:
        raise RuntimeError("no container id given to the MCP server")
    try:
        process = subprocess.run(
            ["docker", "exec", "-i", "-w", workdir, CONTAINER, "bash", "-c", command],
            input=stdin.encode(),
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout after {timeout}s") from None
    except FileNotFoundError:
        raise RuntimeError("docker is not installed") from None
    # bytes instead of text=True: text mode turns \r\n into \n, edit_file would change files
    stdout = process.stdout.decode(errors="replace")
    return stdout, process.stderr.decode(errors="replace"), process.returncode


def check_output(command: str) -> str:
    """Like docker_exec, but a failing command raises with its error message."""
    stdout, stderr, exit_code = docker(command)
    if exit_code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or f"exit code {exit_code}")
    return stdout


def grep(options: str) -> str:
    """grep -rn in the testbed, reformatted as '/path/file.py:<line> <content>'."""
    stdout, stderr, exit_code = docker(f"grep -rnI {options} {TESTBED}")
    if exit_code == 1:
        return "no matches found"
    if exit_code != 0:
        raise RuntimeError(stderr.strip())
    results = []
    for line in stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            results.append(f"{parts[0]}:{parts[1]} {parts[2]}")
    return "\n".join(results)


# server tools

@mcp.tool(
    description="Run a shell command in the repository's Docker container. "
    'Returns a JSON string: {"stdout": str, "stderr": str, "exit_code": int}.'
)
def run_command(command: str, workdir: str = TESTBED) -> str:
    stdout, stderr, exit_code = docker(command, workdir)
    return json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": exit_code})


@mcp.tool(
    description="Read a file with line numbers ('<line_number>: <line_content>'). "
    "end_line=0 reads until the end of the file."
)
def read_file(filepath: str, start_line: int = 1, end_line: int = 0) -> str:
    program = 'NR >= s && (e == 0 || NR <= e) { print NR ": " $0 }'
    return check_output(
        f"awk -v s={int(start_line)} -v e={int(end_line)} {shlex.quote(program)} "
        f"{shlex.quote(filepath)}"
    )


@mcp.tool(
    description="Replace old_str with new_str in a file. old_str must appear exactly once: "
    "include a few surrounding lines to make it unique. Python files are checked for "
    "syntax errors after the edit."
)
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    content = check_output(f"cat {shlex.quote(filepath)}")
    count = content.count(old_str) if old_str else 0
    if count != 1:
        raise ValueError(f"old_str was found {count} times in {filepath}, "
                         "it must be found exactly once")
    new_content = content.replace(old_str, new_str, 1)
    _, stderr, exit_code = docker(f"cat > {shlex.quote(filepath)}", stdin=new_content)
    if exit_code != 0:
        raise RuntimeError(stderr.strip())
    if filepath.endswith(".py"):
        try:
            compile(new_content, filepath, "exec")
        except SyntaxError as error:
            return (f"Edited {filepath}, but it now has a syntax error at line "
                    f"{error.lineno}: {error.msg}. Fix it with another edit.")
    return f"Edited {filepath}"


@mcp.tool(description="List files in a directory (recursively) whose name matches a glob "
                      "pattern, e.g. '*.py'.")
def list_files(directory: str = TESTBED, pattern: str = "*") -> str:
    return check_output(
        f"set -o pipefail; find {shlex.quote(directory)} -name {shlex.quote(pattern)} "
        "-not -path '*/.git/*' | sort"
    )


@mcp.tool(description="Search a regex (grep -E) in the repository. Only files matching "
                      "file_pattern are searched. Returns '/path/file.py:<line> <content>'.")
def search_code(pattern: str, file_pattern: str = "*.py") -> str:
    return grep(f"-E --include={shlex.quote(file_pattern)} -e {shlex.quote(pattern)}")


@mcp.tool(description="Find where a function or class is defined. "
                      "Returns '/path/file.py:<line> <content>'.")
def search_function_or_class_definition_in_code(name: str) -> str:
    regex = r"^\s*(async\s+)?(def|class)\s+" + name + r"\b"
    return grep(f"-E --include='*.py' -e {shlex.quote(regex)}")


@mcp.tool(description="Find all usages of a function or class name (whole word) in the "
                      "repository's Python files. Returns '/path/file.py:<line> <content>'.")
def find_references(name: str, filepath: str = "", line: int = 0) -> str:
    # the search is by name: filepath and line are accepted for the mandatory signature
    return grep(f"-w --include='*.py' -e {shlex.quote(name)}")


@mcp.tool(
    description="Run the task's evaluation script (tests) "
    'Returns a JSON string: {"stdout": str, "stderr": str, "exit_code": int}.'
)
def run_tests() -> str:
    stdout, stderr, exit_code = docker(f"bash {EVAL_SCRIPT}", timeout=TESTS_TIMEOUT_SECONDS)
    return json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": exit_code})


@mcp.tool(description="Return the git diff of all changes made to the repository. "
                      "Submit it with final_answer(get_patch()).")
def get_patch() -> str:
    return check_output("git -c core.fileMode=false diff")


if __name__ == "__main__":
    mcp.run(transport="stdio")
