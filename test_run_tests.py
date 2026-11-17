from mcp_tools_mbpp import run_tests   # sans le décorateur, ou avec s'il reste appelable

print(run_tests("def add(a, b): return a + b", ["assert add(1, 2) == 3"]))   # succès
print(run_tests("def add(a, b): return a - b", ["assert add(1, 2) == 3"]))   # AssertionError
print(run_tests("def add(a, b) return a + b", ["assert add(1, 2) == 3"]))    # SyntaxError
print(run_tests("while True: pass", []))                                      # timeout (30 s)