# Calibration log — agent-checkpoint

Same contract as experiments 1 and 2: every round is recorded, including the
ones that changed the design, and especially the ones that found the harness
measuring itself.

## Phase 0 — what experiment 2 got wrong, fixed before any data

Experiment 2's injections did not fire in 43.8% of attempts, and where they
fired they sometimes could not change the answer. Both defects were traced in
the raw stage-2 records before this experiment was designed:

| task | experiment 2 defect | cause | fix (Amendment A1) |
|---|---|---|---|
| T2 | off_by_one never fired (0/20) | C4 had one shipped order, so `sum_totals` got one id | O14 added: C4, shipped, 58.20 |
| T5 | stale never fired (0/20) | the agent never calls `get_order`; it lists shipped orders and reads shipments | kind changed to omission; O14 has no shipment record and is last in the list |
| T3 | wrong_field fired 10/10, outcome pass 25/25 | a customer's region does not touch "which orders have no customer" | kind changed to omission; the orphan is O15, the highest id |
| T6 | omission fired 20/20, outcome pass 25/25 | the dropped last id (O13, 88.00) was above the 80.00 threshold anyway | O15 (20.00) is the last pending id |
| T8 | wrong_field fired 10/10, outcome wrong 3/25 | C1's order (120.00) was not EU's largest, so a wrong region rarely moved the answer | O01 total 320.00 |
| T3, T4, T8 | late never fired (0/30) | the probe's call count did not transfer to the injected run | position factor dropped |

The general lesson is now a gate. `relevance.py` runs a scripted naive
solver per task, clean and injected, and requires the clean answer to be
right and the injected answer to be wrong. Experiment 2's discoverability
check ran on hand-written calls (`sum_totals(["O06", "O08"])` for T2, a
call the task never makes) and would have passed all of the above.

Also fixed before data: the model. `deepseek-v4-flash` is retired; the API
serves `deepseek-flash` (DeepSeek-V4.1-Flash) at new prices. This experiment
pins the served id in its own `config.yaml` (Amendment A0).

## Stage 0 — the pilot

`results/ckpt-stage0-20260929T144231Z.jsonl`, 8 clean trajectories, one per
task, **$0.0458**. Served model `deepseek-flash`, equal to the pin on every
record.

### Ceiling: 8/8 clean

Above the 70% floor. A failure under injection can be attributed to the
injection.

### The firing check: 8/8

Gate G9 replays each recorded clean tool sequence against the task's
injection. Every one fires on the first call to the targeted tool:

| task | first call to the targeted tool | would fire |
|---|---|---|
| T1 | `list_orders(pending, EU)` → 2 ids | yes |
| T2 | `sum_totals([O08, O14])` → 488.95 | yes |
| T3 | `list_orders()` → 15 ids | yes |
| T4 | `get_customer(C1)` | yes |
| T5 | `list_orders(shipped)` → 5 ids | yes |
| T6 | `list_orders(pending)` → 8 ids | yes |
| T7 | `list_orders(pending)` → 8 ids | yes |
| T8 | `get_customer(C1)` | yes |

Two of these were the pairs that could not fire in experiment 2 (T2, T5).

### Budget, re-measured

| | measured |
|---|---|
| tool-call steps | 122 (35 model turns) |
| output tokens per step | 242 |
| reasoning tokens per step | 29 |
| input tokens served from cache | 80.4% |
| cost per step | $0.00038 |
| cost per trajectory | $0.00573 (range $0.0017 T5 to $0.0138 T3) |
| projected stage 1 (64) | ~$0.45 |
| projected stage 2 (160) | ~$1.10 |

Trajectories are longer than experiment 2's (mean 15 steps against 12): the
new fixtures have 15 orders instead of 13, and this model reads every order
before answering. No truncation, no step-cap hit. `max_tokens` stays at
8192.

### What the pilot changed

Nothing. No threshold, no task, no fixture. The pilot's job was to confirm
the firing check on real trajectories before money is spent on the matrix,
and it did.

## Stage 1 — k = 2

`results/ckpt-stage1-20260929T144350Z.jsonl`, 64 trajectories, **$0.5961**.
Projected from the pilot at ~$0.45; the overshoot is entirely the
`inject_tool` arm, which averaged 26 steps against 17 for `inject`. Served
model `deepseek-flash` on every record; no truncation; no step-cap hit;
every one of the 48 injections fired.

### Result

| | `inject` | `inject_tool` | `inject_enforced` |
|---|---|---|---|
| **silent failure rate** | **9/16 = 56.2%** [33.2, 76.9] | **3/16 = 18.8%** [6.6, 43.0] | **0/16 = 0.0%** [0.0, 19.4] |
| outcome pass (fired) | 7/16 | 13/16 | 16/16 |
| detection (T7 excluded) | 7/14 | 10/14 | 4/14 |
| reconcile usage | – | 16/16 | – |
| cost per trajectory | $0.00755 | $0.01644 (2.18x) | $0.00709 (0.94x) |

Under the pre-registered stopping rule at the 99% level: **H2 falsified, H4
and H5 supported, H1 and H3 continue to stage 2.**

### H2 was falsified, and the prediction was wrong in an interesting way

The prediction was that an agent handed a `reconcile` tool would mostly not
use it. It used it in 16 of 16 trajectories, and heavily: 155 of the arm's
418 tool calls were reconciliations, a median of 6 per trajectory and up to
28. The cost of the arm doubled. And it still finished wrong and said "done"
in 3 of 16 trajectories, because it reconciled the wrong things: in both T4
failures it reconciled the order list and the orphan customer but never the
customer whose region had been corrupted; in the T8 failure it reconciled
every order and no customer. Voluntary reconciliation is not reluctance, it
is spray: the agent checks what is easy to check, not what is wrong.

### The enforced checkpoint was cheaper than no checkpoint

0.94x. Every tool result carries the reconciled truth, so input grows, but
the agent takes fewer steps: 14.8 on average against 17.3 in `inject`, and
on T5 8 steps against 20. An agent that is handed the truth stops
re-deriving it. The cost-per-avoided-silent-failure column in RESULTS.md is
negative for this arm for that reason.

### The defect stage 1 exposed: T8 was asking for numbers

Both clean T8 trajectories were graded wrong. Their answers were
`{"EU": 1, "US": 5, "APAC": 11}`: the right orders, as bare numbers. T8's
prompt inherited experiment 2's `mapping` shape line, "an object mapping
string keys to numbers", and the agent did what it was told. That is the
harness measuring its own prompt, the format failure experiment 2's rule R2
exists to forbid.

Fixed as Amendment A2 before stage 2: T8 gets an id-mapping shape line, and
its check normalises `1` to `O01` with a test that a wrong number stays
wrong. Re-graded under the fixed check, both trajectories are correct and
the clean ceiling reads 16/16 instead of 14/16. The stage-1 records are not
rewritten; the two trajectories are `T8|clean|0` and `T8|clean|1`. No
hypothesis reads T8's clean outcome, so no verdict moves. Two of the stage-1
`inject` failures on T8 were real (EU mapped to `3`, the corrupted region's
effect) and stand.

A stage-2 run had already started under the old line when this was found.
It was stopped after 8 trajectories ($0.0181); the partial file is kept as
`results/aborted-stage2-20260929T145312Z.jsonl` and is not a result.

### Two observations for the write-up, not for the verdicts

- **Detection in `inject` read 7 of 14**, against 8 of 70 in experiment 2.
  Different model, corrected fixtures, longer trajectories; not comparable,
  and the design says so. It is reported as what this model does here.
- **Silent failures were confident.** The 12 silent failures across the three
  arms carried confidence 72 to 100, eight of them at 97 or above.

### What was not changed after seeing these numbers

No threshold, no metric definition, no fixture, no injection. The T8 fix is a
prompt-side format repair with its rationale above; stage 2 runs the full
matrix as pre-registered, and H1 and H3 are judged there at 95%.
