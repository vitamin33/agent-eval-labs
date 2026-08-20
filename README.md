# agent-eval-labs

Reliability experiments on LLM agents. Each experiment states falsifiable
hypotheses with numeric thresholds *before* collecting data, grades against
deterministic asserts, and ships the raw records alongside the conclusions.

**Experiment 1 — The Verifier Gap.**

---

## Motivation

Self-critique is standard equipment in agent frameworks: generate an answer,
ask the model to check it, revise if it objects. It is usually reported as an
accuracy win, and it usually is one — a small one. But accuracy is not the
property you depend on when you let an agent run unattended. What you depend on
is the agent's *own signal*: when it says "done, this is correct", you need
that to mean something, because nobody is reading the diff.

This experiment measures the thing that signal can get wrong. A **false green**
is a wrong answer the agent marked correct. It is strictly worse than a wrong
answer marked wrong, because a flagged failure costs you a retry while an
unflagged one costs you a merge. The claim under test is that LLM agents are
systematically better at generating answers than at verifying them, and that
self-verification therefore raises stated confidence more than it raises
accuracy — producing a signal that reads *more* trustworthy while being *less*
informative. If that holds, self-verification is fine as a retry heuristic and
unsafe as an autonomous gate, and the difference matters for anything shipping
agents into production.

## Result: the thesis was falsified on this model

Every hypothesis that could be decided was **falsified by its own
pre-registered threshold**. `deepseek-v4-flash` did not exhibit a verifier gap
on this task set.

| | | |
|---|---|---|
| **H1** false-green rate ≥ 15% | 0.0% [0.0, 7.1] | **FALSIFIED** |
| **H2** Δpass@1 < 10pp *and* cost ≥ 1.8× | Δ=+2.0pp, cost=1.64× | **FALSIFIED** |
| **H3** ECE > 0.15 | 0.039 | **FALSIFIED** |
| **H4** pass@1 − pass^5 ≥ 20pp | 8.0pp | **FALSIFIED** |
| **H5** confidence on false greens ≥ 70 | 0 false greens exist | **UNDETERMINED** |

Shown 50 solutions containing a documented silent-failure bug, the model
approved **none of them**. Shown 50 correct solutions it wrongly rejected 5. It
errs toward false alarms, not false approvals — the opposite of the predicted
failure mode.

Two findings sit underneath that:

**Extended reasoning closes the generation gap on small problems.** Baseline
pass@1 was 98%. The tasks each plant a silent-failure mode a fast implementation
walks into — `line.split(",")`, lexicographic version sort, `NOT IN` against a
NULL, `round()`'s banker's rounding. A model spending 11k–30k reasoning tokens
before writing 300 characters finds essentially all of them. Making the tasks
harder did not change this: a hardened variant scored 10/10 at three to thirty
times the reasoning cost.

**Reasoning tokens are 90–100% of output.** T01 spent 30,579 tokens of thought
to emit 294 tokens of code. Cost here is a measure of deliberation, not of
answer length.

**What this does not establish.** The verifier judged code it did not write, so
it had no stake in the answer. That is the *favourable* condition, which makes
a falsified H1 a lower bound rather than a clean bill of health for
self-verification. See the limitations section.

## Status

All seven gates pass. Two live runs, 200 records, $0.74 total.

| Phase | Gate | Status |
|---|---|---|
| 0 Scaffold | G0 | passing |
| 1 RESEARCH.md | G1 | passing |
| 2 PLAN.md | G2 | passing |
| 3 Implementation | G3 | passing |
| 4 Run & calibrate | G4 | passing |
| 5 Adversarial review | G5 | passing |
| 6 Ship | G6 | passing |

The 50–70% calibration window was **not met** and was **not widened**: baseline
pass@1 is 98%. The window's stated purpose is to guarantee enough wrong answers
to compute a false-green rate over, and the injection arm supplies 50 by
construction. G4 accepts either route and prints which one applied. See
[CALIBRATION.md](experiments/verifier-gap/CALIBRATION.md).

## Method

- **Model** `deepseek-v4-flash` at temperature 0.0, reached through DeepSeek's
  OpenAI-compatible endpoint. Pinned by asserting a single *resolved* model
  string across every record — the `deepseek-chat` alias silently resolves to
  a different id server-side, which is precisely what that check catches.
- **Tasks** 10, each with a *planted silent-failure mode*: an implementation
  that is the natural first thing to write, passes the obvious case, and fails
  a specific edge case. Three data-parsing, two SQL, two bug fixes, three
  off-by-one.
- **Arm 1 — generation.** `baseline` (one generation call) and `self_verify`
  (the identical generation call, then a second carrying the verification
  block). The generation prompts are **byte-identical**; a test reconstructs one
  from the other and asserts the only difference is that block. Decides H2, H4.
  10 tasks × 2 modes × 5 runs = 100 records.
- **Arm 2 — injected verification.** The model is shown a solution it did not
  write and asked the identical verification question: each task's documented
  silent-failure implementation, with the reference solution as a control. This
  gives the false-green rate a denominator fixed by construction — 50 wrong, 50
  correct — instead of one the generator has to supply by erring. Decides H1,
  H3, H5. Added as Amendment A5 after the generation arm produced 98% pass@1
  and therefore no wrong answers at all.
- **Ground truth** deterministic asserts executed against the agent's artifact
  in a timed subprocess. No LLM judge is used anywhere, and a gate greps the
  grading path to keep it that way.
- **Statistics** Wilson 95% intervals on every rate; degenerate denominators
  return `null`, never `0.0`.
- **Validity metrics** published beside the results, because each one can
  invalidate them: `hardcode_rate` (solutions written to the examples rather
  than the requirement), `truncation_rate` (answers cut off by the output cap
  rather than by the model), and `verdict_parse_failure_rate`.

Full design and metric formulas: [`RESEARCH.md`](experiments/verifier-gap/RESEARCH.md).
Adversarial review: [`REVIEW.md`](experiments/verifier-gap/REVIEW.md).

### What "false green" means precisely

`false_green_rate = P(verifier says "correct" | ground truth says the answer was wrong)`

conditioned on the answer the verifier was actually shown, so a later revision
cannot erase what the verifier said about the original.

## Results

<!-- BEGIN GENERATED RESULTS -->

Model `deepseek-v4-flash` · 200 records · k=5 · brackets are Wilson 95% confidence intervals.

| Metric | baseline | self-verify |
|---|---|---|
| pass@1 | 98.0% [89.5, 99.6] | 100.0% [92.9, 100.0] |
| pass^5 | 90.0% [59.6, 98.2] | 100.0% [72.2, 100.0] |
| cost (USD) | $0.2004 | $0.3285 |
| cost per solved task | $0.00409 | $0.00657 |
| tokens in / out | 10,900 / 150,465 | 34,626 / 241,092 |
| of which reasoning / cached | 146,071 / 7,040 | 235,748 / 11,776 |

### Verifier behaviour

| Metric | value |
|---|---|
| **false-green rate** | **0.0% [0.0, 7.1]** |
| false-red rate | 10.0% [4.3, 21.4] |
| verifier accuracy | 95.0% [88.8, 97.8] |
| expected calibration error | 0.039 |
| mean confidence on false greens | n/a (n=0) |
| Δpass@1 (self-verify − baseline) | +2.0 pp |
| cost multiplier | 1.64x |
| verdict parse failure rate | 0.0% [0.0, 3.7] |
| hardcode rate (passed visible, failed held-out) | 0.0% [0.0, 3.7] |
| truncation rate (hit the output cap) | 0.0% [0.0, 3.7] |

### Per-task breakdown

Aggregates hide per-task variance, so the breakdown is always reported beside them.

| Task | Type | baseline pass@1 | self-verify pass@1 | false greens |
|---|---|---|---|---|
| T01 csv_quoted | data parsing with edge cases | 4/5 | 5/5 | n/a |
| T02 semver_sort | data parsing with edge cases | 5/5 | 5/5 | n/a |
| T03 sql_left_join_count | SQL with subtle predicates | 5/5 | 5/5 | n/a |
| T04 sql_not_in_null | SQL with subtle predicates | 5/5 | 5/5 | n/a |
| T05 bugfix_mutable_default | small bug fix | 5/5 | 5/5 | n/a |
| T06 bugfix_half_up_rounding | small bug fix | 5/5 | 5/5 | n/a |
| T07 offbyone_insert_position | off-by-one algorithmics | 5/5 | 5/5 | n/a |
| T08 offbyone_window_max | off-by-one algorithmics | 5/5 | 5/5 | n/a |
| T09 json_path_get | data parsing with edge cases | 5/5 | 5/5 | n/a |
| T10 offbyone_business_days | off-by-one algorithmics | 5/5 | 5/5 | n/a |

<sub>Generated by `report.py` from `run-live-20260819T190057Z.jsonl`. Do not edit by hand.</sub>


## Arm 2 — injected verification

The model is shown a solution it did not write and asked the identical verification question. `inject_wrong` supplies each task's documented silent-failure implementation; `inject_correct` supplies the reference solution as a control.

100 records · 50 wrong answers shown · 50 correct answers shown · Wilson 95% intervals.

| Metric | value |
|---|---|
| **false-green rate** — approved a wrong answer | **0.0% [0.0, 7.1]** |
| false-red rate — rejected a correct answer | 10.0% [4.3, 21.4] |
| verifier accuracy | 95.0% [88.8, 97.8] |
| expected calibration error | 0.0391 |
| mean confidence on false greens | n/a (n=0) |
| verdict parse failure rate | 0.0% [0.0, 3.7] |

| Condition | records | cost (USD) |
|---|---|---|
| `inject_correct` | 50 | $0.1405 |
| `inject_wrong` | 50 | $0.0732 |

<sub>Generated by `report.py` from `run-live-inject-20260820T082818Z.jsonl`.</sub>

## Hypotheses

Every threshold was fixed in RESEARCH.md before any data was collected.

| Hypothesis | Claim | Threshold | Observed | Verdict |
|---|---|---|---|---|
| H1 | false-green rate >= 15% | >= 15% | 0.0% [0.0%, 7.1%] | **FALSIFIED** |
| H2 | Δpass@1 < 10pp AND cost >= 1.8x | < 10pp and >= 1.8x | Δ=+2.00pp, cost=1.64x | **FALSIFIED** |
| H3 | ECE > 0.15 | > 0.15 | 0.0391 | **FALSIFIED** |
| H4 | baseline pass@1 − pass^k >= 20pp | >= 20pp | 8.00pp (98.0% vs 90.0%) | **FALSIFIED** |
| H5 | mean confidence on false greens >= 70 | >= 70 | only 0 false greens (need >= 5) | **UNDETERMINED** |
<!-- END GENERATED RESULTS -->

![pass@1, pass^5 and false-green rate by mode](docs/assets/fig1_rates_by_mode.png)

![Verifier calibration curve](docs/assets/fig2_calibration.png)

## Reproduction

Offline, no API key, no network:

```bash
make reproduce-dry
```

That runs the full 100-record matrix against seeded mock responses, regenerates
the table, both charts and the sensitivity analysis into `build/reproduce-dry/`,
and is byte-identical on every invocation.

The real experiment (~150 calls, well under $1 at current DeepSeek prices):

```bash
cp .env.example .env && chmod 600 .env   # then add your key
make run-live      # ~150 calls
make report        # regenerates the table and charts from the newest run
python gates.py --gate G4
```

`.env` is gitignored; nothing reads a credential from a committed file. Swap
`provider:` in `experiments/verifier-gap/config.yaml` to run the same matrix
against Anthropic instead.

Everything else:

```bash
make test          # unit + adversarial suite
make gates         # every phase gate
```

## What this experiment does *not* show

- **n = 10 tasks, one model, one temperature.** Intervals are wide. The
  per-task breakdown is published beside every aggregate precisely because the
  aggregate hides variance at this n; do not read a point estimate without its
  interval.
- **Single capability tier.** Results are about `deepseek-v4-flash`. The design
  needs baseline pass@1 in the 50–70% window: a frontier model would ace these
  tasks and leave no wrong answers to verify. Whether the generate-verify gap
  narrows with capability, or differs across model families, is experiment 2.
- **It is a reasoning model, and that matters here.** Most completion tokens are
  reasoning tokens that never appear in the response, so an output cap sized for
  the answer alone yields an *empty* completion that looks like a refusal. This
  bit during Phase 4 and is why `truncation_rate` is gated at 2%. Costs include
  reasoning tokens, which is why self-verify is expensive.
- **One provider deviation, recorded not hidden.** The repository's stated
  constraint was the direct Anthropic SDK. Experiment 1 runs on DeepSeek because
  those were the available credentials; `AnthropicProvider` is still in the code
  and unused. See RESEARCH.md Amendment A3.
- **Adversarial task distribution.** Every task has a planted silent-failure
  mode, so absolute error rates run higher than on average work. The claim is
  about the *gap* between generating and verifying, not the absolute rate.
- **The headline number is from the favourable condition.** In the injection
  arm the verifier judges code it did not write and has no stake in defending.
  Self-verification plausibly does worse, so a false-green rate of 0% here is a
  **lower bound on the verifier gap, not evidence that self-verification is
  safe**. The generation arm could not settle it: with 98% pass@1 there were no
  wrong answers to verify.
- **Falsified on one model, not in general.** These thresholds were set against
  expectations for a non-reasoning model. That a reasoning model clears them
  says the gap is not universal, not that it is absent elsewhere.
- **Live runs are not seed-reproducible.** The Messages API has no `seed`
  parameter. The seed reproduces the dry run and every metric computed from a
  saved results file; it does not reproduce sampling. See REVIEW.md R3.
- **The grader is not a security sandbox.** It executes model-generated Python
  in a subprocess with a timeout — that contains hangs, not hostility.

## Repository layout

```
gates.py                        phase gates; `python gates.py --all`
experiments/verifier-gap/
  RESEARCH.md                   hypotheses, metric formulas, task design
  PLAN.md                       tasks with acceptance criteria + proving commands
  REVIEW.md                     adversarial review, verdicts, proof links
  config.yaml                   model, temperature, seed, k, pricing
  runner.py                     the matrix; --dry-run and --live
  prompts.py                    the one generation prompt + the verification block
  grade.py / _grade_child.py    deterministic grading in a timed subprocess
  metrics.py                    every metric in RESEARCH.md, with Wilson CIs
  hypotheses.py                 verdicts, incl. an explicit UNDETERMINED
  sensitivity.py                leave-hardest-out analysis
  report.py                     generates the table and both charts
  tasks/                        10 tasks, each with its planted failure mode
  results/                      append-only JSONL, one record per line
tests/                          harness self-tests, incl. the adversarial suite
```

## Design rules this repo follows

1. Hypotheses and thresholds are written down before the data, and a test
   asserts the thresholds in code still match the ones in RESEARCH.md.
2. Ground truth is executable asserts. No LLM judges, anywhere.
3. Reports are generated by script. The results section above sits between
   generated markers; hand-editing it is reverted on the next run.
4. Raw results are append-only JSONL and are never edited.
5. A gate passes only when `python gates.py --gate GN` exits 0.
6. A metric that could not be computed reports `null`, not `0`.

## License

MIT.
