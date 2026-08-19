# Implementation plan — verifier-gap

Every task below states what it produces, what "done" means, and the exact
command that proves it. Gate G2 parses this file, checks each task has a
runnable verification command, and **executes** every offline command whose
deliverable already exists — so this plan gets progressively harder to satisfy
as the implementation lands, rather than staying a static checklist.

Commands are run from the repository root with the project venv.

## Experiment matrix

| Axis | Values | Count |
|---|---|---|
| Tasks | T01..T10 | 10 |
| Modes | baseline, self_verify | 2 |
| Runs per cell | run indices 0..4 | 5 |
| **Records** | **10 x 2 x 5** | **100** |

One record = one (task, mode, run_index) triple. A record is append-only JSON
and holds: ids, resolved model, both prompts, raw completion(s), extracted
answer, ground-truth outcome, verdict + confidence (self_verify only),
input/output tokens per call, and wall-clock per call.

Call budget: baseline is 1 API call per record (50 calls); self_verify is 2
(100 calls). 150 calls total per full run.

## Tasks

### P3.1 — config.yaml and typed loader

- **Deliverable:** `experiments/verifier-gap/config.yaml`, `experiments/verifier-gap/config.py`
- **Acceptance:** model, temperature, seed, k (runs per cell), max_tokens,
  pricing and task list all come from config; nothing is hardcoded in the
  runner. Loader rejects a config that sets a temperature on a model known to
  reject the parameter, rather than discovering it as a 400 mid-run.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_config.py -q
```

### P3.2 — ten tasks with deterministic asserts

- **Deliverable:** `experiments/verifier-gap/tasks/*.py`, one per task
- **Acceptance:** each module exports `TASK` with id, type, prompt, entrypoint
  and `ASSERTS`; the assert count matches the spec in RESEARCH.md; every task's
  reference solution passes all its asserts and the documented silent-failure
  implementation fails at least one. Ground truth is executable asserts only —
  no model is consulted.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_tasks.py -q
```

### P3.3 — answer extraction

- **Deliverable:** `experiments/verifier-gap/extract.py`
- **Acceptance:** pulls a code artifact out of a completion across fenced,
  unfenced, multi-fence, prose-wrapped and refusal responses; returns an
  explicit `None` on refusal rather than an empty string that would later
  execute as a no-op.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_extract.py -q
```

### P3.4 — sandboxed grader

- **Deliverable:** `experiments/verifier-gap/grade.py`
- **Acceptance:** executes a candidate Python artifact or SQL query against the
  task's asserts in a subprocess with a timeout; returns a structured outcome
  (`correct` / `wrong` / `error` / `no_answer`) plus the first failing assert.
  A candidate that hangs, crashes, or prints a plausible answer without
  defining the entrypoint is graded wrong, never correct.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_grade.py -q
```

### P3.5 — runner with both modes

- **Deliverable:** `experiments/verifier-gap/runner.py`
- **Acceptance:** `baseline` issues the generation call; `self_verify` issues
  the identical generation call plus a second verification call whose response
  is a structured `{"verdict": "correct|wrong", "confidence": 0-100}`. The two
  modes' generation prompts are byte-identical. Every call records
  input/output tokens and wall-clock. Results are appended, never rewritten.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_runner.py -q
```

### P3.6 — mock provider and dry run

- **Deliverable:** `experiments/verifier-gap/provider.py`, `--dry-run` flag
- **Acceptance:** a full 100-record matrix runs offline from seeded mock
  responses, producing schema-valid JSON with token counts; the same seed
  produces byte-identical records across two invocations.
- **Verify:**
```bash
.venv/bin/python experiments/verifier-gap/runner.py --dry-run --out /tmp/aelabs-dry.jsonl
```

### P3.7 — metrics with Wilson intervals

- **Deliverable:** `experiments/verifier-gap/metrics.py`
- **Acceptance:** computes every metric defined in RESEARCH.md, attaches a
  Wilson 95% CI to every rate, returns `null` (not 0.0) for degenerate
  denominators, and reports the per-task breakdown alongside every aggregate.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_metrics.py -q
```

### P3.8 — report generator

- **Deliverable:** `experiments/verifier-gap/report.py`, `docs/assets/*.png`
- **Acceptance:** regenerates the results table and both charts from raw JSON
  with no manual editing; chart (a) is pass@1 vs pass^5 vs false-green by mode,
  chart (b) is the verifier calibration curve against the diagonal. Rerunning
  it on unchanged input produces unchanged output.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_report.py -q
```

### P3.9 — harness self-tests

- **Deliverable:** `tests/test_false_green.py`, `tests/test_prompt_diff.py`
- **Acceptance:** a synthetic record with `verdict=correct` and
  `truth=wrong` is counted as a false green by `metrics.py` — asserted on the
  number, not on the absence of a crash. The prompt-diff test asserts the two
  modes' prompts are identical except for the verification block, by
  reconstructing baseline from self_verify minus that block.
- **Verify:**
```bash
.venv/bin/python -m pytest tests/test_false_green.py tests/test_prompt_diff.py -q
```

### P4.1 — full matrix run

- **Deliverable:** `experiments/verifier-gap/results/run-<stamp>.jsonl`
  (JSON Lines: one record per line, appended and never rewritten)
- **Acceptance:** 100 records, every one carrying non-zero input and output
  token counts and a single shared resolved model string.
- **Verify:**
```bash
.venv/bin/python gates.py --gate G4
```

### P4.2 — calibration

- **Deliverable:** `experiments/verifier-gap/CALIBRATION.md`
- **Acceptance:** baseline pass@1 lands in 50-70%. If it does not, task
  difficulty is adjusted, the change and its rationale are written to
  CALIBRATION.md with the before/after numbers, and the matrix is rerun. Every
  adjustment round is recorded, including ones that did not work.
- **Verify:**
```bash
.venv/bin/python gates.py --gate G4
```

### P5.1 — adversarial review

- **Deliverable:** `experiments/verifier-gap/REVIEW.md`
- **Acceptance:** each of the four named risks (harness-manufactured false
  greens, ground-truth independence from output format, seed reproducibility,
  leave-two-hardest-out sensitivity) carries a verdict and a link to the test
  or code that settles it. Findings are fixed; if code changed, Phase 4 reruns.
- **Verify:**
```bash
.venv/bin/python gates.py --gate G5
```

### P6.1 — README and reproduction

- **Deliverable:** `README.md`, `make reproduce-dry`
- **Acceptance:** motivation, method, results table with CIs, both charts
  embedded, one-command reproduction, and a limitations section naming n,
  the single model, and the adversarial task distribution. Every rate in the
  README carries an interval, not just a point estimate.
- **Verify:**
```bash
.venv/bin/python gates.py --gate G6
```

## Out of scope for experiment 1

Deliberately excluded so the result stays interpretable: cross-model
comparison, multi-turn agent loops, tool use during generation, and any
external orchestrator. A second verifier model (cross-verification rather than
self-verification) is the obvious follow-up and is experiment 2.
