import io, signal, contextlib, traceback
from pydantic import BaseModel
from .mcp_client import list_tools, build_tool_wrappers, build_manual


EXEC_TIMEOUT = 30  # secondes

class FinalAnswer(BaseException):
    def __init__(self, value: str) -> None:
        self.value = value


def final_answer(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(
            f"final_answer() expects a string, got {type(value).__name__}"
        )
    raise FinalAnswer(value)

class ExecTimeout(BaseException):
    pass


def _timeout(_signum, _frame):
    raise ExecTimeout()


class Sandbox:
    def __init__(self, extra_namespace):
        tools = list_tools()
        self.manual = build_manual(tools)
        self.namespace: dict = {"__name__": "__main__"}
        self.namespace.update(build_tool_wrappers(tools))
        self.namespace.update({"final_answer": final_answer})
        self.namespace.update(extra_namespace)

    def execute_safe_code(self, code: str) -> tuple[str, str | None]:
        buffer = io.StringIO()
        signal.signal(
            signal.SIGALRM, _timeout
        )  # enregistre la fonction à appeler quand le signal à surveiller arrive
        signal.alarm(
            EXEC_TIMEOUT
        )  # programme une alarme pour qu'elle se déclenche après EXEC_TIMEOUT
        answer = None
        try:
            with contextlib.redirect_stdout(buffer):
                exec(code, self.namespace)
        except ExecTimeout:
            buffer.write("Execution hit the timeout and output is partial")
        except FinalAnswer as f:
            answer = f.value
        except Exception:
            buffer.write(traceback.format_exc())
        finally:
            signal.alarm(0)  # annule l'alarme restante
        return buffer.getvalue(), answer
