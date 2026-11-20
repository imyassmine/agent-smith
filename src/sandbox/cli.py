import argparse
import codeop
import sys
from contextlib import ExitStack
from pydantic import ValidationError
from models import SandboxConfig
from sandbox.mcp_client import McpConnection, McpError
from sandbox.sandbox import Sandbox, SandboxError


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sandbox", description="Interactive sandbox")
    parser.add_argument("config", nargs="?", help="sandbox JSON config (SandboxConfig)")
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument("--mcp-stdio", metavar="CMD",
                           help='MCP server command, e.g. "python mcp_tools_mbpp.py"')
    transport.add_argument("--mcp-server", metavar="URL",
                           help="MCP server URL (streamable HTTP)")
    return parser.parse_args(argv)


def read_block() -> str | None:
    lines: list[str] = []
    while True:
        try:
            line = input("... " if lines else ">>> ")
        except EOFError:
            print()
            return "\n".join(lines) if lines else None
        lines.append(line)
        source = "\n".join(lines)
        try:
            complete = codeop.compile_command(source, "<sandbox>", "exec")
        except (SyntaxError, ValueError, OverflowError):
            return source
        if complete is not None:
            return source


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = SandboxConfig.from_json_file(args.config) if args.config else SandboxConfig()
    except (OSError, ValueError, ValidationError) as error:
        print(f"sandbox: invalid config {args.config}: {error}", file=sys.stderr)
        return 1

    with ExitStack() as stack:
        mcp = None
        try:
            if args.mcp_stdio:
                mcp = stack.enter_context(McpConnection.stdio(args.mcp_stdio))
            elif args.mcp_server:
                mcp = stack.enter_context(McpConnection.http(args.mcp_server))
            sandbox = stack.enter_context(Sandbox(config, mcp))
        except (McpError, SandboxError, OSError) as error:
            print(f"sandbox: {error}", file=sys.stderr)
            return 1
        print(sandbox.manual())
        print("\nCtrl-D to quit.")
        while True:
            try:
                source = read_block()
            except KeyboardInterrupt:
                print("\nKeyboardInterrupt")
                continue
            if source is None:
                return 0
            if not source.strip():
                continue
            try:
                result = sandbox.execute(source)
            except SystemExit as exit_:
                print(f"[SystemExit({exit_.code!r}) raised by the code: bye]")
                return 0
            except KeyboardInterrupt:
                print("\nKeyboardInterrupt")
                continue
            print(result.output, end="" if result.output.endswith("\n") else "\n")
            if result.final_answer is not None:
                print(f"[final_answer] {result.final_answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
