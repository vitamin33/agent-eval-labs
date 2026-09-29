# Implementation plan — agent-checkpoint

Same contract as experiments 1 and 2: each task states what it produces, what
"done" means, and the exact command that proves it. Gate G2 executes every
offline command whose deliverable exists.

## What is reused unchanged

From experiment 1: `config.Config` (constructed by `ckpt_config.py` from this
experiment's own `config.yaml`), `provider.py` (DeepSeek tool-calling client),
`metrics.Rate` and `wilson`, `hypotheses.compare`, the gate registry.

From experiment 2: `env.Env` (subclassed, not copied), `inject.py` verbatim
(corruption, fingerprint, same-subject recheck, discoverability lambdas),
the task wording, the answer coercion rule, the staged stopping rule.

New: fixtures with Amendment A1's corrections, the `reconcile` primitive,
the enforced-checkpoint wrapper in the loop, the naive solvers for the
answer-relevance gate, silent-failure and usage metrics, gates G9 and G10.

## Estimated budget

Experiment 2's stage-2 tokens, repriced at the current Flash rates (peak):

| mode | tokens in / cache hit / out per trajectory | cost per trajectory |
|---|---|---|
| clean | 15,870 / 13,770 / 3,352 | $0.00473 |
| inject | 17,819 / 15,536 / 3,720 | $0.00524 |
| inject_verify | 19,250 / 16,869 / 3,836 | $0.00542 |

`inject_enforced` wraps every tool result with the reconciled truth, so its
input roughly doubles; most of that is served from cache at $0.006 per
million, so the per-trajectory cost should land near $0.007. Rounded up:

| stage | trajectories | estimate |
|---|---|---|
| 0 (pilot) | 8 | $0.05 |
| 1 (k=2) | 64 | $0.45 |
| 2 (k=5) | 160 | $1.10 |
| **total** | **232** | **$1.60**, ceiling $5 |

The pilot re-measures tokens per step before stage 1 commits.

## Tasks

### P1 — fixtures and environment

- **Deliverable:** `ckpt_fixtures.py`, `ckpt_env.py`
- **Acceptance:** Amendment A1's fixtures; `Env3` subclasses experiment 2's
  environment, adds `reconcile(tool, args)` returning the authoritative
  result and never injected; deterministic snapshot.
- **Verify:** `.venv/bin/python -m pytest tests/test_ckpt_env.py -q`

### P2 — tasks and naive solvers

- **Deliverable:** `ckpt_tasks.py`
- **Acceptance:** the eight tasks over the new fixtures with deterministic
  `check(env, answer)`; one primary injection kind per task; a scripted naive
  solver per task that returns the correct answer clean.
- **Verify:** `.venv/bin/python -m pytest tests/test_ckpt_tasks.py -q`

### P3 — answer-relevance and discoverability

- **Deliverable:** `relevance.py`
- **Acceptance:** for every (task, kind): the naive solver is correct clean;
  with the injection applied at the first eligible call it is wrong; the
  corrupt value differs from the truth, keeps its shape, and a scripted
  sequence exposes it. Exit 1 on any failure.
- **Verify:** `.venv/bin/python experiments/agent-checkpoint/relevance.py`

### P4 — prompts and tool surfaces

- **Deliverable:** `ckpt_prompts.py`
- **Acceptance:** `inject_tool` differs from `inject` by exactly the
  `reconcile` tool definition; `inject_enforced` differs by exactly
  `CHECKPOINT_BLOCK`; a test reconstructs each from `inject`.
- **Verify:** `.venv/bin/python -m pytest tests/test_ckpt_prompt_diff.py -q`

### P5 — agent loop and records

- **Deliverable:** `ckpt_agent.py`, `ckpt_mock.py`
- **Acceptance:** schema v2 records (per-step cache hit/miss/write, served
  model, pricing tier, config sha256, harness commit); reconcile calls
  unwrapped for same-subject detection; enforced checkpoints wrap every
  non-submit result and never count as detection; a planted false green
  (wrong outcome, `claims_success=true`) is recorded as one.
- **Verify:** `.venv/bin/python -m pytest tests/test_ckpt_agent.py -q`

### P6 — metrics and hypotheses

- **Deliverable:** `ckpt_metrics.py`, `ckpt_hypotheses.py`
- **Acceptance:** silent failure rate, false-green rate, outcome pass, usage
  rate, detection, contamination, cost multipliers, cost per avoided silent
  failure, all with Wilson intervals and `null` on empty denominators;
  thresholds held against RESEARCH.md by a test; stopping rule at 99/95.
- **Verify:** `.venv/bin/python -m pytest tests/test_ckpt_metrics.py tests/test_ckpt_hypotheses.py -q`

### P7 — runner and report

- **Deliverable:** `ckpt_runner.py`, `ckpt_report.py`
- **Acceptance:** stages 0/1/2, append-only JSONL, refuses to append to an
  existing file; a dry run with the mock provider produces a valid file the
  report can render.
- **Verify:** `.venv/bin/python experiments/agent-checkpoint/ckpt_runner.py --dry-run --stage 1 --out build/ckpt-dry.jsonl --quiet && .venv/bin/python experiments/agent-checkpoint/ckpt_report.py --results build/ckpt-dry.jsonl --out build/ckpt-dry-RESULTS.md`

### P8 — substrate gate

- **Deliverable:** gate `G9` in `gates.py`
- **Acceptance:** deterministic env; every pair answer-relevant and
  discoverable; mode-difference tests green; pre-registration precedes data
  (git); if a stage-0 file exists, every task's injection fires on its
  recorded tool sequence.
- **Verify:** `.venv/bin/python gates.py --gate G9`

### P9 — pilot

- **Deliverable:** `results/ckpt-stage0-*.jsonl`, `CALIBRATION.md` stage 0
- **Acceptance:** 8 clean trajectories; ceiling >= 70%; firing check 8/8;
  tokens per step measured and the stage-1 estimate confirmed.
- **Verify:** `.venv/bin/python gates.py --gate G9`

### P10 — stages 1 and 2, report, run gate

- **Deliverable:** `results/ckpt-stage{1,2}-*.jsonl`, `RESULTS.md`
- **Acceptance:** served model equals the pin; step-cap rate under 10%;
  gate recomputes the silent failure rate independently of the metrics
  module; stopping rule applied and its level stated.
- **Verify:** `.venv/bin/python gates.py --gate G10`

### P11 — adversarial review and write-up

- **Deliverable:** `REVIEW.md`, `README.md` section, charts
- **Acceptance:** every risk with a verdict and a test that runs; at minimum:
  can the checkpoint field leak which call was corrupted; can reconcile be
  counted as detection without matching the subject; can a wrapped result be
  graded differently from a bare one; is the cost multiplier inflated by the
  wrapper alone (clean-with-checkpoint is not run, stated as a limit).
- **Verify:** `.venv/bin/python gates.py --gate G10`

## Out of scope

A second model. The harness keeps the model as a config field so a
cross-model replication of `inject` and `inject_enforced` can run as a
separate stage; that stage is planned, budgeted and pre-registered on its own.

### P12 — stage 3, cross-model replication (pre-registered in RESEARCH.md)

- **Deliverable:** `config.haiku45.yaml`, `config.gemini-flash.yaml`,
  `config.stage3-deepseek.yaml`; Anthropic tool calling and a generic
  OpenAI-compatible provider in `provider.py`; `inject_wrapped` arm.
- **Acceptance:** the translation to and from the Anthropic message shape is
  test-held; a dry run with each config completes; the per-model report
  evaluates H6–H9 with their thresholds held against RESEARCH.md.
- **Verify:** `.venv/bin/python -m pytest tests/test_provider_tools.py tests/test_ckpt_hypotheses.py -q && .venv/bin/python experiments/agent-checkpoint/ckpt_runner.py --dry-run --stage 3 --config experiments/agent-checkpoint/config.haiku45.yaml --out build/ckpt-dry-haiku.jsonl --quiet && .venv/bin/python experiments/agent-checkpoint/ckpt_report.py --results build/ckpt-dry-haiku.jsonl --out build/ckpt-dry-haiku-RESULTS.md`
