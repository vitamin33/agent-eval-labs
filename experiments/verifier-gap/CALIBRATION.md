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

Pending: the full matrix is running. Result, and any task-difficulty
adjustment it prompts, is recorded here.
