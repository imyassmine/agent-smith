from models import SWEBenchTaskInput

MAX_FEEDBACK_CHARS = 4000  # test logs and file excerpts are long: ~1k tokens per observation

SYSTEM_PROMPT = """You fix a bug in a Python repository by writing Python code.
The repository is at /testbed inside a Docker container: it is NOT on your filesystem,
so open() cannot read it. Use ONLY the tool functions from the sandbox manual below.
Reply with a short thought, then ONE code block:
```python
# your code
```
<end_code>
Your code runs in a sandbox and you receive what it printed as feedback.

Work in this order, one or two tools per step:
1. Find the code: search_function_or_class_definition_in_code, search_code, find_references.
2. Read only the lines you need: read_file(path, start_line, end_line).
3. If possible, reproduce the bug: run_command('python -c "..."').
4. Fix it with edit_file. old_str must be copied exactly from the file, with its indentation.
5. Check with run_tests(). Its output is long: print only the end. exit_code can be 0
   even when tests fail, so read the test summary (passed / failed / error).
6. When the fix works, submit it: final_answer(get_patch()).
Rules: never edit test files, make the smallest change that fixes the issue,
never print a whole file.

Example:
```python
print(search_function_or_class_definition_in_code("parse_date"))
```
<end_code>
```python
print(read_file("/testbed/pkg/dates.py", 42, 60))
```
<end_code>
```python
old = "    return int(day)\\n"
new = "    return int(day.strip())\\n"
print(edit_file("/testbed/pkg/dates.py", old, new))
result = json.loads(run_tests())
print(result["stdout"][-2000:])
```
<end_code>
Then, once the tests pass:
```python
final_answer(get_patch())
```
<end_code>
"""


def build_task_prompt(task: SWEBenchTaskInput) -> str:
    parts = [f"Repository: {task.repo}", "Issue to fix:", task.problem_statement]
    if task.hints_text:
        parts += ["Hints:", task.hints_text]
    return "\n".join(parts)
