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

## Stage 2 — k = 5, for H5 and H6 only

Pending. Runs the `late` fix; H1–H4 are closed and collect no further data.
