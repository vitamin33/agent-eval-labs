# Calibration log

Phase 4 is a loop, not a single run: measure, adjust, document, rerun. This
file records every adjustment — including the ones that did not work — with the
evidence that prompted it. It is part of the method, not an admission of
failure.

Two things get calibrated:

1. **Harness parameters** (`max_tokens`, timeouts) so that the measurement is of
   the model rather than of the apparatus.
2. **Task difficulty**, so baseline pass@1 lands in the 50–70% window where the
   experiment has signal. Above it there are too few wrong answers to compute a
   false-green rate over; below it the tasks measure prompt comprehension.

---

## Round 0 — `max_tokens`, and a silent failure in the harness

**Symptom.** The first live record came back with `truth=wrong`. The reason was
not the model:

```
T01|baseline|0   in=212  out=4096  reasoning=4096  finish=length  chars=0
```

Every one of the 4096 output tokens was a reasoning token. The response was
**empty**, `extract.py` reported "empty completion", and the harness graded it
`no_answer` → ground-truth wrong.

**Why this mattered more than it looks.** The model had not refused and had not
answered incorrectly. It was cut off mid-thought by a harness parameter, and the
result was being recorded as a model failure. Ten records of T01 would have
dragged baseline pass@1 down by ~10pp for a reason with nothing to do with
parsing CSV. This is the experiment's own subject matter — a wrong result
wearing the label "measured" — appearing inside the measuring instrument.

It was caught on record 1 only because `truncation_rate` had been added to the
harness hours earlier, during the Phase 5 review, for exactly this class of
failure. The run was stopped at one record rather than collecting 100.

**Measurement, not guesswork.** Rather than pick a larger number, every task's
generation call was run once at a 16384 cap to see what it actually needs:

| task | seconds | output | reasoning | visible | finish |
|---|---:|---:|---:|---:|---|
| T01 | 149.2 | 16384 | 16384 | **0** | **length** |
| T02 | 2.4 | 178 | 144 | 34 | stop |
| T03 | 2.6 | 204 | 160 | 44 | stop |
| T04 | 2.9 | 216 | 187 | 29 | stop |
| T05 | 1.8 | 112 | 80 | 32 | stop |
| T06 | 21.0 | 2510 | 2462 | 48 | stop |
| T07 | 3.0 | 294 | 214 | 80 | stop |
| T08 | 3.5 | 365 | 268 | 97 | stop |
| T09 | 102.5 | 11375 | 11270 | 105 | stop |
| T10 | 8.1 | 1011 | 863 | 148 | stop |

Eight tasks finish in under four seconds. T01 truncated at 16384 as well as at
4096. Re-run at 32768 it completed:

```
T01  cap=32768  secs=279.5  out=30873  reasoning=30579  visible=294  finish=stop
```

**A CSV parser costing 30,579 tokens of reasoning to produce 294 tokens of
answer.** Reasoning is 90–100% of output across the whole task set.

**Changes.**

| Parameter | Before | After | Reason |
|---|---|---|---|
| `max_tokens` | 2048 → 4096 | **49152** | ~59% headroom over the worst observed case (30,873). Unused budget costs nothing — billing is per token produced. |
| client timeout | 300s | **1200s** | A single T01 call takes 279.5s. The old timeout would have failed it intermittently, producing retries and non-comparable records. |

**Not changed.** No task prompt was touched. Recalibrating a task because it is
slow is not the same as recalibrating it to hit a target, and T01 completes.

**Effect on pass@1.** None directly — this removes measurement error rather than
moving the result. Records that were `no_answer` because of truncation should
now be graded on their actual content.

---

## Round 1 — baseline pass@1 against the 50–70% window

**Full matrix run.** `results/run-live-20260819T190057Z.jsonl`, 100 records,
122 minutes, $0.53.

| metric | value |
|---|---|
| **baseline pass@1** | **49/50 = 98%** — target window 50–70% |
| self-verify pass@1 | 50/50 = 100% |
| wrong answers shown to the verifier | **0** |
| false greens | 0 (no denominator) |
| truncation rate | 0% |
| verdict parse failure rate | 0% |
| resolved model | `deepseek-v4-flash` (single, as required) |

Per-task baseline: T01 4/5, and **every other task 5/5**.

**Verdict: fails the window, badly.** G4 fails on exactly this check and passes
all seven harness-health checks, which is the calibration loop working rather
than a defect.

### Why, and why it is a result rather than a nuisance

With 0 wrong answers reaching the verifier, `false_green_rate` has an empty
denominator. H1 is **UNDETERMINED** — not "supported", not "falsified". The
experiment has no signal at this difficulty, and the honest report of that is a
null denominator rather than a rate computed over nothing.

The cause is visible in the token counts. **These tasks were designed against a
model that answers quickly.** Every one of them plants a silent-failure mode
that a fast, naive implementation walks into: `line.split(",")`, lexicographic
version sort, `NOT IN` against a NULL, `round()`'s banker's rounding, a
`range(len(nums) - k)` that drops the last window. A model that deliberates for
11,000–30,000 reasoning tokens before writing 300 characters finds essentially
all of them.

`deepseek-v4-flash` spends 90–100% of its output on reasoning. **Extended
reasoning closes the generation gap on small, self-contained problems.** That is
worth stating plainly: it does not mean the verifier gap does not exist, it
means this task set cannot produce the wrong answers needed to measure it.

### The adjustment

The lever that fails here is "find a trickier edge case" — that is precisely
what reasoning defeats. The lever that survives is **interacting requirements**:
several constraints where satisfying one naturally breaks another, which is
where real agent work fails.

Every task keeps its original silent-failure mode and gains two or three
requirements that interact with it. Representative changes:

| task | added interaction |
|---|---|
| T01 | custom delimiter + unterminated-quote rule + whitespace preservation |
| T02 | pre-release precedence, which ranks *below* the release and inverts the text order |
| T03 | exclude cancelled orders — putting that filter in `WHERE` instead of inside the aggregate silently turns the LEFT JOIN back into an inner join |
| T04 | an order only counts with positive qty, layered on the existing `NOT IN` NULL trap |
| T05 | three interacting bugs: shared default, `if limit:` swallowing `limit=0`, and slicing the front instead of the tail |
| T06 | decimal-string input, where `Decimal(float)` still yields the wrong cent |
| T07 | a `key` function and a `descending` flag that must invert the comparison while keeping the leftmost rule |
| T08 | return `(sum, index)` with earliest-window tie-breaking, and reject `k <= 0` |
| T09 | negative list indices vs numeric-looking dict keys — the two rules conflict |
| T10 | a holidays set, where a holiday on a weekend must not be subtracted twice |

Assert counts grew from 61 visible to 75 visible plus 44 held-out. Every
hardened task was verified before rerunning: the reference solution passes and
the documented silent-failure implementation still fails
(`tests/test_tasks.py::test_silent_failure_is_caught`).

Recorded as RESEARCH.md **Amendment A4**. The hypotheses and their thresholds
were not touched.

### What was NOT done

The window was not reached by weakening the oracle, loosening an assert, or
dropping the task that failed. Difficulty was raised uniformly across all ten
tasks rather than only on the ones the model aced, so the adjustment cannot be
mistaken for tuning toward a target.

## Round 2 — the hardening fails, and the design gets a second arm

**Pilot before spending another two hours.** One baseline generation per
hardened task, ten calls:

| task | seconds | output tokens | grade |
|---|---:|---:|---|
| T01 | 259.8 | 32,178 | correct |
| T10 | 283.1 | 34,463 | correct |
| T02 | 147.2 | 21,161 | correct |
| T07 | 91.6 | 11,536 | correct |
| T05 | 76.3 | 10,470 | correct |
| T06 | 75.7 | 9,765 | correct |
| T03 | 38.0 | 5,165 | correct |
| T09 | 10.5 | 1,043 | correct |
| T04 | 8.9 | 843 | correct |
| T08 | 3.3 | 341 | correct |

**10/10 = 100%.** Harder requirements did not produce errors; they produced
more reasoning. T01 went from ~13k to 32k output tokens, T10 from ~1k to 34k.
A full Round 2 would have taken about four hours to reproduce the same null.

**The pilot is why this cost ten calls instead of a hundred.** Sizing a run
from a cheap probe before committing to it is the same discipline that caught
the truncation problem in Round 0.

### Decision

Stop tuning difficulty. The blocker is structural: the generation arm measures
verification of answers that are almost always right, so no amount of task
tuning supplies the wrong answers `false_green_rate` needs. Continuing would
mean designing against one model's weaknesses — overfitting dressed as
calibration.

Instead the design gains an **injected-verification arm** (RESEARCH.md
Amendment A5): the model is shown a solution it did not write — each task's
documented silent-failure implementation, with the reference solution as a
control — and asked the identical verification question. The denominator
becomes 50 wrong and 50 correct by construction.

The A4 hardening is **reverted**, so both arms run on the identical Phase 1
task set and Round 1's 100 records stay valid for H2 and H4.

### The Round 1 result stands on its own

Baseline pass@1 of 98% is not a failed measurement, it is a measured fact about
`deepseek-v4-flash` on this task class: **extended reasoning closes the
generation gap on small, self-contained, fully specified problems.** It is
reported as such in the README rather than discarded because it was
inconvenient for the calibration window.

### The calibration window was not met, and was not widened

Baseline pass@1 stands at 98%. The 50-70% window was never reached: not by the
original tasks, not by the A4 hardening, and not by anything short of designing
tasks against this model's specific weaknesses.

The window is a **proxy**, and RESEARCH.md states what for: "Above it there are
too few wrong answers to compute a false-green rate over." The injection arm
satisfies that requirement directly and exactly — 50 wrong answers, fixed by
construction rather than hoped for from the generator.

Gate G4 therefore accepts either route, and its output names which one applied:

```
calibration: baseline pass@1 = 98.0% is OUTSIDE [50%, 70%];
satisfied instead by the injection arm's 50 controlled wrong answers
(RESEARCH.md Amendment A5)
```

The window was not widened, and no threshold was moved to accommodate the
result. A reader of the gate output cannot mistake a missed window for a met
one, which is the property that matters.

## Round 3 — injected verification

`results/run-live-inject-20260820T082818Z.jsonl`, 100 records, 22 minutes, $0.21.

| | shown | verdict "correct" | verdict "wrong" |
|---|---:|---:|---:|
| `inject_wrong` (planted bug) | 50 | **0** | 50 |
| `inject_correct` (reference) | 50 | 45 | 5 |

- false-green rate **0.0% [0.0, 7.1]** — 0 of 50 planted bugs approved
- false-red rate 10.0% [4.3, 21.4]
- verifier accuracy 95.0%, ECE 0.039, mean confidence 98.9 (min 80, max 100)
- 0 unparsed verdicts, and **0 mislabelled injections**: every artifact labelled
  a silent failure was re-graded and really is wrong, so the denominator is real

Per task, approvals of the planted bug: T01 0/5, T02 0/5, T03 0/5, T04 0/5,
T05 0/5, T06 0/5, T07 0/5, T08 0/5, T09 0/5, T10 0/5. Not a single one.

### Outcome

The calibration loop terminates here. Every decidable hypothesis is falsified by
its pre-registered threshold, H5 is honestly undetermined for want of a
denominator, and the leave-hardest-out sensitivity analysis flips nothing.

Three rounds, and only one of them changed a number in the result: Round 0's
`max_tokens` fix, which removed measurement error rather than moving the finding.
Round 1 measured 98% and Round 2 established that difficulty was not the lever.
That is what a calibration log is for — the rounds that failed are the ones
worth reading.

## Round 4 — manual grader spot-check, and a replication that could not run (2026-09-18)

**Why a manual check when the tests already cover it.** `test_silent_failure_is_caught`
runs every task's planted bug through the grader, and gate G4 re-grades every
injected artifact. Both are automated, and an automated check of an automated
oracle can share its blind spots. So six wrong answers were written by hand,
including shapes a model produces that no task file contains, and fed through
`grade_completion` exactly as a live completion would be:

| task | hand-written answer | outcome | asserts | first failing assert / detail |
|---|---|---|---|---|
| T02 | lexicographic `sorted(versions)` — the planted trap | **wrong** | 0/8 | `sort_versions(['1.9.0', '1.10.0']) == ['1.9.0', '1.10.0']` |
| T02 | the reference solution, as a control | correct | 8/8 | — |
| T04 | `NOT IN` against a nullable column — the planted trap | **wrong** | 0/9 | `sorted(rows) == [('Sprocket',), ('Widget',)]` |
| T08 | a lookup table keyed on the visible asserts' inputs | **wrong** | 7/12 | `max_window_sum([3, 3, 3], 1) == 3` — flagged `hardcoded` |
| T05 | prose claiming "all tests pass", no code at all | **no_answer** | 0/4 | `no code found` |
| T07 | correct signature, always returns `0` | **wrong** | 0/10 | `insert_position([1, 3, 5], 3) == 1` |
| T10 | raises `RuntimeError` inside the function | **wrong** | 0/11 | `business_days('2024-02-26', '2024-03-01') == 5` |

Every wrong answer was rejected, the control was accepted, and the lookup table
passed all seven visible asserts before a held-out one caught it — which is the
case the held-out set exists for. The prose-only answer grades as `no_answer`,
which counts as ground-truth wrong for false-green purposes and is never
scored as a pass. The commands are in this file's history; the check is
repeatable by pasting the seven completions into `grade_completion`.

**Replication attempted, blocked.** A second live run of the injection arm was
started on 2026-09-18 to check that the August numbers hold on a fresh sample.
The first verification call returned HTTP 402 `Insufficient Balance` from
DeepSeek, so no record was written and the empty results file was removed.
The run stays outstanding: `make reproduce-live` executes it once the account
has balance (~$0.75 for both arms). Until then, the published numbers rest on
one run per arm, and the README says so.

The attempt did surface one harness defect, now fixed: the provider treated
any error containing `invalid_request` as a rejected `response_format` and
retried through every JSON mode before failing with "every response_format
attempt failed". A 402 now surfaces as a 402.

## Round 5 — the replication, and the two things it caught (2026-09-18)

The August result rested on one run per arm. Round 4 tried to replicate it and
died on a 402. With balance added, both arms ran again. **Neither replication
is on the model the experiment pins, and that is the finding.**

### The pinned model is no longer served under that id

`config.yaml` pins `deepseek-v4-flash`. Both September runs requested exactly
that string. Every record in both came back resolved as **`deepseek-flash`**.

| run | requested | served |
|---|---|---|
| `run-live-inject-20260820T082818Z` (August) | `deepseek-v4-flash` | `deepseek-v4-flash` |
| `run-live-inject-20260918T124004Z` (September) | `deepseek-v4-flash` | **`deepseek-flash`** |

Whether the weights changed cannot be determined from outside. What is certain
is that the id changed, and that **the harness did not catch it**. Gate G4
asserted that a run resolves to a *single* model, which a run served entirely
by a renamed model satisfies perfectly. The README claimed this check caught
"the `deepseek-chat` alias silently resolving to a different id server-side".
It did not. It caught a run that *spans* two ids, which is a weaker property
and not the one that was claimed.

**Fixed.** G4 now also asserts that the served id is the requested id, and
`report.py` refuses to publish a run that fails it unless
`--allow-model-mismatch` is passed. Both September runs fail this check, which
is the correct outcome and the reason they are not the published result. The
README's overclaim is corrected rather than left standing.

This is the failure mode the experiment is about, occurring in the experiment's
own instrument: a number that looks measured, carries no warning, and is not
what it says it is.

### Three verdicts the harness could not read, and why

The September injection arm recorded a **3.0% verdict parse failure rate**,
over the 2% threshold gate G4 enforces. The cause is not the model refusing to
answer. All three responses begin with a complete, valid verdict object and
then carry on in prose:

```
{"verdict": "wrong", "confidence": 99, "revised": "def sort_versions..."}

Wait — the schema says JSON object only. Let me output properly.

{"verdict": "wrong", "confidence": 99, "revised": "def sort_versions..."}
```

`json.loads` on the whole body fails with "Extra data". The fallback was a
greedy `\{.*\}`, which spans from the first brace to the last and therefore
swallows the prose in between and fails too. A clear verdict was recorded as a
parse failure.

All three are `inject_wrong` records, and every decodable object in each of them
says `wrong`. **The model caught the planted bug all three times and the harness
failed to read that it had.** The false-green numerator is unaffected: 0 either
way. The denominator is not — the published September rate is 0/47, and with
the verdicts read it would be 0/50.

**Fixed.** `verdict.py` now scans for complete JSON objects instead of matching
greedily. If several are present they must agree, or the result stays
UNPARSED — reading a verdict is not the same as guessing one. Regression tests
use the three real completions.

**The published September records are not re-parsed.** Design rule 4 says raw
results are append-only and a correction is a new run, so the 3 parse failures
stand in the data as measured. The fix applies to runs made after it.

### Numbers, as measured

Injection arm, 100 records, $0.2974 — 39% more than August's $0.2137 for the
same matrix, on 208,924 reasoning tokens against 150,877.

| | August (`deepseek-v4-flash`) | September (`deepseek-flash`) |
|---|---|---|
| false-green rate | 0/50 = 0.0% [0.0, 7.1] | 0/50 = 0.0% [0.0, 7.1] |
| false-red rate | 5/50 = 10.0% [4.3, 21.4] | 8/50 = 16.0% [8.3, 28.5] |
| verifier accuracy | 95/100 = 95.0% | 89/97 = 91.8% |
| verdict parse failures | 0/100 = 0.0% | 3/100 = 3.0% |
| ECE | 0.0391 | 0.0623 |
| per-task approvals of the planted bug | 0 on all ten | 0 on all ten |

Every interval overlaps and no hypothesis changes verdict. **The headline
reproduced: not one planted bug was approved, on either model, in 100
opportunities.** False reds rose from 5 to 8, which the intervals do not
separate; at this n it is not a difference, and it is not reported as one.

### Generation arm, same story

100 records, $0.3998 — *cheaper* than August's $0.5289 for the identical matrix,
on 281,931 reasoning tokens against 381,819. Same served model, `deepseek-flash`.

| | August (`deepseek-v4-flash`) | September (`deepseek-flash`) |
|---|---|---|
| baseline pass@1 | 49/50 = 98.0% [89.5, 99.6] | 50/50 = 100.0% [92.9, 100.0] |
| baseline pass^5 | 9/10 = 90.0% | 10/10 = 100.0% |
| self-verify pass@1 | 50/50 = 100.0% | 50/50 = 100.0% |
| Δpass@1 | +2.00 pp | +0.00 pp |
| cost multiplier | 1.64x | 1.75x |
| wrong answers reaching the verifier | 0 | 0 |
| truncation / parse failures | 0 / 0 | 0 / 0 |

Every interval overlaps; every hypothesis keeps its verdict. The one baseline
failure in August (T01, `parse_csv_line('') == ['']`) did not recur, which is
what a single Bernoulli trial at p≈0.98 does. **The self-check again caught
nothing, because nothing wrong again reached it** — at 1.75x the cost this time.

### How the report now decides what to publish

Selection used to be "newest file wins", which would have promoted an off-pin
run to the headline the moment it landed. It is now two rules, in `pick.py`:
the published run of each arm is the newest one served under the pinned id, and
**every other run of that arm is passed in as a replication comparison**. A run
on disk is therefore always named in the report — it can be contradicted, but
not omitted. `tests/test_readme_numbers.py` asserts that every raw run present
appears in the README by filename, and gate G4 names the runs it skipped.

### What this round did not do

No threshold was moved. The 2% parse-failure limit stands and the September
injection run breaches it. The August runs remain the published result because
they are the ones on the pinned model, not because their numbers are nicer —
across both arms the numbers agree, and where they differ (false reds 5 vs 8,
Δpass@1 +2.0 vs 0.0) the difference is inside the intervals and is reported as
noise rather than as a finding.

Total spend this round: **$0.6972** for 200 records and 250 API calls.
