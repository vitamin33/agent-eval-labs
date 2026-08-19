# agent-eval-labs — developer entry points.
# Every target is safe to run offline except `run-live`, which calls the API.

PY := .venv/bin/python
UV := $(shell command -v uv 2>/dev/null)

DRY := build/reproduce-dry
.PHONY: help venv test gates reproduce-dry report clean

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

reproduce-dry: .venv/bin/python ## full offline reproduction — no API key needed
	@rm -rf $(DRY) && mkdir -p $(DRY)
	$(PY) experiments/verifier-gap/runner.py --dry-run --out $(DRY)/run.jsonl --quiet
	$(PY) experiments/verifier-gap/report.py --results $(DRY)/run.jsonl \
	    --out-md $(DRY)/RESULTS.md --assets $(DRY)/assets --no-readme
	$(PY) experiments/verifier-gap/sensitivity.py --results $(DRY)/run.jsonl
	@echo
	@echo "Reproduced offline into $(DRY)/ using MOCKED responses."
	@echo "These numbers are synthetic. Real results require: make run-live"

run-live: .venv/bin/python ## the real matrix — needs ANTHROPIC_API_KEY, ~150 calls
	$(PY) experiments/verifier-gap/runner.py --live

report: .venv/bin/python ## regenerate table + charts from the newest live run
	$(PY) experiments/verifier-gap/report.py \
	    --results $$(ls -t experiments/verifier-gap/results/run-live-*.jsonl | head -1)

.venv/bin/python:
	@$(MAKE) venv

clean: ## remove caches and build output
	rm -rf .pytest_cache **/__pycache__ __pycache__ build
