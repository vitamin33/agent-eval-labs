# agent-eval-labs

**Reliability experiments on LLM agents, built so they can come back "no".**

Each experiment writes down falsifiable hypotheses with numeric thresholds
*before* collecting data, grades against deterministic asserts, publishes the
raw records, and passes a set of gates that fail loudly when the method slips.

**Experiment 1 tested the claim that agents are worse at verifying than
generating — and falsified it.** Every hypothesis that could be decided failed
its own pre-registered threshold.

## Motivation

Self-critique is standard equipment in agent frameworks: generate an answer, ask
the model to check it, revise if it objects. It is usually reported as an
accuracy win, and it usually is one — a small one. But accuracy is not the
property you depend on when an agent runs unattended. What you depend on is the
agent's *own signal*: when it says "done, this is correct", that has to mean
something, because nobody is reading the diff. The failure that matters is not
the wrong answer, it is the wrong answer marked **correct** — a **false green**.
A flagged failure costs a retry; an unflagged one costs a merge.

The wider problem is that evaluation writeups tend to confirm the thesis they
set out with. It is easy to build a benchmark that produces the number you
expected, and hard to tell that from the outside. So this repository is
organised around the opposite property: thresholds are fixed in advance and a
test asserts they never drift, ground truth is executable rather than
model-judged, the harness is attacked before it is trusted, and every claim in
the writeup links to a check that would fail if the claim stopped being true.
The point is not that the conclusions here are right — it is that you can tell
when they are wrong.

## What makes a result here checkable

| Property | How it is enforced |
|---|---|
| Hypotheses fixed before data | Thresholds live in `RESEARCH.md`; a test fails if code and document disagree |
| No LLM judges | Ground truth is executable asserts in a sandboxed subprocess; a gate greps the grading path for model calls |
| The harness is attacked | 12 forged-pass vectors in `tools/attack_probe.py`, gated on every change |
| Raw data published | Append-only JSONL, one record per line, never edited |
| Reports are generated | `report.py` writes the tables and charts; hand edits are reverted on the next run |
| Failed rounds are published | `CALIBRATION.md` records what went wrong, including the round that killed the original design |
| Uncertainty is stated | Wilson 95% intervals on every rate; a metric with no denominator returns `null`, never `0` |
| Verdicts can be "don't know" | `UNDETERMINED` is a first-class outcome, used when evidence is missing |

Every phase ends at a gate. `python gates.py --all` runs them; each exits
non-zero on failure, so "looks done" is not a state this repo can be left in.

## The result: it depends entirely on what you ask the agent to verify

Two experiments, **the same model**, opposite answers.

**Experiment 1 — verifying a single answer.** Shown 50 solutions each containing
a documented silent-failure bug, `deepseek-v4-flash` approved **none of them**,
and every rejection came with a repair that passed the asserts.

**Experiment 2 — verifying its own twelve-step trajectory.** One tool result is
silently corrupted — plausible, non-erroring, wrong. The agent noticed **8 times
in 70**. Of the forty-five trajectories that finished wrong, **forty-five
claimed success.** Every single one.

| | Experiment 1 (one answer) | Experiment 2 (trajectory) |
|---|---|---|
| false-green rate | **0%** [0.0, 7.1] | **100%** [92.1, 100.0] |
| caught the planted fault | 50 / 50 | 8 / 70 |
| verdict on the thesis | falsified | supported |

The model has not changed. What changed is that reviewing ten lines of code in
front of you is a different task from re-deriving twelve steps of accumulated
state — and only the second is what an agent actually does before it says
"done".

Three further findings from 200 trajectories:

- **Errors run a long way before anything notices.** Median contamination depth
  is **8 tool-call steps**, reaching 21: the agent keeps acting on the poisoned
  value for most of the trajectory.
- **The obvious fix does nothing.** A per-step "check your work is consistent"
  instruction — the intervention people actually ship — moved detection by
  **+5.7 pp at 1.03x the cost**, well inside noise at this sample size. It was
  free, and it did not help.
- **Noticing is not the problem; noticing at all is.** When the agent did detect
  the corruption it recovered **8 times out of 8**. The predicted failure — spot
  it and still fail — did not happen. The failure is that detection is rare.

**Read this before quoting the numbers.** The injection failed to fire in 43.8%
of attempts, so the effective sample is 70 injected trajectories rather than 160.
**H5 is UNDETERMINED and stays open**: pooled across tasks it appears to reverse
sign at −26 pp, but every late injection that fired came from a task whose tool
is called once — where "late" *is* "early" — so that figure is a task effect
wearing a position label. It is published and disclaimed rather than reported.
Full accounting in
[`CALIBRATION.md`](experiments/agent-verifier-gap/CALIBRATION.md); the harness
review is [`REVIEW.md`](experiments/agent-verifier-gap/REVIEW.md).

## Experiment 1 — The Verifier Gap

**Thesis under test:** LLM agents are systematically better at generating
answers than verifying them, so self-verification inflates confidence more than
accuracy and produces false greens.

**Result on `deepseek-v4-flash`: falsified.**

| | observed | verdict |
|---|---|---|
| **H1** false-green rate ≥ 15% | **0.0%** [0.0, 7.1] | FALSIFIED |
| **H2** Δpass@1 < 10pp *and* cost ≥ 1.8× | Δ=+2.0pp, cost=1.64× | FALSIFIED |
| **H3** verifier ECE > 0.15 | 0.039 | FALSIFIED |
| **H4** pass@1 − pass^5 ≥ 20pp | 8.0pp | FALSIFIED |
| **H5** confidence on false greens ≥ 70 | no false greens exist | UNDETERMINED |

Shown 50 solutions each containing a documented silent-failure bug — a naive
`line.split(",")`, a lexicographic version sort, an INNER JOIN that drops
zero-order customers, `NOT IN` against a NULL — the model approved **none of
them**, on any task. Shown 50 correct solutions it wrongly rejected 5. **It errs
toward false alarms, not false approvals** — the opposite of the predicted
failure mode.

Two findings sit underneath that:

- **Extended reasoning closes the generation gap on small problems.** Baseline
  pass@1 was 98%. Each task plants a silent-failure mode that a fast
  implementation walks into; a model spending 11k–30k reasoning tokens before
  writing 300 characters finds essentially all of them. Making the tasks harder
  did not change this — a hardened variant scored 10/10 at three to thirty times
  the reasoning cost.
- **Reasoning tokens are 90–100% of output.** One task spent 30,579 tokens of
  thought to emit 294 tokens of code. Cost here measures deliberation, not
  answer length, which is why self-verification came in cheaper than predicted.

**Read this before quoting the 0%.** The verifier judged code it did **not**
write, so it had no stake in defending it. That is the *favourable* condition,
which makes this a **lower bound on the verifier gap, not evidence that
self-verification is safe**. See [limitations](#what-this-experiment-does-not-show).

## Method

- **Model** `deepseek-v4-flash` at temperature 0.0, via DeepSeek's
  OpenAI-compatible endpoint. Pinned by asserting a single *resolved* model
  string across every record — the `deepseek-chat` alias silently resolves to a
  different id server-side, which is exactly what that check catches.
- **Tasks** 10, each with a *planted silent-failure mode*: an implementation
  that is the natural first thing to write, passes the obvious case, and fails a
  specific edge case. Three data-parsing, two SQL, two bug fixes, three
  off-by-one.
- **Arm 1 — generation.** `baseline` (one call) vs `self_verify` (the identical
  call, then a second carrying the verification block). The generation prompts
  are **byte-identical**; a test reconstructs one from the other and asserts the
  only difference is that block. Decides H2, H4.
- **Arm 2 — injected verification.** The model is shown a solution it did not
  write — each task's documented silent-failure implementation, with the
  reference solution as a control — and asked the identical verification
  question. The false-green denominator is fixed by construction (50 wrong, 50
  correct) instead of depending on the generator to err. Decides H1, H3, H5.
- **Ground truth** deterministic asserts run in a timed subprocess, plus a
  held-out set never shown in the prompt, so a solution written to the examples
  is caught rather than scored correct.
- **Statistics** Wilson 95% intervals on every rate.

Design and formulas: [`RESEARCH.md`](experiments/verifier-gap/RESEARCH.md) ·
Adversarial review: [`REVIEW.md`](experiments/verifier-gap/REVIEW.md) ·
Calibration log: [`CALIBRATION.md`](experiments/verifier-gap/CALIBRATION.md)

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

Offline, no API key, no network — runs the full 100-record matrix against seeded
mock responses and regenerates every artifact, byte-identically each time:

```bash
make reproduce-dry
```

The real experiment (~250 calls, well under $1 at current prices):

```bash
cp .env.example .env && chmod 600 .env   # then add your key
make run-live          # arm 1 — generation
make run-live-inject   # arm 2 — injected verification
make report            # regenerate tables and charts from both arms
python gates.py --all
```

`.env` is gitignored; no credential is ever read from a committed file. Swap
`provider:` in `experiments/verifier-gap/config.yaml` to run against Anthropic
instead.

```bash
make test    # 247 unit + adversarial tests
make gates   # every phase gate
```

## How the harness tries not to fool itself

The headline metric is a rate of *wrong things marked correct*. If the harness
can do that too, the number measures the apparatus rather than the model. So the
grader was attacked before it was trusted — twelve vectors, five of which
worked:

- **A candidate that printed a passing verdict and called `sys.exit(0)`** was
  graded `correct` on a task it never attempted. `SystemExit` derives from
  `BaseException`, so the guard around `exec` never saw it.
- **The first fix was theatre.** It authenticated verdicts with a nonce — stored
  in the child's `__main__`, inside the very interpreter running the candidate.
  Reading it, wrapping `emit`, or registering an `atexit` hook each defeated it.
- **An object whose `__eq__` returns `True`** satisfied every `==` assert and
  passed three tasks outright. The oracle now compares canonical values it
  computes itself and never calls the candidate's `__eq__`.
- **A lookup table keyed on the assert inputs** passed everything — the realistic
  one, since a model can reach for it without meaning to cheat. Held-out asserts
  now catch it.
- **Floating-point noise decided a hypothesis.** `100 * (0.65 - 0.55)` is
  `9.999999999999998`, so a true value of exactly 10pp reported as satisfying
  "< 10pp". All thresholds now go through one boundary-aware comparator.

All twelve are regression tests. `REVIEW.md` also states the threat model
plainly: the candidate shares the grader's interpreter, so this stops
reward-hacking-shaped shortcuts, **not** a hostile artifact. Only OS-level
isolation would, and this experiment does not attempt it.

## What this experiment does *not* show

- **The headline number is from the favourable condition.** In the injection arm
  the verifier judges code it did not write and has no stake in defending.
  Self-verification plausibly does worse, so 0% is a lower bound on the verifier
  gap, not a clean bill of health. The generation arm could not settle it: at
  98% pass@1 there were no wrong answers to verify.
- **n = 10 tasks.** Intervals are wide and the per-task breakdown is published
  beside every aggregate. Do not read a point estimate without its interval.
- **Single capability tier.** Results are about `deepseek-v4-flash`. Thresholds
  were set against expectations for a non-reasoning model; that a reasoning model
  clears them says the gap is not universal, not that it is absent elsewhere.
- **Adversarial task distribution.** Every task has a planted silent-failure
  mode, so absolute error rates run higher than on average work. The claim is
  about the *gap*, not the absolute rate.
- **Small, self-contained, fully specified problems.** This says nothing about
  long-horizon or underspecified work, where the gap may well appear.
- **Live runs are not seed-reproducible.** The API has no `seed` parameter. The
  seed reproduces the dry run and every metric computed from a saved file; it
  does not reproduce sampling.
- **The grader is not a security sandbox.** It runs model-generated code in a
  subprocess with a timeout — that contains hangs, not hostility.

## Repository layout

```
gates.py                        phase gates; `python gates.py --all`
tools/attack_probe.py           12 forged-pass vectors against the grader
experiments/verifier-gap/
  RESEARCH.md                   hypotheses, metric formulas, task design, amendments
  PLAN.md                       tasks with acceptance criteria + proving commands
  REVIEW.md                     adversarial review, threat model, proof links
  CALIBRATION.md                every calibration round, including the failures
  RESULTS.md                    generated — do not edit
  config.yaml                   provider, model, temperature, seed, k, pricing
  runner.py                     both arms; --dry-run and --live
  prompts.py                    the one generation prompt + the verification block
  grade.py / _grade_child.py    deterministic grading in a timed subprocess
  metrics.py                    every metric, with Wilson intervals
  hypotheses.py                 verdicts, incl. an explicit UNDETERMINED
  sensitivity.py                leave-hardest-out analysis
  report.py                     generates the tables and both charts
  tasks/                        10 tasks, each with its planted failure mode
  results/                      append-only JSONL — the raw experimental data
tests/                          harness self-tests, incl. the adversarial suite
```

## Design rules

1. Hypotheses and thresholds are written down before the data, and a test
   asserts the thresholds in code still match the document.
2. Ground truth is executable asserts. No LLM judges, anywhere.
3. Reports are generated by script. Hand edits are reverted on the next run.
4. Raw results are append-only and never edited; a correction is a new run.
5. A gate passes only when `python gates.py --gate GN` exits 0.
6. A metric that could not be computed reports `null`, not `0`.
7. Calibration rounds that failed are published, not quietly dropped.

## Experiment 2 — the verifier gap in agent trajectories (designed, pre-registered)

Experiment 1 has a substrate problem, and experiment 2 is the fix. "Write a
function that parses CSV" is one call, no tools, no state, no steps — an LLM
eval wearing an agent eval's clothes. The claim that matters for autonomy is not
"can the model review a diff", it is: *when an agent has taken twelve steps and
says "done", does that mean anything?*

[`experiments/agent-verifier-gap/RESEARCH.md`](experiments/agent-verifier-gap/RESEARCH.md)
is the pre-registration, written before any data. A deterministic environment
makes ground truth computable at **every step**, not just the outcome; a silent
failure is injected into one tool result — plausible, non-erroring, wrong — and
the measurements are new:

- **detection rate** — does the agent ever notice
- **contamination depth** — how many steps ran on the poisoned belief first
- **trajectory false-green rate** — it finished, claimed success, and was wrong
- **recovery rate** — noticing and still failing is a different failure

Three gates are specific to it: the environment must be deterministic, every
injection must be **discoverable** (a tool sequence exists that exposes it —
otherwise the task is impossible and the failure is the harness's), and every
corrupted value is asserted to actually differ from the truth.

The design is **staged with a pre-registered stopping rule**: a hypothesis whose
99% interval already clears its threshold after stage 1 stops there; only
genuinely marginal questions pay for the full matrix. The 99%/95% split across
the two looks is what keeps that from being ordinary peeking.

**Built so far:** the `orderdesk` environment, four injection types, the
discoverability proof, the tool-calling agent loop, and the eight tasks — all
gated by **G7**. The stage-0 pilot has run.

**Stage-0 pilot result:** a tool-choice decision costs **290 output tokens**, not
the 30k experiment 1 spent on code generation, so the full 200-trajectory matrix
projects to **$1.07** rather than the feared $32. Clean ceiling 8/8. The pilot
also found three defects that would each have produced a confident wrong number
— most seriously, detection matching on tool name alone counted an agent's
ordinary progress as suspicion. See
[`CALIBRATION.md`](experiments/agent-verifier-gap/CALIBRATION.md).

```bash
python experiments/agent-verifier-gap/discoverability.py   # 16/16 pairs discoverable
python gates.py --gate G7
```

## License

MIT.
