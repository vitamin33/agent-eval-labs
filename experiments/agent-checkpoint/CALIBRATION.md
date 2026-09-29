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
`results/aborted-stage2-20260929T145312Z.jsonl` and is not a result. A
second start under the fixed line was stopped after 1 trajectory ($0.0014)
for a tooling reason (the launcher's 10-minute limit would have cut a
20-minute run) and relaunched detached; that file is kept as
`results/aborted-stage2-20260929T145534Z.jsonl`. Neither is counted, both
are on disk.

### The defect the third start exposed: a malformed call crashed the run

The relaunched stage 2 died on its 13th trajectory, `T1|inject_tool|1`
(12 records, $0.0691, kept as `results/aborted-stage2-20260929T145602Z.jsonl`).
The agent, offered `reconcile(tool, args)`, called the plain `list_orders`
tool with an `args` keyword. The environment raised `TypeError`, the loop
only caught `ToolError`, and the process exited. Experiment 2's loop had the
same latent hole; its agents never tripped it because they were never shown
a nested-argument tool.

The agent's mistake is part of its trajectory and must be visible to it, not
fatal to the run. Fixed: every malformed argument set is now returned to the
agent as `{"error": "bad arguments for ..."}`, exactly like a bad id, with a
test for the crashing shape. No measurement changed; no threshold, metric,
fixture or prompt changed.

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

## Stage 2 — k = 5

`results/ckpt-stage2-20260929T145911Z.jsonl`, 160 trajectories, **$1.3901**.
Projected at ~$1.10 before stage 1 and revised to ~$1.50 after it (the
`inject_tool` arm is the expensive one); the revised estimate held. Served
model `deepseek-flash` on every record, harness commit `ba661e1` on every
record, all 120 injections fired, no step-cap hit, one truncated completion
(`T7|inject_tool|1`, 0.6%, under the 2% threshold; graded wrong, kept).

### Result, judged at 95%

| | `inject` | `inject_tool` | `inject_enforced` |
|---|---|---|---|
| **silent failure rate** | **22/40 = 55.0%** [39.8, 69.3] | **6/40 = 15.0%** [7.1, 29.1] | **0/40 = 0.0%** [0.0, 8.8] |
| outcome pass (fired) | 18/40 | 33/40 | 40/40 |
| detection (T7 excluded) | 17/35 | 29/35 | 11/35 |
| reconcile usage | – | 38/40 | – |
| cost per trajectory | $0.00723 | $0.01399 (1.94x) | $0.00720 (1.00x) |

**H1 supported, H2 falsified, H3 falsified, H4 supported, H5 supported.**
Three predictions right, two wrong, and the two wrong ones are the same
finding seen twice.

### The two falsifications are one fact: given a tool, the agent uses it

H2 predicted the agent would reconcile in fewer than half its trajectories.
It reconciled in 38 of 40, and 371 of the arm's 952 tool calls were
reconciliations. H3 predicted that voluntary use would leave the silent
failure rate where it was; it fell from 55% to 15%. The pre-registered
"will not use it" hypothesis was wrong, in stage 1 and again here.

What survives of the prediction is the *shape* of the failures that remain.
All six are on the two `wrong_field` tasks (T4: 4 of 5, T8: 2 of 5). In four
of them the agent reconciled one to four things, none of them the corrupted
customer; in the other two it reconciled nothing at all. The two
trajectories in the whole arm that never called `reconcile` are both among
the failures. Voluntary reconciliation is broad, expensive, and aimed by the
agent's own sense of what might be wrong, which is exactly the sense that
failed in the first place.

### The enforced checkpoint cost nothing

1.00x, to three decimals 0.997x. Every tool result carries the reconciled
truth, and the arm's input tokens are still lower than `inject`'s (25,493
against 26,582 per trajectory), because the agent stops re-deriving what it
has been handed: on T5, 8.6 steps against 17.8; on T2, 12.8 against 15.4. The
cost-per-avoided-silent-failure is therefore $0, and the report says so
rather than printing a negative number.

The checkpoint did not switch off the agent's own checking: in 11 of 35
trajectories it still re-examined the corrupted subject after being shown
the contradiction, most often on the mutating tasks T1 and T6.

### Two things the baseline confirms from experiment 2

- **Every wrong trajectory claimed success.** 22 of 22 in `inject`, on a
  different model with corrected fixtures. Confidence on the 28 silent
  failures across all arms ran 95 to 100.
- **Detection implies recovery.** 17 of 17 detections in `inject` ended
  correct. The failure is in noticing, never in fixing.

### Determinism

At temperature 0, every one of the 32 cells with repeats produced more than
one distinct tool sequence across its five runs. k bought real variation.

### What was not changed after seeing stage 2

Nothing. The stopping rule was applied as written; H1 and H3 were the two
hypotheses stage 1 left open, and both are decided here at 95%. The report
change in this stage is cosmetic: a mode that removes failures at no extra
spend now prints "$0 (no extra spend)" instead of "$-0.0000".

## Stage 3 on DeepSeek — the wrapper without its sentence, k = 2

`results/ckpt-stage3-deepseek-wrapped-20260929T183420Z.jsonl`, 48
trajectories, **$0.4247**, served `deepseek-flash`, harness `c663760`, all
48 injections fired, one step-cap hit (`T1|inject|1`, which never submitted
and is graded wrong and honest: the first wrong-but-honest trajectory in
the whole experiment).

| | `inject` | `inject_enforced` | `inject_wrapped` |
|---|---|---|---|
| silent failure rate | 7/16 = 43.8% | 0/16 = 0.0% | 2/16 = 12.5% |
| outcome pass (fired) | 8/16 | 16/16 | 14/16 |
| cost per trajectory | $0.00926 | $0.00615 (0.66x) | $0.01113 (1.20x) |

**H8 is UNDETERMINED at 99%** (2 of 16; the interval reaches 44.5%) and
continues to stage 4 at k = 5, as the rule says.

Both wrapped failures are on T7, the task whose job is to report whether
`count_orders` agrees with `list_orders`. Without the sentence saying the
checkpoint is authoritative, the agent saw the corrupted list next to the
true one and reported the disagreement as its finding, `pending: false`.
That is a defensible reading of its instructions and a wrong answer to the
task, and it is the kind of ambiguity the one prompt line removes. The
enforced arm, with the line, stayed at 0 and ran at 0.66x, cheaper than in
stage 2 (1.00x) because this baseline took 20.5 steps against 17.6 then.
Both figures are on 16 trajectories and will be replaced by stage 4's.

## Stage 4 on DeepSeek — the wrapper without its sentence, k = 5

`results/ckpt-stage4-deepseek-wrapped-20260929T184151Z.jsonl`, 120
trajectories, **$1.1282**, served `deepseek-flash`, harness `6ea4780`, all
120 injections fired, no step-cap hit, no truncation.

| | `inject` | `inject_enforced` | `inject_wrapped` |
|---|---|---|---|
| silent failure rate | 20/40 = 50.0% [35.2, 64.8] | 0/40 = 0.0% [0.0, 8.8] | 4/40 = 10.0% [4.0, 23.1] |
| outcome pass (fired) | 20/40 | 40/40 | 36/40 |
| mean steps | 18.9 | 14.9 | 19.3 |
| input tokens per trajectory | 30,709 | 24,500 | 35,911 |
| cost per trajectory | $0.00819 | $0.00706 (0.86x) | $0.01295 (1.58x) |

**H8 supported at 95%**: 4 of 40, upper bound 23.1%, below the 25%
threshold. The prediction (5–25%) held.

### What the sentence does

Handed the truth next to every tool result with no explanation of what it
is, the agent still used it on seven of the eight tasks: 36 of 40 correct,
against 20 of 40 with no checkpoint. All four failures are on T7, the task
whose job is to report whether two counts agree. There the agent saw the
corrupted list beside the true one and reported the disagreement it had
been shown, `pending: false`, in all four wrong runs. Without the sentence
the checkpoint is evidence; with it, the checkpoint is the answer. On the
one task where "the two disagree" is itself an answer, that distinction is
the whole result.

The sentence is also what makes the checkpoint free. Without it the agent
does not stop re-deriving: 19.3 steps against 14.9 with the sentence, and
the largest input per trajectory of the three arms, 35,911 tokens, because
every step carries the doubled results and the agent keeps reading. 1.58x
against 0.86x. The access to the truth removes most of the failures; the
one line removes the rest and pays for itself.

### The baseline, a third time

20 of 40 silent failures, and 20 of 20 wrong trajectories claiming success.
Stage 2 read 22 of 40 and 22 of 22, experiment 2 read 45 of 45. Three runs,
two model versions, the same shape each time.

### What was not changed after seeing stage 4

Nothing. H8's threshold and prediction are the ones committed before stage
3 ran; the stopping rule was applied as written.
