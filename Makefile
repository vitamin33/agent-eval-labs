# agent-eval-labs — developer entry points.
# Every target is safe to run offline except `run-live`, which calls the API.

PY := .venv/bin/python
UV := $(shell command -v uv 2>/dev/null)

.PHONY: help venv test gates lint clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv: ## create .venv and install dependencies
ifeq ($(UV),)
	python3 -m venv .venv && $(PY) -m pip install -e ".[dev]"
else
	uv venv .venv && uv pip install --python $(PY) -e ".[dev]"
endif

test: ## run the unit test suite
	$(PY) -m pytest

gates: ## run every registered phase gate
	$(PY) gates.py --all

clean: ## remove caches
	rm -rf .pytest_cache **/__pycache__ __pycache__
