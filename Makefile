# agent-eval-labs — developer entry points.
# Every target is safe to run offline except `run-live`, which calls the API.

PY := .venv/bin/python
UV := $(shell command -v uv 2>/dev/null)

DRY := build/reproduce-dry
.PHONY: help venv test gates reproduce-dry reproduce-live run-live run-live-inject report clean

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

reproduce-live: .venv/bin/python ## the real experiment, end to end: both arms, report, gate G4 (~250 calls, ~$0.75, ~2.5h)
	$(MAKE) run-live-inject
	$(MAKE) run-live
	$(MAKE) report
	$(PY) gates.py --gate G4

run-live: .venv/bin/python ## arm 1 — generation: baseline vs self-verify (~150 calls)
	$(PY) experiments/verifier-gap/runner.py --live --arm generation

run-live-inject: .venv/bin/python ## arm 2 — verify supplied answers (~100 calls)
	$(PY) experiments/verifier-gap/runner.py --live --arm injection

# The published run is the newest one the API served under the pinned model id;
# every other run of the same arm is passed as a replication comparison, so a
# run that exists can never be absent from the report. `pick.py` does the
# selection and prints both, and refuses if no run is on the pin.
report: .venv/bin/python ## regenerate tables, charts, cost and replication from the raw runs
	$(PY) experiments/verifier-gap/report.py $$($(PY) experiments/verifier-gap/pick.py)

.venv/bin/python:
	@$(MAKE) venv

post-check: .venv/bin/python ## publication gate for a post: make post-check POST=path/to/post.mdx [EXTRA=dir-of-other-posts]
	@test -n "$(POST)" || { echo "usage: make post-check POST=path/to/post.mdx"; exit 2; }
	$(PY) tools/post_check.py "$(POST)" $(if $(EXTRA),--extra "$(EXTRA)",)

source-pack: .venv/bin/python ## every number a post may cite, from the published artifacts
	@$(PY) tools/post_check.py --source-pack

persona-prompt: ## print the six-persona read-through prompt for a subagent
	@cat docs/templates/persona_round_prompt.md

clean: ## remove caches and build output
	rm -rf .pytest_cache **/__pycache__ __pycache__ build
