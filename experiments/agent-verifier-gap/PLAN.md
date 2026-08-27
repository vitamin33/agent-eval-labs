# Implementation plan — agent-verifier-gap

Same contract as experiment 1: each task states what it produces, what "done"
means, and the exact command that proves it. Gate G2 executes every offline
command whose deliverable exists.

## What is reused unchanged

`config.py`, `provider.py`, `verdict.py`, `metrics.py` (Rate, Wilson,
summarize), `hypotheses.py`, and the whole gate registry carry over. Only the
substrate is new: an environment, a tool loop, and trajectory-level metrics.

## Estimated budget

200 trajectories x ~8 steps = ~1,600 calls. Agent steps are short decisions,
not 30k-token essays, so ~1,500-2,500 output tokens each. Roughly **$4-7** and
**2-3 hours** at DeepSeek pricing. A pilot sizes this before the full run —
the lesson from experiment 1's calibration round 2.

## Tasks

### P1 — orderdesk environment

- **Deliverable:** `env.py`, `fixtures.py`
- **Acceptance:** deterministic state machine; every tool a pure function of
  state or an explicit mutation; `snapshot()` returns a canonical state hash.
  Same seed, same state, byte-identical.
- **Verify:** `.venv/bin/python -m pytest tests/test_env.py -q`

### P2 — injection layer

- **Deliverable:** `inject.py`
- **Acceptance:** four injection types, each producing a plausible non-erroring
  wrong value with a fingerprint. Asserts the corrupted value differs from the
  true one. Fires at the configured position, exactly once per trajectory.
- **Verify:** `.venv/bin/python -m pytest tests/test_inject.py -q`

### P3 — discoverability proof

- **Deliverable:** `discoverability.py`
- **Acceptance:** for every (task, injection) pair, a scripted tool sequence
  exposes the corruption. A pair with no such sequence fails the build rather
  than being measured as agent failure.
- **Verify:** `.venv/bin/python -m pytest tests/test_discoverability.py -q`

### P4 — agent loop

- **Deliverable:** `agent.py`
- **Acceptance:** tool-calling loop over the direct SDK, step cap, structured
  `submit`. `inject` and `inject_verify` prompts differ only by the
  verification block, asserted by reconstruction.
- **Verify:** `.venv/bin/python -m pytest tests/test_agent_prompt_diff.py -q`

### P5 — trajectory record and grading

- **Deliverable:** `trajectory.py`, `grade_traj.py`
- **Acceptance:** append-only JSONL, one record per trajectory, storing every
  step's tool, args, result, whether it was injected, whether it consumed the
  fingerprint, tokens and latency. Final-state assert is deterministic.
- **Verify:** `.venv/bin/python -m pytest tests/test_trajectory.py -q`

### P6 — trajectory metrics

- **Deliverable:** `traj_metrics.py`
- **Acceptance:** detection rate, contamination depth distribution, trajectory
  false-green rate, recovery rate, all with Wilson CIs and `null` on empty
  denominators. T7 excluded from headline detection.
- **Verify:** `.venv/bin/python -m pytest tests/test_traj_metrics.py -q`

### P7 — the critical harness tests

- **Deliverable:** `tests/test_traj_false_green.py`
- **Acceptance:** a synthetic trajectory with `claims_success=true` and a wrong
  final state is **counted** as a trajectory false green; a synthetic
  consumption chain of known depth is measured at exactly that depth.
- **Verify:** `.venv/bin/python -m pytest tests/test_traj_false_green.py -q`

### P8 — pilot

- **Deliverable:** `CALIBRATION.md` round 0
- **Acceptance:** 8 clean trajectories, one per task. Establishes the ceiling:
  if `clean` outcome pass rate is below 70% the tasks are too hard and every
  injection number would be confounded by ordinary failure.
- **Verify:** `.venv/bin/python gates.py --gate G4b`

### P9 — full matrix and report

- **Deliverable:** `results/*.jsonl`, `RESULTS.md`, charts
- **Acceptance:** 200 trajectories, single resolved model, truncation rate
  under threshold, report recomputed independently by the gate.
- **Verify:** `.venv/bin/python gates.py --gate G4b`

### P10 — adversarial review

- **Deliverable:** `REVIEW.md`
- **Acceptance:** attacks specific to this design, each with a verdict and a
  passing test. At minimum: can a trajectory be scored detected without the
  agent acting; can the fingerprint appear by coincidence; can an injection
  accidentally produce the correct answer; is the step cap biasing detection.
- **Verify:** `.venv/bin/python gates.py --gate G5b`

## New charts

- Detection rate by injection position (early vs late), with CIs.
- Contamination-depth distribution — a histogram, not a mean.
- Outcome pass rate by mode: clean / inject / inject_verify.

## Out of scope

Production traces, multi-agent delegation, and human-in-the-loop review. Each is
a separate experiment; folding them in here would make no single number
interpretable.
