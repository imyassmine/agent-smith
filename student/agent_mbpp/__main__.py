import argparse, sys
from pathlib import Path
from .models import MBPPTaskInput
from pydantic import ValidationError
from .loop import run_agent, build_task_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="MBPP code agent")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--max-iterations", default=10, type=int)
    args = parser.parse_args()
    try:
        raw = Path(args.task_file).read_text()
        task = MBPPTaskInput.model_validate_json(raw)
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 1
    except ValidationError as e:
        print(f"Validation of task file failed: {e}", file=sys.stderr)
        return 1
    try:
        output = run_agent(
            provider_url=args.provider_url,
            model_name=args.model_name,
            task=build_task_prompt(task),
            task_id=str(task.task_id),
            benchmark="mbpp",
            max_iterations=args.max_iterations,
        )
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output.model_dump_json(indent=2))
    except (KeyboardInterrupt, SystemExit) as e:
        print(f"Request to exit: {e}", file=sys.stderr)
        return 130 if KeyboardInterrupt else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
