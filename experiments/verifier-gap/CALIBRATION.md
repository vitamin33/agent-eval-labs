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

## Round 2 — hardened tasks

Pending.
