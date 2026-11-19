# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ LAYOUT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT			= \033[0m
GREEN			= \033[1;32m
CYAN			= \033[1;36m

define ANIMATION
				@for frame in ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏; do \
				printf "$$frame $(1)...\r"; \
				sleep 0.02; \
				done; \
				printf "\n"
ende


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

install:
				$(call ANIMATION,Installing project dependencies)
				@uv sync

run:
				@uv run python -m $(ARGS)

debug:
				@uv run python -m pdb -m $(ARGS)

clean:
				$(call ANIMATION,Removing compiled files and caches)
				@rm -rf __pycache__ */*/*/__pycache__ */__pycache__  */*/__pycache__ .pytest_cache .mypy_cache

lint:
				@uv run ruff check src tests mcp_tools_mbpp.py
				@uv run ruff format --check src tests mcp_tools_mbpp.py

lint-strict:
				@uv run ruff check src tests mcp_tools_mbpp.py
				@uv run ruff format --check src tests mcp_tools_mbpp.py

test:
				@uv run python -m pytest tests -v


help:
				@printf "Usage: make [target]\n"
				@printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
				@printf "$(CYAN)install$(DEFAULT)		- Install project dependencies\n"
				@printf "$(CYAN)run$(DEFAULT)		- Run the agent (use ARGS=\"<args>\" to pass agent name)\n"
				@printf "$(CYAN)debug$(DEFAULT)		- Run the agent in debug mode (use ARGS=\"<args>\" to pass agent name)\n"
				@printf "$(CYAN)clean$(DEFAULT)		- Remove compiled Python files and caches\n"
				@printf "$(CYAN)lint$(DEFAULT)		- Run linter and type checker to ensure code quality\n"
				@printf "$(CYAN)lint-strict$(DEFAULT)	- Run linter and type checker with strict settings\n"
				@printf "$(CYAN)test$(DEFAULT)		- Run tests using pytest\n"
				@printf "$(CYAN)help$(DEFAULT)		- Show this help message\n"

.PHONY:			install run debug clean lint lint-strict test help
