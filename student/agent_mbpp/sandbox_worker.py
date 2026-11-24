import contextlib, io, json, sys, traceback

# Le canal de dialogue est gardé à part : pendant l'exécution, sys.stdout est
# redirigé vers un tampon pour capturer les print() du code du modèle.
CHANNEL = sys.stdout


class FinalAnswer(BaseException):
    def __init__(self, value: str) -> None:
        self.value = value


def final_answer(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(
            f"final_answer() expects a string, got {type(value).__name__}"
        )
    raise FinalAnswer(value)


def send(message: dict) -> None:
    CHANNEL.write(json.dumps(message) + "\n")
    CHANNEL.flush()


def receive() -> dict:
    line = sys.stdin.readline()
    if not line:  # l'agent a fermé le canal : on s'arrête
        raise SystemExit
    return json.loads(line)


def make_tool(name: str, params: list[str]):
    """Fonction qui transmet l'appel à l'agent, qui parle au serveur MCP."""

    def tool(*args, **kwargs):
        arguments = {**dict(zip(params, args)), **kwargs}
        send({"type": "tool_call", "name": name, "arguments": arguments})
        reply = receive()
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply["result"]

    tool.__name__ = name
    return tool


def main() -> None:
    init = receive()
    namespace = {"__name__": "__main__"}
    for name, params in init["tools"].items():
        namespace[name] = make_tool(name, params)
    namespace["final_answer"] = final_answer
    namespace.update(init["namespace"])
    while True:
        code = receive()["code"]
        buffer = io.StringIO()
        answer = None
        try:
            with contextlib.redirect_stdout(buffer):
                exec(code, namespace)
        except FinalAnswer as f:
            answer = f.value
        except Exception:
            buffer.write(traceback.format_exc())
        send({"type": "result", "output": buffer.getvalue(), "answer": answer})


if __name__ == "__main__":
    main()
