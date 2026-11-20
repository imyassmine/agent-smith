import builtins
import importlib
import io
import json
import os
import signal
import sys
import threading
import time
import traceback

try:
    import resource
except ImportError:
    resource = None

# audit events we always refuse
BLOCKED_EVENT_PREFIXES = (
    "socket.",
    "subprocess.",
    "os.system",
    "os.exec",
    "os.posix_spawn",
    "os.spawn",
    "os.fork",
    "os.forkpty",
    "os.kill",
    "os.killpg",
    "pty.",
    "ctypes.",
    "winreg.",
    "webbrowser.",
)
BLOCKED_MODULES = {"_posixsubprocess", "_ctypes", "_socket", "_ssl",
                "_multiprocessing"}

PATH_EVENTS = {
    "os.listdir", "os.scandir", "os.remove", "os.rmdir", "os.mkdir",
    "os.chmod", "os.chown", "os.chdir", "os.truncate", "os.utime",
    "os.rename", "os.link", "os.symlink", "shutil.rmtree", "glob.glob",
}
REMOVED_BUILTINS = {"input", "breakpoint", "exit", "quit", "help", "copyright",
                    "credits", "license"}
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


# baseexception so except Exception in llm code can't catch it
class FinalAnswer(BaseException):
    def __init__(self, value):
        super().__init__(value)
        self.value = value


class Channel:
    def __init__(self):
        self._in = os.fdopen(os.dup(0), "r", encoding="utf-8")
        self._out = os.fdopen(os.dup(1), "w", encoding="utf-8")
        devnull = os.open(os.devnull, os.O_RDWR)
        # private copies so the code cant mess with the protocol
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        self._lock = threading.Lock()

    def send(self, **message):
        line = json.dumps(message)
        with self._lock:
            self._out.write(line + "\n")
            self._out.flush()

    def recv(self):
        line = self._in.readline()
        if not line:
            raise EOFError("parent closed the channel")
        return json.loads(line)


class OutputStream(io.TextIOBase):
    def __init__(self, channel):
        self._channel = channel
        self._buffer = []

    def writable(self):
        return True

    def write(self, text):
        if not isinstance(text, str):
            raise TypeError(f"write() argument must be str, not {type(text).__name__}")
        self._buffer.append(text)
        if "\n" in text or sum(map(len, self._buffer)) > 4096:
            self.flush()
        return len(text)

    def flush(self):
        if self._buffer:
            self._channel.send(type="output", data="".join(self._buffer))
            self._buffer = []


def is_import_allowed(name, patterns):
    for pattern in patterns:
        if pattern == name:
            return True
        if pattern.endswith(".*") and name.startswith(pattern[:-2] + "."):
            return True
    return False


def is_inside(path, roots):
    real = os.path.realpath(path)
    return any(real == root or real.startswith(root.rstrip(os.sep) + os.sep)
               for root in roots)


def preimport(patterns):
    for pattern in patterns:
        base = pattern[:-2] if pattern.endswith(".*") else pattern
        try:
            importlib.import_module(base)
        except ImportError:
            pass


def make_audit_hook(roots, stdlib_roots):
    def audit(event, args):
        if event.startswith(BLOCKED_EVENT_PREFIXES):
            raise PermissionError(f"Sandbox: '{event}' is not allowed")
        if event == "import" and args[0].split(".")[0] in BLOCKED_MODULES:
            raise ImportError(f"Sandbox: import of '{args[0]}' is not allowed")
        if event == "open":
            path, mode, flags = args
            if path is None or isinstance(path, int):
                return
            path = os.fsdecode(path)
            if is_inside(path, roots):
                return
            writing = (mode is not None and any(c in str(mode) for c in "wax+")) or (
                flags is not None and flags & WRITE_FLAGS)
            if not writing and is_inside(path, stdlib_roots):
                return
            raise PermissionError(
                f"Sandbox: access to '{path}' is not allowed (allowed: {', '.join(roots)})")
        if event in PATH_EVENTS:
            for path in args:
                if isinstance(path, (str, bytes)) and not is_inside(os.fsdecode(path), roots):
                    raise PermissionError(
                        f"Sandbox: access to '{os.fsdecode(path)}' is not allowed")
    return audit


def limit_memory(max_mb, channel):
    limit = max_mb * 1024 * 1024
    if resource is None:
        return
    try:
        # linux only, the watchdog below covers macos
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ValueError, OSError):
        pass
    unit = 1 if sys.platform == "darwin" else 1024

    def watchdog():
        while True:
            if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit > limit:
                channel.send(type="memory_exceeded", limit_mb=max_mb)
                os._exit(3)
            time.sleep(0.05)
    threading.stack_size(256 * 1024)
    threading.Thread(target=watchdog, daemon=True).start()


def clean_traceback(exc):
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename != __file__]
    message = "".join(traceback.format_exception_only(type(exc), exc))
    if not frames:
        return message
    return ("Traceback (most recent call last):\n"
            + "".join(traceback.format_list(frames)) + message)


def build_namespace(channel, stream, config, functions, roots):
    patterns = config["authorized_imports"]
    real_import, real_open = builtins.__import__, builtins.open

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0:
            raise ImportError("relative imports are not allowed in the sandbox")
        if not is_import_allowed(name, patterns):
            raise ImportError(
                f"Import of '{name}' is not allowed in the sandbox. "
                f"Allowed modules: {', '.join(patterns)}")
        return real_import(name, globals, locals, fromlist, level)

    def guarded_open(file, mode="r", *args, **kwargs):
        if not isinstance(file, int) and not is_inside(os.fsdecode(file), roots):
            raise PermissionError(
                f"Sandbox: access to '{file}' is not allowed (allowed: {', '.join(roots)})")
        return real_open(file, mode, *args, **kwargs)

    safe_builtins = dict(vars(builtins))
    for name in REMOVED_BUILTINS:
        safe_builtins.pop(name, None)
    safe_builtins["__import__"] = guarded_import
    safe_builtins["open"] = guarded_open

    def final_answer(answer):
        if not isinstance(answer, str):
            raise TypeError(f"final_answer() expects a string, got {type(answer).__name__}")
        raise FinalAnswer(answer)

    namespace = {"__builtins__": safe_builtins, "__name__": "__main__",
                 "final_answer": final_answer}
    for spec in functions:
        namespace[spec["name"]] = make_remote_function(channel, stream, spec)
    return namespace


def make_remote_function(channel, stream, spec):
    params = spec["params"]

    def remote(*args, **kwargs):
        if len(args) > len(params):
            raise TypeError(f"{spec['name']}() takes {len(params)} arguments "
                            f"({len(args)} given)")
        for name, value in zip(params, args):  # noqa: B905
            if name in kwargs:
                raise TypeError(f"{spec['name']}() got multiple values for '{name}'")
            kwargs[name] = value
        try:
            json.dumps(kwargs)
        except TypeError as error:
            raise TypeError(f"{spec['name']}(): arguments must be JSON values: {error}") from None
        stream.flush()
        channel.send(type="call", kind=spec["kind"], name=spec["name"], arguments=kwargs)
        reply = channel.recv()
        if not reply.get("ok"):
            raise RuntimeError(f"{spec['name']}() failed: {reply.get('error')}")
        return reply.get("result")

    remote.__name__ = spec["name"]
    remote.__doc__ = spec.get("doc", "")
    return remote


def run_code(code, namespace, channel, stream):
    try:
        compiled = compile(code, "<agent_code>", "exec")
        exec(compiled, namespace)
    except FinalAnswer as answer:
        stream.flush()
        channel.send(type="final_answer", value=answer.value)
        return
    except SystemExit as exit_:
        stream.flush()
        code_ = exit_.code if isinstance(exit_.code, (int, str, type(None))) else str(exit_.code)
        channel.send(type="system_exit", code=code_)
        return
    except KeyboardInterrupt:
        stream.flush()
        channel.send(type="keyboard_interrupt")
        return
    except BaseException as error:
        stream.write(clean_traceback(error))
    stream.flush()
    channel.send(type="done")


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    channel = Channel()
    init = channel.recv()
    config = init["config"]
    roots = [os.path.realpath(d) for d in config["allowed_directories"]]
    stdlib_roots = {os.path.realpath(p) for p in
                    (os.path.dirname(os.__file__), sys.base_prefix, sys.prefix)}

    preimport(config["authorized_imports"])
    stream = OutputStream(channel)
    namespace = build_namespace(channel, stream, config, init["functions"], roots)
    limit_memory(config["max_memory_mb"], channel)
    sys.stdout = sys.stderr = sys.__stdout__ = sys.__stderr__ = stream
    sys.addaudithook(make_audit_hook(roots, stdlib_roots))  # can't be removed once added
    channel.send(type="ready")

    while True:
        try:
            message = channel.recv()
        except EOFError:
            return
        if message.get("type") == "exec":
            run_code(message["code"], namespace, channel, stream)


if __name__ == "__main__":
    main()
