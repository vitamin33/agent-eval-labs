# agent-eval-labs — developer entry points.
# Every target is safe to run offline except `run-live`, which calls the API.

PY := .venv/bin/python
UV := $(shell command -v uv 2>/dev/null)

DRY := build/reproduce-dry
.PHONY: help venv test gates reproduce-dry reproduce-live run-live run-live-inject report clean ckpt-dry ckpt-live ckpt-report

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

# --- experiment 3: deterministic checkpoints -------------------------------- #
ckpt-dry: .venv/bin/python ## exp3 offline: mock matrix + report into build/ (synthetic numbers)
	@rm -f build/ckpt-dry.jsonl && mkdir -p build
	$(PY) experiments/agent-checkpoint/ckpt_runner.py --dry-run --stage 1 --out build/ckpt-dry.jsonl --quiet
	$(PY) experiments/agent-checkpoint/ckpt_report.py --results build/ckpt-dry.jsonl --out build/ckpt-dry-RESULTS.md
	$(PY) experiments/agent-checkpoint/relevance.py

ckpt-live: .venv/bin/python ## exp3 live stage: make ckpt-live STAGE=0|1|2 (0 = 8 clean, 1 = 64, 2 = 160 trajectories)
	@test -n "$(STAGE)" || { echo "usage: make ckpt-live STAGE=0|1|2"; exit 2; }
	$(PY) experiments/agent-checkpoint/ckpt_runner.py --live --stage $(STAGE)

ckpt-report: .venv/bin/python ## exp3 RESULTS.md from the newest completed stage: make ckpt-report RESULTS=path LEVEL=99|95
	@test -n "$(RESULTS)" || { echo "usage: make ckpt-report RESULTS=experiments/agent-checkpoint/results/<file>.jsonl [LEVEL=99|95]"; exit 2; }
	$(PY) experiments/agent-checkpoint/ckpt_report.py --results "$(RESULTS)" --level $(or $(LEVEL),99)
	$(PY) gates.py --gate G10

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
