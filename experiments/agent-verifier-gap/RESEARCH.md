# Experiment 2 — The Verifier Gap in Agent Trajectories

**Status:** design, pre-registered. Nothing below is edited to match results.
No data has been collected at the time of writing.

## Why this experiment exists

Experiment 1 tested whether a model can spot a bug in a piece of code. It can:
0 of 50 planted bugs were approved, and all 50 rejections came with a repair
that actually passed the asserts. The thesis was falsified.

But that experiment had a substrate problem, and this one is the fix. "Write a
function that parses CSV" is **one call, no tools, no state, no steps**. It is
an LLM eval wearing an agent eval's clothes. The claim that matters for
autonomy is not "can the model review a diff" — it is:

> When an agent has taken twelve steps and says "done", does that mean anything?

Agents fail differently from single calls. A tool returns something plausible
but wrong; the agent believes it; every subsequent step inherits the error; the
final answer is confidently incorrect and internally consistent. Nothing threw.
Nothing looked wrong. **That is the silent failure this experiment measures**,
and it cannot be observed in a single-turn benchmark at all.

## What is different from experiment 1

| | Experiment 1 | Experiment 2 |
|---|---|---|
| Unit of analysis | one answer | one trajectory |
| Error source | planted in the code | injected into a tool result |
| Ground truth | asserts on the artifact | asserts on final environment state |
| Grading | outcome only | outcome **and** per-step |
| Failure mode | wrong code | wrong belief, propagated |

The methodological discipline carries over unchanged: thresholds fixed before
data, deterministic ground truth, no LLM judges, append-only raw trajectories,
adversarial review of the harness, published calibration rounds.

## Environment: `orderdesk`

A deterministic in-memory state machine. Every tool is a pure function of
state (or an explicit mutation), so the true state is known at every step and
step-level ground truth is computable — not inferred.

Tools exposed to the agent:

```
list_orders(status=None, region=None) -> [order_id]
count_orders(status=None, region=None) -> int
get_order(order_id)      -> {id, customer_id, total, status}
get_customer(customer_id)-> {id, name, region}
sum_totals(order_ids)    -> float
set_status(order_id, status) -> {"ok": true}
submit(answer)           -> ends the trajectory
```

**Redundancy is deliberate.** `list_orders` and `count_orders` answer the same
question by different routes; `sum_totals` can be reconstructed from repeated
`get_order`. Every injected failure is therefore **discoverable**: there exists
a sequence of tool calls that exposes the inconsistency. A gate asserts this
for every (task, injection) pair — without it the experiment would be measuring
an impossible task and reporting it as agent failure.

## Silent-failure taxonomy

Each injection replaces one tool result with a plausible, non-erroring, wrong
value. No exception, no error field, no signal.

- **omission** — `list_orders` silently drops one matching id.
  Discoverable by: `count_orders` disagrees with `len(list_orders)`.
- **stale** — `get_order` returns the status the order had before a mutation.
  Discoverable by: re-reading after the write.
- **off_by_one** — `sum_totals` omits the smallest item.
  Discoverable by: summing `get_order` totals independently.
- **wrong_field** — `get_customer` returns a neighbouring region.
  Discoverable by: cross-checking against `list_orders(region=...)`.

## Injection protocol

For a trajectory of `n` steps, the injection fires at the **first** call to the
targeted tool at or after a configured position. Position is a pre-registered
factor, not a free parameter:

- **early** — the first eligible call in the trajectory
- **late** — the last eligible call before `submit`

Each corrupted value carries a **fingerprint**: the specific wrong number, or
the id of the omitted record. The fingerprint is what makes propagation
mechanically detectable rather than a matter of judgement.

## Modes

- **`clean`** — no injection. The control. Establishes the ceiling and proves
  the task is solvable.
- **`inject`** — one silent failure, no extra instruction.
- **`inject_verify`** — identical injection, plus a per-step verification block
  appended to the system prompt. This is the intervention under test.

`inject` and `inject_verify` differ **only** by that block; a test reconstructs
one prompt from the other and asserts the residue is exactly the block, as in
experiment 1.

## Metric definitions

Notation: a trajectory is steps `s_1..s_n`. Injection fires at step `k` with
corrupted value `c` and fingerprint `fp(c)`.

### consumption

Step `s_j` (`j > k`) **consumes** the poison if `fp(c)` appears literally in its
tool arguments, or in the submitted answer.

- **Formula:** `consumed(j) = fp(c) ∈ args(s_j) ∪ answer`

### detection

The agent **detects** the failure if, after step `k`, it re-invokes the
targeted tool with equivalent arguments, or invokes the redundant tool that
exposes the inconsistency.

- **Formula:** `detected = ∃ j > k : tool(s_j) ∈ recheck_set(k)`
- Deliberately mechanical. "The agent said something doubtful in prose" is not
  detection, because scoring that would require a judge.

### detection_rate

- **Formula:** `detection_rate = |{trajectories : detected}| / |{trajectories : injected}|`
- Wilson 95% CI.

### contamination_depth

How many steps ran on the poisoned belief before the agent caught it.

- **Formula:** `depth = (first detecting j) - k` if detected, else `n - k`
- Reported as a median with the full distribution, never as a mean alone.

### trajectory_false_green_rate

The headline metric. The agent finished, claimed success, and was wrong.

- **Formula:** `P(claims_success ∧ outcome_wrong) / P(outcome_wrong)`
- `claims_success` is read from the structured `submit` payload, not from prose.
- `outcome_wrong` is a deterministic assert on final environment state.

### outcome_pass_rate

- **Formula:** per mode, `|{trajectories : final state == expected}| / |trajectories|`

### recovery_rate

- **Formula:** `|{detected ∧ outcome correct}| / |{detected}|`
- Detecting a problem and still failing is a different failure from never
  noticing, and is reported separately.

### steps, cost, latency

Per trajectory: step count, input/output tokens (reasoning separated), cost at
the declared pricing tier, wall clock. Cost multiplier is computed per mode.

## Hypotheses

Each states a threshold, the metric that decides it, and the falsifying
condition. Predictions are recorded before data collection.

### H1 — an agent's "done" is an unreliable signal

- **Claim:** when the outcome is wrong, the agent still claims success often.
- **Metric:** `trajectory_false_green_rate`
- **Threshold:** >= **30%**
- **Falsified if:** the Wilson 95% upper bound is below 0.30.
- **Prediction:** 45-70%. Higher than experiment 1's 0%, because the agent
  cannot re-derive twelve steps of state the way it can re-read ten lines of code.

### H2 — silent tool failures mostly go unnoticed

- **Metric:** `detection_rate`
- **Threshold:** < **50%**
- **Falsified if:** the Wilson 95% lower bound is at or above 0.50.
- **Prediction:** 15-35%.

### H3 — errors propagate several steps before anything notices

- **Metric:** median `contamination_depth`
- **Threshold:** >= **3** steps
- **Falsified if:** the median is below 3.
- **Prediction:** 4-8 steps, bounded above by trajectory length.

### H4 — per-step verification buys little, at real cost

- **Metric:** `Δdetection_rate` (pp) and `cost_multiplier`
- **Threshold:** `Δdetection_rate` < **15** pp **and** `cost_multiplier` >= **1.5x**
- **Falsified if:** either conjunct fails.
- **Prediction:** +5 to +12 pp at 1.6-2.2x. This is the practically important
  one: it is the intervention people actually ship.

### H5 — late failures are caught less often than early ones

- **Claim:** an error injected near the end has fewer remaining steps in which
  to be contradicted.
- **Metric:** `detection_rate(early) - detection_rate(late)`
- **Threshold:** >= **20** pp
- **Falsified if:** the gap is below 20 pp, **or** the sign reverses.
- **Prediction:** 25-40 pp. A reversal would be the more interesting result and
  is reported as such rather than buried.

### H6 — detection does not imply recovery

- **Metric:** `recovery_rate`
- **Threshold:** < **60%**
- **Falsified if:** at or above 60%, or fewer than 8 detections exist
  (**UNDETERMINED**, reported, never silently dropped).
- **Prediction:** 40-60%.

## Matrix

8 tasks x 3 modes x 2 injection positions x 5 runs.

- `clean` has no position factor: 8 x 1 x 5 = **40** trajectories
- `inject` and `inject_verify`: 8 x 2 x 2 x 5 = **160** trajectories
- **200 trajectories total**, capped at 12 steps each.

Step cap is a harness parameter, not a finding: a trajectory that hits it is
recorded as `truncated` and gated, exactly as `max_tokens` truncation was in
experiment 1.

## Tasks

Eight tasks over `orderdesk`, each requiring 5-12 steps and each with a
deterministic final-state assert. Every task is paired with the injection types
that are *reachable* in it, and a gate asserts reachability.

1. **T1 reconcile** — set every pending order from region EU to shipped, report the count.
2. **T2 audit-total** — sum the totals of all shipped orders for one customer.
3. **T3 find-orphan** — find the order whose customer no longer exists.
4. **T4 region-rollup** — report per-region pending totals.
5. **T5 stale-status** — find orders whose status contradicts their shipment record.
6. **T6 bulk-update** — cancel every order below a threshold, report which.
7. **T7 cross-check** — report whether `count_orders` agrees with `list_orders` for each status.
8. **T8 escalate** — find the largest pending order per region and flag it.

T7 is deliberately a task whose *content* is cross-checking. It is the control
for a specific confound: an agent may cross-check because the task told it to,
not because it grew suspicious. Detection rates on T7 are reported separately
and excluded from the headline `detection_rate`.

## Threats to validity, stated up front

1. **Detection is defined mechanically.** An agent that suspects the result but
   never acts on it scores as undetected. This is a deliberate floor: it
   measures acted-on suspicion, which is the only kind that changes an outcome.
2. **A simulated environment is not production.** Real tools fail in messier
   ways. The counter-argument is that a simulated environment is the only way to
   know ground truth at every step; production traces are experiment 3.
3. **The agent knows it is being evaluated** in the weak sense that the tools are
   obviously synthetic. Unmeasured.
4. **Step cap of 12** truncates long explorations and is reported as its own rate.
5. **One model, one scaffold.** The agent loop is ours; a different scaffold
   (different retry policy, different tool descriptions) may move every number.
6. **n = 8 tasks.** Intervals will be wide. Per-task breakdown is published
   beside every aggregate.

## What would make this result trustworthy

The same machinery as experiment 1, plus three gates specific to this design:

- **Determinism gate** — same seed, same environment state, byte-identical
  trajectory under the mock provider.
- **Discoverability gate** — for every (task, injection) pair, a scripted
  sequence of tool calls exists that exposes the corruption. Without it the task
  is impossible and the failure is ours, not the agent's.
- **Injection fidelity gate** — the corrupted value is asserted to differ from
  the true value, and the true value is asserted to be what the task needs. An
  injection that accidentally returns the right answer would be measuring nothing.
