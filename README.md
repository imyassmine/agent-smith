*This activity has been created as part of the 42 curriculum by mosimon.*

# Agent Smith

## Description

Agent Smith is a **code agent**: a program that gives a task to a large language model (LLM),
lets the model write Python code, runs that code in a secure sandbox, and sends the result back
to the model, until the model submits an answer. It follows the
**Thought → Code → Observation** loop.

The agent is evaluated on two benchmarks:

- **MBPP**: write a small Python function that passes given tests
  (limits: 10 iterations, 6k input / 1.5k output tokens, 120 s).
- **SWE-bench Verified**: fix a real bug in a real open-source repository, inside a Docker
  container, and submit the patch (limits: 30 iterations, 300k input / 10k output tokens, 900 s).

The project is built without any agent framework: the loop, the sandbox, the LLM client and the
MCP integration are written from scratch. The sandbox security relies only on the Python
standard library.

## Instructions

### Requirements

- Python 3.10 and [uv](https://docs.astral.sh/uv/)
- Docker Desktop, running (SWE-bench only)
- At least one free API key: [Google AI Studio](https://aistudio.google.com/apikey) and/or
  [OpenRouter](https://openrouter.ai/keys)

### Installation

```bash
make install        # uv sync
```

Create a `.env` file at the root of the repository (it is gitignored). Several keys per provider
can be given, separated by commas; the agent rotates to the next key when one is rate limited:

```bash
GEMINI_API_KEYS=key1,key2
OPENROUTER_API_KEYS=key1
```

The singular form (`OPENROUTER_API_KEY=...`) is also accepted.

### Running the agents

The command used by the evaluation:

```bash
uv run python -m agent_mbpp --task-file task.json --output solution.json \
    --model-name "nvidia/nemotron-3.5-lightning:free" --provider-url "https://openrouter.ai/api/v1"
uv run python -m agent_swebench --task-file task.json --output solution.json \
    --model-name "gemini-flash-lite-latest" \
    --provider-url "https://generativelanguage.googleapis.com/v1beta/openai"
```

`--model-name` and `--provider-url` are optional: without a URL, the provider is found in
`models.json` from the model name; without a model, `default_model` from `models.json` is used.

### Makefile

| Command | What it does |
|---|---|
| `make test` | runs the unit tests (sandbox security, MCP, agent loop with a scripted LLM) |
| `make lint` | checks the code with ruff |
| `make eval` | runs the moulinette on one task: dump → run the agent → validate |
| `make show` | pretty-prints the last `solution.json` step by step |

`make eval` accepts variables: `BENCH=mbpp|swebench`, `SEED=<n>` (reproducible task choice) and
`MODEL=<name>`. Example:

```bash
make eval BENCH=swebench SEED=3 MODEL=inclusionai/ling-3.2-flash:free
make show BENCH=swebench
```

Task and solution files are written to `cache/`. The moulinette needs Python 3.12, which
`make eval` selects by itself; the agent stays on Python 3.10.

### Interactive sandbox

```bash
uv run sandbox sandbox_template.json --mcp-stdio "python mcp_tools_mbpp.py"
```

## System architecture

```
agent-smith/
├── models.json              providers, models and their settings
├── sandbox_template.json    sandbox limits (imports, directories, time, memory)
├── mcp_tools_mbpp.py        MCP server for MBPP (run_tests)
├── mcp_tools_swebench.py    MCP server for SWE-bench (9 tools, work inside a container)
└── src/
    ├── agent_mbpp/
    │   ├── __main__.py      CLI: load the task, start MCP + sandbox, write solution.json
    │   └── loop.py          run_agent(): the shared Thought → Code → Observation loop
    ├── agent_swebench/
    │   ├── __main__.py      CLI, SWE-bench system prompt, task prompt
    │   └── container.py     start / prepare / remove the Docker container
    ├── llm/client.py        OpenAI-compatible client: retries, key rotation, deadline
    ├── sandbox/
    │   ├── sandbox.py       parent side: starts the worker, enforces timeouts, relays MCP calls
    │   ├── worker.py        child process that runs the model's code under restrictions
    │   ├── mcp_client.py    MCP client (stdio or streamable HTTP)
    │   ├── manual.py        builds the tool manual shown to the LLM
    │   └── cli.py           interactive sandbox
    ├── models/              pydantic models: configs, tasks, limits, SolutionOutput
    └── show.py              pretty-printer for solution.json
```

One run, end to end:

```
task.json ──► agent CLI ──► run_agent loop ──► LLM provider (models.json)
                               │   ▲
                         code  ▼   │ feedback
                            Sandbox (parent) ──JSON──► worker process (restricted Python)
                               │
                               └── MCP client ──stdio──► mcp_tools_*.py ──► Docker container
                                                                            (SWE-bench)
solution.json ◄── SolutionOutput (every step, tokens, timings, system prompt)
```

Both agents share the same loop (`run_agent`); only the system prompt, the task prompt, the MCP
server and the limits change.

## Agent loop explanation

`run_agent()` in `src/agent_mbpp/loop.py`:

1. **System prompt**: the benchmark's instructions plus a **manual** generated from the MCP
   server's tool list (signatures and descriptions), so the model knows exactly which functions
   exist.
2. **Thought → Code**: the model answers with a short thought and one ```` ```python ```` block
   ending with `<end_code>`. `<end_code>` and `Observation:` are **stop sequences**: the API stops
   the model there, so it cannot invent the result of its own code.
3. **Observation**: the code runs in the sandbox; what it printed (or its error) is sent back as
   the next user message. Long outputs are truncated (head and tail kept) to save tokens.
4. **Stop**: when the code calls `final_answer(answer)`, or when a limit is reached.

Limits are checked **before** each call, not after:

- **time**: a deadline (timeout minus a safety margin) bounds the LLM call, its retries, the code
  execution and every MCP tool call;
- **input tokens**: the whole conversation is re-sent at each call, so the agent estimates the size
  of the next call and stops if it would go over the budget;
- **output tokens**: `max_tokens` of each call is capped by what is left of the budget;
- **iterations**: at most `max_iterations` steps.

Every step is recorded in `solution.json` (`StepMetrics`): raw LLM output, code sent to the
sandbox, sandbox output, tokens, request time, provider URL, model name and number of retries.
This makes the agent's reasoning fully traceable.

The **LLM client** (`src/llm/client.py`) calls any OpenAI-compatible `/chat/completions` API.
It retries failed calls with exponential backoff, never past the task deadline, and switches to
the next API key of the provider on a 429 (rate limit).

## Sandbox design

The model's code is untrusted, so it runs in a **separate worker process**
(`src/sandbox/worker.py`) started with `python -I -S` and an almost empty environment: the API
keys of the agent are not visible to it. The parent (`src/sandbox/sandbox.py`) and the worker talk
through a JSON message channel on stdin/stdout. Protection is layered, using only the standard
library:

| Protection | How |
|---|---|
| Import allowlist | a guarded `__import__` only allows the modules of `authorized_imports` (e.g. `math`, `re`, `json`); internal modules such as `_socket`, `_posixsubprocess`, `_ctypes` are always blocked |
| Dangerous actions | an **audit hook** (PEP 578, `sys.addaudithook`) blocks `subprocess`, `socket`, `os.system`, `os.exec*`… even when reached indirectly (e.g. `random._os.system`); an audit hook cannot be removed once added |
| Filesystem | `open()` and path events (`os.listdir`, `os.remove`, …) are restricted to `allowed_directories`; the standard library stays readable |
| Builtins | `input`, `breakpoint`, `exit`, `quit`, `help`… are removed |
| Time | the parent waits with a timeout; on timeout the worker is killed and restarted, and the partial output is returned |
| Memory | `RLIMIT_AS` plus a watchdog thread on the resident memory; exceeding the limit returns a `MemoryError` feedback |
| Exits | `SystemExit` and `KeyboardInterrupt` raised by the code become feedback instead of stopping the agent |

Variables persist between steps (the worker keeps its namespace), so the model can build its
solution step by step. If the worker is restarted, the feedback says that variables are lost.

**Tools inside the sandbox**: each MCP tool becomes a plain Python function in the worker. When
the code calls it, the worker sends a `call` message to the parent, which forwards it to the MCP
server and sends the result back. The model's code therefore never gets network or Docker access
itself: only the parent talks to the tools, and the time spent in a tool is bounded by the task
deadline.

## Tool implementation details

Tools are exposed through the **Model Context Protocol (MCP)** with FastMCP servers started over
stdio. The sandbox discovers the tools at startup (`list_tools`), so any MCP server can be
plugged in without changing the agent.

**MBPP** (`mcp_tools_mbpp.py`):

- `run_tests(code, test_list)`: runs the candidate code and the tests **inside a new sandbox**
  (same restrictions as the agent) and returns JSON `{"success": ..., "output": ...}`.

**SWE-bench** (`mcp_tools_swebench.py <container_id>`): every tool runs `docker exec` in the task's
container, in the repository at `/testbed`:

| Tool | Purpose |
|---|---|
| `run_command(command, workdir)` | run a shell command, returns stdout, stderr and exit code |
| `read_file(filepath, start_line, end_line)` | read a file (or a range of lines), with line numbers |
| `edit_file(filepath, old_str, new_str)` | replace one exact, unique occurrence of a string; Python files are checked for syntax errors after the edit |
| `list_files(directory, pattern)` | list files matching a glob |
| `search_code(pattern, file_pattern)` | regex search in the repository |
| `search_function_or_class_definition_in_code(name)` | find where a function or class is defined |
| `find_references(name, filepath, line)` | find the usages of a name |
| `run_tests()` | run the task's evaluation script (`/eval.sh`) |
| `get_patch()` | return the `git diff` of all changes, to submit with `final_answer` |

The SWE-bench agent (`src/agent_swebench/`) starts the task's Docker image
(`docker run -d <image> sleep infinity`), copies the evaluation script into it, connects the MCP
server to that container, runs the loop, and always removes the container at the end. Its system
prompt teaches a methodology: search → read → reproduce → edit → run the tests → submit
`final_answer(get_patch())`.

## Benchmark results and analysis

The full report is in [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md): 5 models compared on the same
SWE-bench tasks (pass/fail, iterations, tokens, time), provider reliability, intermediary metrics,
an ablation study and the conclusions. The `solution.json` files behind it are in the repository.

## Resources

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
  (Yao et al., 2022): the thought / action / observation loop.
- [Executable Code Actions Elicit Better LLM Agents](https://arxiv.org/abs/2402.01030)
  (Wang et al., 2024): using Python code as the agent's action format.
- [SWE-bench](https://arxiv.org/abs/2310.06770) (Jimenez et al., 2023) and
  [swebench.com](https://www.swebench.com/): the benchmark, its Verified subset and leaderboards.
- [SWE-agent](https://arxiv.org/abs/2405.15793) (Yang et al., 2024): agent-computer interfaces
  and tool design for software engineering.
- [Program Synthesis with Large Language Models](https://arxiv.org/abs/2108.07732)
  (Austin et al., 2021): the MBPP dataset.
- [Model Context Protocol specification](https://modelcontextprotocol.io/) and its
  [Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- [PEP 578 – Python Runtime Audit Hooks](https://peps.python.org/pep-0578/) and the Python
  documentation of [`sys.addaudithook`](https://docs.python.org/3/library/sys.html#sys.addaudithook)
  and [`resource`](https://docs.python.org/3/library/resource.html).
- [OpenRouter API](https://openrouter.ai/docs) and the
  [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai) documentation.
- [uv](https://docs.astral.sh/uv/), [Ruff](https://docs.astral.sh/ruff/) and
  [Docker](https://docs.docker.com/) documentation.

### How AI was used

AI was used to understand how LLM systems work (agent loops, tool calling, tokens, providers),
to produce visual representations (diagrams and tables of the architecture), to help with
documentation, and to automate tasks (scripts to test providers and models, Makefile targets).
