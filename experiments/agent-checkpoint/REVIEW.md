# Adversarial review — agent-checkpoint harness

A separate pass whose job is to break the instrument, not to confirm it. The
question throughout: **could this experiment report that a checkpoint works,
or that it does not, as an artefact of the apparatus?**

The stakes cut both ways here. A harness that leaks the corrupted call into
the checkpoint field, or that grades a wrapped result differently from a bare
one, would make the enforced mode look better than it is. A harness whose
injection fires and changes nothing, as two of experiment 2's did, would make
every mode look better than it is, and the difference between modes would
vanish into a denominator of trajectories that were never really at risk.

| Risk | Verdict | Proof |
|---|---|---|
| A1 The injection fires but cannot change the answer (experiment 2's T3, T6) | **FIXED** | `tests/test_ckpt_relevance.py::test_experiment_2s_t3_pairing_is_caught_as_irrelevant` |
| A2 The injection never fires on the path the agent actually takes | **FIXED** | G9 replays stage 0: `tests/test_ckpt_relevance.py::test_fires_on_replays_the_first_target_call` |
| A3 The checkpoint or the reconcile description names what was corrupted | **CLEAR** | `tests/test_ckpt_prompt_diff.py::test_nothing_in_the_intervention_names_the_sabotage` |
| A4 Modes differ by more than the declared intervention | **CLEAR** | `tests/test_ckpt_prompt_diff.py::test_tool_mode_residue_is_exactly_the_reconcile_tool` |
| A5 The harness checkpoint is counted as the agent detecting | **CLEAR** | `tests/test_ckpt_agent.py::test_harness_checkpoint_is_not_detection` |
| A6 A reconcile call on some other subject counts as detection | **CLEAR** | `tests/test_ckpt_agent.py::test_reconcile_on_another_subject_is_not_detection` |
| A7 `reconcile` returns the corrupted value (the truth is not the truth) | **CLEAR** | `tests/test_ckpt_agent.py::test_reconcile_is_never_injected` |
| A8 A trajectory whose injection did not fire dilutes the silent failure rate | **CLEAR** | `tests/test_ckpt_metrics.py::test_silent_failure_needs_wrong_and_claimed_and_fired` |
| A9 A planted false green goes uncounted | **CLEAR** | `tests/test_ckpt_agent.py::test_planted_false_green_is_recorded_as_a_silent_failure` |
| A10 The wrapper changes what is graded, not only what is shown | **CLEAR** | `tests/test_ckpt_agent.py::test_enforced_checkpoint_carries_the_truth_next_to_the_corrupt_result` |
| A11 A threshold moves after the data is in | **CLEAR** | `tests/test_ckpt_hypotheses.py::test_code_thresholds_match_research_md` |
| A12 H4 is decided by float noise at 1.5 | **CLEAR** | `tests/test_ckpt_hypotheses.py::test_h4_is_decided_exactly_at_the_threshold_by_arithmetic_not_float_noise` |
| A13 The served model is not the pinned one | **CLEAR** | G10; `tests/test_ckpt_agent.py::test_record_is_schema_v2_with_provenance` |
| A14 The cost multiplier of (c) is the wrapper's token bill, not the checkpoint's value | **SCOPED** | stated below |
| A15 Temperature 0 makes k runs one run | **SCOPED** | reported as `cells whose repeats differ` in RESULTS.md |
| A16 A simulated environment is not production | **ACCEPTED** | stated below |
| A17 A malformed tool call by the agent ends the run instead of the trajectory | **FIXED** | `tests/test_ckpt_agent.py::test_a_malformed_tool_call_is_returned_to_the_agent_as_an_error` |
| A18 T8's prompt asked for numbers and graded ids (format decided correctness) | **FIXED** | `tests/test_ckpt_tasks.py::test_t8_accepts_a_bare_order_number_but_not_a_wrong_one` |

---

## A1 — an injection that changes nothing (**was live in experiment 2**)

Experiment 2's T3 corrupted a customer's region in a task that asks which
orders have no customer. It fired in every run. The outcome was right in every
run. Those trajectories counted as "the agent survived a silent failure" when
nothing had been at risk. T6 was the same: the dropped order was above the
cancel threshold anyway.

The fix is a gate, not a judgement call. `relevance.py` runs a scripted naive
solver per task, once clean and once with the injection applied at the first
eligible call, and requires the clean answer to be right and the injected
answer to be wrong. The test replays experiment 2's T3 pairing through it and
asserts it is refused.

## A2 — an injection that never fires on the real path

Experiment 2's discoverability gate ran on a hand-written call the task never
made. Here the naive solver is a real tool path, and gate G9 goes further: it
replays the pilot's recorded clean trajectories, the agent's own paths, and
requires the injection to fire on every task. Stage 0 measured 8 of 8.

## A3, A4 — the intervention must not leak

The checkpoint block and the reconcile tool description are checked for the
words that would name the sabotage. And each mode is reconstructed from
`inject`: `inject_tool` is `inject` plus one tool definition, `inject_enforced`
is `inject` plus one prompt block, byte for byte. A difference in outcome is
attributable to the checkpoint, not to wording.

## A5, A6, A7 — detection stays an agent action, and the truth stays true

In `inject_enforced` the harness reconciles after every call. If those calls
counted as detection, the mode would read as 100% detected by construction.
They do not count. In `inject_tool`, a `reconcile` call counts only when its
inner tool and subject match the corrupted call, by the same same-subject
rule experiment 2 established. And `reconcile` is never routed through the
injection: the test asserts the corrupted list and the reconciled list
differ in exactly the dropped id.

## A8, A9 — the denominator

A silent failure is fired ∧ wrong ∧ claimed. A trajectory where the injection
did not fire is excluded from the denominator, not counted as a success. A
planted false green (wrong outcome, `claims_success=true`) is asserted to
land in every field the metrics read.

## A14 — what the cost multiplier does and does not measure

`inject_enforced` doubles the size of every tool result. Its multiplier over
`inject` therefore includes tokens the agent may never have needed. A cleaner
design would add a fourth arm, clean-with-checkpoint, to separate the
wrapper's cost from the injection's; it is not run, and the number is reported
as the cost of *deploying* the checkpoint on every call, which is what a team
would pay.

## A15 — determinism at temperature 0

Repeated runs of the same cell may be identical. RESULTS.md reports the share
of cells whose repeats differ, so a reader can see how much k bought.

## A17, A18 — what the live run found (**both were live**)

Stage 2's first relaunch died when the agent, offered `reconcile(tool, args)`,
called the plain `list_orders` with an `args` keyword: the environment raised
`TypeError`, the loop caught only `ToolError`, and the process exited after 12
trajectories. The agent's malformed call is part of its trajectory; it now
receives `{"error": "bad arguments for list_orders: ..."}` and continues.

Stage 1 graded both clean T8 trajectories wrong because the prompt's shape
line, inherited from experiment 2, asked for "numbers" and the agent answered
`1` for `O01`. Fixed before stage 2 as Amendment A2: the line asks for ids,
and the check normalises a bare number to its id, with a test that a wrong
number stays wrong. CALIBRATION.md carries both.

## What this review does not remove

- **A16.** The environment is synthetic. Real reconciliation is slower,
  partial, and sometimes wrong itself. The finding is about whether an agent
  acts on a contradiction it is handed, not about building reconciliation.
- **One model.** The successor of the retired one. No number here replicates
  experiment 2; the model is a config field so a cross-model stage can follow.
- **Kind is confounded with task.** One injection kind per task; no kind-level
  claim is made.
