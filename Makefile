SRC_DIR = src
TESTS_DIR = tests
ARGS =
BENCH = mbpp
LIMIT = $(if $(filter swebench,$(BENCH)),900,120)
TASK = $(CURDIR)/cache/$(BENCH)_task.json
SOLUTION = $(CURDIR)/cache/$(BENCH)_solution.json
MOULINETTE = uv run --python 3.12 moulinette_eval

ESC = $(shell printf '\033')
BOLD = $(ESC)[1m
PURPLE = $(ESC)[35m
GREEN = $(ESC)[32m
RED = $(ESC)[31m
GREY = $(ESC)[90m
CYAN = $(ESC)[36m
RESET = $(ESC)[0m

STEP = $(BOLD)$(PURPLE)➜
OK = $(BOLD)$(GREEN)✔
KO = $(BOLD)$(RED)✘

help: logo
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "help" "show this help"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "install" "install dependencies with uv sync"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "run" "run a module, ex: make run ARGS=\"agent_mbpp --task-file t.json ...\""
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "debug" "same as run but inside pdb"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "test" "run all tests with pytest"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "eval" "dump + run agent + validate, ex: make eval BENCH=swebench SEED=3"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "show" "pretty-print the last solution.json, ex: make show BENCH=swebench"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "lint" "check code and formatting (ruff)"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "lint-strict" "same as lint for now"
	@printf "  $(CYAN)%-16s$(RESET) %s\n" "clean" "remove python caches"

logo:
	@printf "$(BOLD)$(PURPLE)%s\n" '  ____  __  __ ___ _____ _   _ '
	@printf "%s\n" ' / ___||  \/  |_ _|_   _| | | |'
	@printf "%s\n" ' \___ \| |\/| || |  | | | |_| |'
	@printf "%s\n" '  ___) | |  | || |  | | |  _  |'
	@printf "%s$(RESET)\n" ' |____/|_|  |_|___| |_| |_| |_|'
	@printf "$(GREY)   Agent Smith$(RESET)\n\n"

install:
	@echo "$(STEP) Installing dependencies$(RESET)"
	@uv sync && echo "$(OK) Install done !$(RESET)" || (echo "$(KO) Install failed$(RESET)"; exit 1)

run:
	@echo "$(STEP) Running $(ARGS) ...$(RESET)"
	@uv run python -m $(ARGS)

debug:
	@echo "$(STEP) Debugging $(ARGS) ...$(RESET) $(GREY)(n next, s step, p x print, c continue)$(RESET)"
	@uv run python -m pdb -m $(ARGS)

test:
	@echo "$(STEP) Running tests ...$(RESET)"
	@uv run python -m pytest $(TESTS_DIR) -v && echo "$(OK) All tests passed !$(RESET)" || (echo "$(KO) Some tests failed$(RESET)"; exit 1)

lint:
	@echo "$(STEP) running ruff check ...$(RESET)"; uv run ruff check $(SRC_DIR) $(TESTS_DIR); c=$$?; \
	echo "$(STEP) running ruff format --check ...$(RESET)"; uv run ruff format --check $(SRC_DIR) $(TESTS_DIR); f=$$?; \
	if [ $$c -eq 0 ] && [ $$f -eq 0 ]; then echo "$(OK) Lint OK !$(RESET)"; \
	else echo "$(KO) Lint failed$(RESET) $(GREY)(fix with: uv run ruff format .)$(RESET)"; exit 1; fi

eval:
	@echo "$(STEP) 1/3 dump $(BENCH) task$(RESET)"
	@cd moulinette && $(MOULINETTE) dump $(BENCH) $(if $(SEED),--seed $(SEED)) --output $(TASK)
	@echo "$(STEP) 2/3 run agent ($(LIMIT)s)$(RESET)"
	@uv run --project moulinette --python 3.12 moulinette_eval run-agent $(LIMIT) \
		"uv run python -m agent_$(BENCH) --task-file $(TASK) --output $(SOLUTION) $(if $(MODEL),--model-name $(MODEL)) $(if $(URL),--provider-url $(URL))"
	@echo "$(STEP) 3/3 validate$(RESET)"
	@cd moulinette && $(MOULINETTE) validate $(BENCH) $(TASK) $(SOLUTION)

show:
	@uv run python src/show.py $(SOLUTION)

# todo: add stricter checks here later
lint-strict: lint

clean:
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	@echo "$(OK) Cleaned !$(RESET)"

.PHONY: help logo install run debug test eval show lint lint-strict clean
