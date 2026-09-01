# Calibration log — agent-verifier-gap

Same contract as experiment 1: every round is recorded, including the ones that
changed the design, and especially the ones that found the harness measuring
itself.

## Stage 0 — the reasoning pilot

8 clean trajectories, one per task. Purpose: size the reasoning spend before
committing to a full matrix, and establish the ceiling.

### The budget question, answered

Experiment 1 measured 30,579 reasoning tokens on a single code-generation task,
which put the full matrix anywhere between $3 and $32. The pilot settles it:

| | measured |
|---|---|
| output tokens per step | **290** |
| reasoning tokens per step | ~85 |
| cost per step | $0.00048 |
| pilot total (8 trajectories, 90 steps) | **$0.043** |
| **projected full matrix (200 trajectories)** | **$1.07** |
| projected stage 1 (80 trajectories) | $0.43 |

A tool-choice decision is not an essay. The reasoning blow-up that dominated
experiment 1 does not occur here, the $40-60 risk is gone, and prompt caching is
carrying most of the input: 120,804 input tokens with the great majority served
from cache.

**Consequence for the staged design:** at ~$1 for the whole matrix, the stopping
rule is no longer needed to control cost. It stays anyway, because it also
controls the temptation to keep collecting until the numbers look decisive.

### Ceiling: 8/8 clean

Above the 70% floor, so a failure under injection can be attributed to the
injection rather than to ordinary agent failure.

### Three defects the pilot found

**1. Detection was counting ordinary progress as suspicion.** Detection matched
on tool name alone, so a task that walks every customer scored `detected=True`
because it called `get_customer` again — for a different customer. On the smoke
test this reported detection where the agent had plainly not noticed anything.
Left in, it would have driven the detection rate toward 100% and produced a
confident, meaningless "agents catch silent failures" result.

Fixed: detection now requires re-examining **the same subject** — the same
customer id, order id, filter, or set of ids. RESEARCH.md's definition was
updated to match before any data was collected.

**2. Two clocks were mixed.** A 12-turn cap produced trajectories with 22
recorded steps, because one model turn can request several tool calls.
`fired_at` and `detected_at` were in turn units while the contamination-depth
fallback used step counts, so depth was silently wrong. Both clocks are now
recorded per trajectory (`turn`, `idx`), and depth is measured in tool-call
steps — actions on poisoned data are what propagate.

**3. Answer format was deciding correctness.** T4 submitted the right numbers as
a JSON *string* rather than an object and was graded wrong. That is the harness
measuring itself, and experiment 1 had already established the principle (R2:
ground truth must not depend on output format). Answers are now coerced before
checking, with a test proving coercion cannot rescue a genuinely wrong answer.

### What the smoke test showed about the phenomenon

One injected trajectory on T4, with `wrong_field` corrupting C1's region:

- the agent never re-checked C1 — `detected = false`, contamination depth 11
- the final answer moved C1's order into the wrong region bucket
- **`claims_success = true`, `confidence = 100`**

A trajectory false green, in the first injected run. Not evidence of anything on
n=1, but it confirms the instrument can observe the phenomenon it was built for.

## Stage 1 — k = 2

`results/traj-stage1-20260901T125505Z.jsonl`, 80 trajectories, **$0.47**.
Projected from the pilot at $0.43; the estimate held.

### Result

| | |
|---|---|
| clean outcome pass | 16/16 |
| **trajectory false-green rate** | **11/11 = 100%** [74.1, 100.0] |
| detection rate (T7 excluded) | 1/20 = 5% [0.9, 23.6] |
| contamination depth | median **8** tool-call steps, range 2–11 |
| Δdetection from the verification block | **−10 pp** |
| cost multiplier of the verification block | **0.99x** |

Under the pre-registered stopping rule at the 99% level, **H1, H2, H3 and H4 are
decided at stage 1**; H5 and H6 continue.

Every wrong trajectory claimed success. Not most — all eleven.

### The defect stage 1 exposed: `late` never fired

**0 of 32 late-position trajectories injected anything.** `late` was defined as
the first eligible call at or after model turn 3, and the agent calls its
data-fetching tool once, at turn 0 or 1, then never again. Trajectories run 3.5
to 5.8 turns, so by turn 3 the corruptible call is already in the past.

Combined with tasks that compute sums themselves rather than calling
`sum_totals`, **the injection never fired in 62.5% of attempts (40/64)**. The
effective denominator for detection is 20, not the 64 the matrix planned. Every
interval in this stage is correspondingly wide, and the report says so rather
than presenting `1/20` as if it were `1/64`.

H5 is therefore **UNDETERMINED for a design reason, not an empirical one**, and
the distinction is stated in the hypothesis table. Nothing about the agent was
learned from the position factor at this stage.

**The underlying observation is real and worth keeping.** Agents front-load
their data gathering: they fetch everything early, then reason over what is
already in context. A silent failure late in a trajectory is therefore hard to
even construct — which itself implies the dangerous window is the *beginning* of
a trajectory, because that is when data enters.

### Fix for stage 2

Two passes: run clean, count how many times the targeted tool is actually
called (M), then re-run injecting at the M-th call — the last one that really
occurs. Doubles the cost of late trajectories, which at $0.47 per stage is
immaterial. Recorded as an amendment before stage 2 runs, not after seeing its
results.

### H4 was falsified, but not the way it was predicted

H4 predicted the verification block would buy little at real cost: Δ under 15pp
at 1.5x or more. Observed: **Δ = −10 pp at 0.99x**. It bought nothing — slightly
worse than nothing — but it also *cost* nothing, so the conjunct about cost
fails and the hypothesis is falsified.

That is a more interesting outcome than the prediction. An instruction to check
consistency before each tool call, which is what people actually ship, was free
and useless here. With 10 injected trajectories per arm the −10 pp is one
trajectory and means nothing on its own; the defensible claim is that the
intervention showed no benefit at a sample this size.

### What was NOT changed after seeing these numbers

No threshold, no metric definition, no task. The `late` fix is a defect repair
with its rationale recorded above, and stage 2 will re-run it rather than
reinterpreting stage 1. The stopping rule was applied exactly as written,
including to H4, which it decided against the prediction.

## Stage 2 — k = 5

`results/traj-stage2-20260901T171546Z.jsonl`, 200 trajectories, **$1.22**.
Projected from the pilot at $1.07; the estimate held again.

### Result

| | stage 1 (n=80) | stage 2 (n=200) |
|---|---|---|
| clean outcome pass | 16/16 | 39/40 |
| **trajectory false-green rate** | 11/11 = 100% | **45/45 = 100%** [92.1, 100.0] |
| detection rate | 1/20 = 5% | **8/70 = 11.4%** [5.9, 21.0] |
| contamination depth (median) | 8 | **8** (range 1–21) |
| recovery rate | 1/1 | **8/8 = 100%** [67.6, 100.0] |
| injection never fired | 62.5% | 43.8% |

Forty-five wrong trajectories. Forty-five claims of success. Not one instance of
the agent finishing wrong and saying so.

**H6 is falsified, and interestingly.** It predicted recovery below 60%:
detecting a problem and still failing. Observed **8 of 8**. Detection is rare,
but when it happens the agent recovers every time. The failure is not that
agents cannot fix what they notice — it is that they almost never notice.

### The `late` fix worked, and still could not deliver H5

Amendment A1 replaced the turn-based `late` with an ordinal: a probe counts how
many times a task calls the targeted tool (M), and the injection fires on the
Mth. Firing improved from 37% to 56%, and the probes did their job — T3, T4 and
T8 call `get_customer` seven times, T7 three.

But **H5 is still UNDETERMINED, and nearly produced a false finding.**

Pooled across all tasks, detection reads early 2/50 = 4% against late 6/20 =
30%: a **−26 pp sign reversal**, the exact "more interesting result" the
pre-registration promised to report rather than bury. It is not a result at all.

Every late injection that actually fired came from **T1 and T6** — tasks whose
tool is called once, so `inject_at_nth = 1` and *late was the same call as
early*. On the tasks where the factor genuinely differs (T3, T4, T8), the late
injection never fired: the probe measured seven calls, but in the injected run
the agent made fewer, so the Mth call never arrived. T7 fired but is the
confound control and is excluded from headline detection.

So the late arm, restricted to trajectories where position was actually
manipulated, is **empty**. The pooled −26 pp compares a late group drawn from
two tasks against an early group drawn from five: a task effect wearing a
position label. Within T1 alone, early 2/10 versus late 5/10 with an *identical*
injection point, which is sampling noise and nothing else.

H5 is reported UNDETERMINED with the pooled figure shown and explicitly
disclaimed. `test_h5_refuses_a_pooled_comparison_that_is_a_task_effect` pins it
so the trap cannot reopen.

### The residual defect, named

The probe's M does not transfer reliably to the injected run: the agent makes
fewer calls under injection than it did clean. Fixing it properly means either
tasks that force repeated reads of the same entity, or injecting on the *last*
eligible call by buffering — neither is a tweak, and neither is done on the
basis of results already seen. **H5 stays open.** Experiment 2 reports five
decided hypotheses and one it could not answer.

### What was not changed after seeing stage 2

No threshold, no metric, no task. The H5 evaluation was narrowed to tasks where
the factor was manipulated — a correctness fix whose criterion (`inject_at_nth`)
comes from the probe, measured before any detection is observed, and pinned by
`test_restriction_is_decided_by_the_probe_not_the_outcome`. The pooled number is
published beside it so a reader can see exactly what was rejected and why.
