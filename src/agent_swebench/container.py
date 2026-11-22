import subprocess

EVAL_SCRIPT_PATH = "/eval.sh"  # must match EVAL_SCRIPT in mcp_tools_swebench.py


def docker(*args: str, stdin: str = "") -> str:
    """Runs a docker command on the host: returns stdout, raises on failure."""
    process = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"docker {args[0]} failed: {process.stderr.strip()}")
    return process.stdout.strip()


def start_container(image: str) -> str:
    return docker("run", "-d", image, "sleep", "infinity")  # prints the container id


def copy_eval_script(container: str, script: str) -> None:
    docker("exec", "-i", container, "bash", "-c", f"cat > {EVAL_SCRIPT_PATH}", stdin=script)


def remove_container(container: str) -> None:
    docker("rm", "-f", container)
