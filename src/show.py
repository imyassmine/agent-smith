"""Pretty-prints a solution.json step by step. Usage: python src/show.py <solution.json>"""

import json
import sys


def indent(text: str, label: str) -> str:
    lines = text.strip().splitlines() or [""]
    pad = " " * len(label)
    return "\n".join([label + lines[0]] + [pad + line for line in lines[1:]])


def show(path: str) -> None:
    with open(path) as file:
        out = json.load(file)
    status = "SOLVED" if out["success"] else f"FAILED ({out['error']})"
    print(
        f"=== task {out['task_id']} · {out['benchmark']} · {status} · "
        f"{out['iterations']} steps · {out['total_input_tokens']} in / "
        f"{out['total_output_tokens']} out tokens · {out['total_time_seconds']:.1f}s ==="
    )
    for step in out["steps"]:
        print(
            f"\n--- step {step['step']} · {step['model_name']} · "
            f"{step['input_tokens']} in / {step['output_tokens']} out · "
            f"{step['request_time_ms'] / 1000:.1f}s · {step['retries']} retries ---"
        )
        print(indent(step["llm_output"], "LLM:    "))
        print(indent(step["sandbox_output"], "RESULT: "))
    if out["success"]:
        print("\n" + indent(out["solution"], "SOLUTION: "))


if __name__ == "__main__":
    show(sys.argv[1])
