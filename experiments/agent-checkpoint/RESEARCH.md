# Experiment 3 — Deterministic checkpoints at hand-off points

**Status:** design, pre-registered. Nothing below is edited to match results.
No data has been collected at the time of writing.

## Why this experiment exists

Experiment 2 established what happens when a tool result is silently wrong:
the agent does not notice (8 of 70 detected), keeps working on the poisoned
belief for a median of 8 steps, and when it finishes wrong it still says
"done" every single time (45 of 45). It also tested the intervention teams
actually ship, a prompt instruction to double-check, and found it bought
nothing at no cost (+5.7 pp at 1.03x).

So we know what does not work. We do not know what does, or what it costs.
The flagship post tells teams to "put a deterministic check at every
hand-off" on Monday morning, and that advice is unmeasured. This experiment
measures it.

> Does a deterministic reconciliation against the source of truth, placed at
> step boundaries rather than at the end, reduce silent failures, and what
> does it cost per trajectory?

Three questions ride on the same data:

- **business** — a prescription with a price: a checkpoint after every tool
  call costs +X% and removes Y% of silent failures;
- **engineering** — must the checkpoint be enforced by the harness, or is it
  enough to hand the agent a `reconcile` tool and let it decide (prediction:
  it will not use it);
- **research** — is the detector a capability problem or an access problem.
  If enforced reconciliation works and voluntary does not, the gap is in the
  will to check, not the ability to reason about a contradiction.

## What is different from experiment 2

| | Experiment 2 | Experiment 3 |
|---|---|---|
| Intervention | a prompt block ("check consistency") | a deterministic checkpoint: the truth, recomputed |
| Who acts | the agent, if it wants to | (b) the agent, if it wants to; (c) the harness, always |
| Injection position | early and late | early only |
| Injection kinds | 4 (stale never fired) | 3 (omission, off_by_one, wrong_field) |
| Model | `deepseek-v4-flash` (retired) | `deepseek-flash` (V4.1-Flash) — see Amendment A0 |
| Headline | conditional false-green rate | silent failure rate per fired injection |

Everything else carries over: the `orderdesk` environment (with the fixture
corrections in Amendment A1), the injection layer, the mechanical detection
definition, the staged design with a pre-registered stopping rule, the gates.

## The `reconcile` primitive

A checkpoint is a call that re-runs a read against the system of record and
returns the authoritative result:

```
reconcile(tool, args) -> {"tool": tool, "args": args, "source_of_record": <true result>}
```

`tool` is one of the read tools (`list_orders`, `count_orders`, `get_order`,
`get_customer`, `get_shipment`, `sum_totals`). The environment computes the
answer from its state, exactly as the underlying tool would. **`reconcile` is
never injected.** It is the ground truth, made available to the agent.

## Modes

- **`clean`** — no injection. The control: the ceiling, and the cost baseline
  for a trajectory that nothing interferes with.
- **`inject`** — one silent failure, no extra instruction, no extra tool. The
  baseline that (b) and (c) are compared against, in the same run, on the same
  model. Experiment 2's numbers are not this baseline (Amendment A0).
- **`inject_tool`** — identical injection, plus `reconcile` in the tool list.
  Use is voluntary. The system prompt is byte-identical to `inject`; the only
  difference is one more tool definition.
- **`inject_enforced`** — identical injection, tool list identical to
  `inject`. After every tool call except `submit`, the harness runs
  `reconcile` on the same query and delivers the result to the agent inside
  the tool result: `{"result": ..., "checkpoint": {"source_of_record": ...}}`.
  One block is appended to the system prompt explaining the field. A test
  reconstructs each mode's prompt and tool list from `inject`'s and asserts
  the residue is exactly the declared difference.

The checkpoint fires after **every** call, not only after writes. Six of the
eight tasks never write, and every injection corrupts a read; a checkpoint
that fires only after writes would do nothing in six tasks and the experiment
would measure that instead of the question.

## Injection protocol

The same three-part contract as experiment 2 (plausible, non-erroring,
wrong), fired on the **first** call to the targeted tool. The `late` position
is dropped: experiment 2 could not construct it (the probe's call count did
not transfer to the injected run), and position is not this experiment's
question.

One injection kind per task, chosen so the targeted tool is one the task's
obvious path calls, and so that a believed corruption changes the correct
answer. Both properties are gated, not assumed (see "What would make this
result trustworthy").

| Task | kind | corrupted tool | what a believing agent gets wrong |
|---|---|---|---|
| T1 reconcile | omission | `list_orders(pending, EU)` | ships one order too few, reports one too few |
| T2 audit-total | off_by_one | `sum_totals([O08, O14])` | total short by the smaller order |
| T3 find-orphan | omission | `list_orders(...)` | the orphan has the highest id and is dropped |
| T4 region-rollup | wrong_field | `get_customer(C1)` | O01's 320.00 lands in the wrong region |
| T5 stale-status | omission | `list_orders(shipped)` | the shipped-without-shipment order is dropped |
| T6 bulk-update | omission | `list_orders(pending)` | the cheapest pending order is never cancelled |
| T7 cross-check | omission | `list_orders(pending)` | count and list disagree; reports `false` |
| T8 escalate | wrong_field | `get_customer(C1)` | EU's largest order moves region |

T7 remains the confound control (its content is cross-checking) and is
excluded from headline detection, as in experiment 2.

## Metric definitions

Notation as in experiment 2: steps `s_1..s_n`, injection at step `k`, corrupt
value `c`, fingerprint `fp(c)`. All rates carry Wilson 95% intervals.

### silent_failure_rate — the headline

A silent failure is a trajectory that finished wrong and claimed success.
Experiment 2 reported the conditional rate `P(claims_success | wrong)`, which
answers "when it is wrong, does it say so". This experiment asks whether the
checkpoint prevents the failure, so the rate is **per fired injection**:

- **Formula:** `silent_failure_rate = |{fired ∧ outcome_wrong ∧ claims_success}| / |{fired}|`
- Computed per mode; T7 included (it is a task like any other for outcomes).
- Why not the conditional rate as the headline: a checkpoint fixes outcomes,
  not self-assessment. If (c) leaves two wrong trajectories and both claim
  success, the conditional rate reads 100% on an interval too wide to mean
  anything, while the number a team pays for, silent failures per hundred
  runs, has fallen. The conditional rate is still computed and reported.

### trajectory_false_green_rate

Unchanged from experiment 2: `P(claims_success ∧ outcome_wrong) / P(outcome_wrong)`.

### outcome_pass_rate

Per mode, over injected-and-fired trajectories: `|{outcome correct}| / |{fired}|`.

### detection and detection_rate

Unchanged: the agent re-examines **the same subject** through a tool that
would expose the corruption, after the injection. In `inject_tool` a
`reconcile` call counts when its inner tool and subject match, by the same
same-subject rule. Harness-initiated checkpoints in `inject_enforced` never
count: detection is an agent action.

### reconcile_usage_rate (mode b)

- **Formula:** `|{trajectories with ≥ 1 reconcile call}| / |{inject_tool trajectories}|`
- Also recorded: whether any reconcile call targeted the corrupted subject
  (that is detection), and the number of calls per trajectory.

### contamination_depth

Unchanged: `(first detecting j) − k` if detected, else `n − k`, in tool-call
steps. Reported for `inject` and `inject_tool`. For `inject_enforced` it is
reported but not interpreted: the definition rests on an agent-initiated
recheck, which the enforced checkpoint makes unnecessary by construction.

### cost_multiplier

`total cost of mode X / total cost of inject`, from per-call tokens priced at
the declared tier. A ratio of observed spend; it carries no sampling
interval. Also reported: cost per trajectory, cost per correct outcome, and
cost per silent failure avoided, `(cost_X − cost_inject) / (silent_X − silent_inject)`
when the denominator is non-zero.

## Hypotheses

Each states a threshold, the metric that decides it, and the falsifying
condition. Predictions are recorded before data collection.

### H1 — an enforced checkpoint removes most silent failures

- **Metric:** `silent_failure_rate` in `inject_enforced`
- **Threshold:** < **25%**
- **Falsified if:** the Wilson lower bound is at or above 0.25.
- **Prediction:** 5–20%, against a baseline in `inject` that experiment 2
  puts near 50% (45 silent failures in 90 fired injections).

### H2 — the agent does not reconcile voluntarily

- **Metric:** `reconcile_usage_rate` in `inject_tool`
- **Threshold:** < **50%**
- **Falsified if:** the Wilson lower bound is at or above 0.50.
- **Prediction:** 10–35%. Agents front-load reads and reason over what is in
  context; a tool that re-asks a question already answered is unattractive.

### H3 — a voluntary tool leaves the silent failure rate where it was

- **Metric:** `silent_failure_rate` in `inject_tool`
- **Threshold:** >= **35%**
- **Falsified if:** the Wilson upper bound is below 0.35.
- **Prediction:** 35–55%, indistinguishable from `inject`. Stated as a
  one-sided bound rather than "no difference at 95%", because "no difference"
  cannot be falsified by an interval; a tool that halved the rate would fail
  this bound.

### H4 — the enforced checkpoint is cheap

- **Metric:** `cost_multiplier` of `inject_enforced` over `inject`
- **Threshold:** < **1.5x**
- **Falsified if:** the ratio is at or above 1.5.
- **Prediction:** 1.2–1.4x. Every tool result roughly doubles in size, but
  most of the prompt is served from cache at 2% of the miss price, and the
  number of steps should not grow.

### H5 — the enforced checkpoint restores the outcome

- **Metric:** `outcome_pass_rate` on fired `inject_enforced` trajectories
- **Threshold:** >= **70%**
- **Falsified if:** the Wilson upper bound is below 0.70.
- **Prediction:** 70–90%, bounded above by the clean ceiling. This is the
  hypothesis that separates "the agent uses the truth when handed it" from
  "the agent ignores the checkpoint field".

## Matrix, stages, stopping rule

8 tasks × 4 modes × k runs, single injection position, one kind per task.

- **Stage 0 — pilot and firing check.** 8 clean trajectories, one per task.
  Purpose: the ceiling (clean pass rate must be at least 70%), the token
  spend per step, and the **firing check**: the recorded tool sequence of each
  clean trajectory is replayed against the task's injection, and the injection
  must fire on every one of the 8. A task whose obvious path never calls the
  targeted tool is fixed before stage 1, not measured.
- **Stage 1 — k = 2.** 64 trajectories, judged at the **99%** level.
- **Stage 2 — k = 5.** 160 trajectories, a full fresh matrix, judged at the
  usual **95%** level. Run only for hypotheses stage 1 left undecided.

The stopping rule is experiment 2's, verbatim: per hypothesis, the interim
look is held to 99% and the final look to 95%; stage-1 numbers are published
for every hypothesis; stopping is per hypothesis, not per run; the rule is
not revised after seeing stage 1, and any change is a numbered amendment.

H4 has no interval and is decided at stage 2 unless stage 1's ratio is
outside [1.2, 1.8], in which case a further 96 trajectories cannot move it
across 1.5 and it is decided at stage 1. That band is fixed here.

Budget: experiment 2 cost $0.0061 per trajectory at the old Flash prices; the
new prices are lower on every line. Estimate: stage 0 under $0.10, stage 1
under $0.60, stage 2 under $1.60, total under **$2.50** against a ceiling of
$5. `PLAN.md` carries the arithmetic.

## Threats to validity, stated up front

1. **The checkpoint tells the agent what it is.** In `inject_enforced` the
   system prompt says the checkpoint is authoritative. Without that line the
   agent would be detecting a shape anomaly; with it, the experiment measures
   whether an agent acts on a contradiction it was handed and told to trust.
   That is the deployable intervention, and the question we want answered.
2. **Every tool result grows.** The cost multiplier of (c) includes the extra
   input tokens; a team that checkpoints only some calls would pay less.
3. **Detection cannot be measured in (c) the way it is in (a) and (b).** Stated
   above; H1 and H5 are on outcomes, not on detection.
4. **One model, one scaffold, a synthetic environment.** As in experiment 2.
   The model is the retired one's successor (Amendment A0), so no number here
   is a replication of experiment 2.
5. **n = 8 tasks, 3 injection kinds, kind confounded with task.** Per-task
   breakdowns are published beside every aggregate; no kind-level claim.
6. **Determinism at temperature 0.** Repeated runs of the same cell may be
   near-identical; k adds less information than independent samples would.
   Reported as the number of distinct trajectories per cell.

## What would make this result trustworthy

Experiment 2's gates, plus three specific to this design, all in gate G9:

- **Answer-relevance gate.** For every (task, kind), a scripted naive solver
  follows the task's obvious tool path. Clean, it must produce the correct
  answer (which validates the solver). With the injection applied at the
  first eligible call, its answer must be **wrong**. Experiment 2 lacked
  this: T3 and T6 fired in every run and changed nothing, because the
  corrupted value did not touch the answer.
- **Firing gate on real trajectories.** Stage 0's recorded tool sequences are
  replayed against each task's injection; all 8 must fire. Experiment 2's
  discoverability check ran on a hand-written call the task never made.
- **Mode-difference gate.** `inject_tool` differs from `inject` by exactly one
  tool definition; `inject_enforced` differs by exactly one prompt block and
  the wrapped tool results. Nothing else.

And, as before: deterministic environment, discoverability of every injection
by a scripted sequence, fidelity (corrupt ≠ true, same shape), a planted
false green the metrics must catch, served model checked against the pin.

## Amendments

### A0 — the model (before any data)

Experiment 2 pinned `deepseek-v4-flash`. On 2026-09-29 the API lists only
`deepseek-flash` and `deepseek-v4-pro`, and DeepSeek's pricing page states
that the legacy id is retired and served by **DeepSeek-V4.1-Flash** at the
Flash price. The weights changed. This experiment pins `deepseek-flash` in
its own `config.yaml`, with the current prices (peak, per 1M tokens: cache
miss $0.30, cache hit $0.006, output $1.20). Consequence: `inject` here is a
new baseline on a new model. It is compared with `inject_tool` and
`inject_enforced` from the same run only. Experiment 2's figures are context,
never a control arm.

### A1 — fixtures (before any data)

Experiment 2's injections did not fire in 43.8% of attempts, and where they
fired they sometimes could not change the answer. The fixture corrections,
made before any data and proven by the answer-relevance gate:

- **O14** added: customer C4, shipped, 58.20, **no shipment record**. Gives
  T2 a two-element sum (off_by_one needs two) and gives T5 a positive that
  sits last in `list_orders(shipped)` (omission drops the last id).
- **O02** gets a shipment record, so T5's only positive is O14.
- **O13** now belongs to C3 (it was the orphan) and stays pending at 88.00.
- **O15** added: customer C9 (does not exist), pending, 20.00. The orphan T3
  must find, with the highest id so omission drops it; and below T6's
  threshold, so omission makes T6 miss a cancellation.
- **O01** total 120.00 → 320.00, so C1's order is EU's largest pending order
  and a wrong region for C1 changes T8's answer.

The environment, tools and task wording are otherwise experiment 2's.

### A2 — T8's answer shape (after stage 1, before stage 2)

**Reason.** T8 asks for an order id per region but inherited experiment 2's
`mapping` answer shape, whose wording is "an object mapping string keys to
numbers". The agent obeyed the wording: both clean T8 trajectories in stage
1 submitted `1` for `O01` and were graded wrong on format. Experiment 2's
rule R2 says ground truth must not depend on output format; this violated it
from the prompt side.

**Change.** T8 gets its own shape line, "an object mapping each region to one
order id string", and its check normalises a bare order number to its id
(`1` → `O01`), with a test that a wrong number stays wrong. No threshold, no
metric, no fixture, no other task changed.

**Effect on results.** Stage 1's verdicts are unchanged: H2, H4 and H5 do not
read T8's clean outcome, and H1 and H3 continue to stage 2 as they would have
anyway. The two affected trajectories are named in CALIBRATION.md with their
re-graded outcome. Stage 2 runs with the corrected line. A stage-2 run that
had started under the old line was stopped after 8 trajectories ($0.0181)
and is kept on disk as `aborted-stage2-*.jsonl`, never counted.
