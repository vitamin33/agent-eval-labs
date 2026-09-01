# Adversarial review — agent-verifier-gap harness

A separate pass whose job is to break the instrument, not to confirm it. The
question throughout: **could this experiment report a verifier gap that is an
artefact of the apparatus?**

The stakes are asymmetric here. Experiment 1's headline was a **0%** false-green
rate, and a broken harness would have had to work hard to produce that.
Experiment 2's headline is **100%**, and a broken harness produces that very
easily — by making detection impossible, by mislabelling correct outcomes as
wrong, or by never firing the injection it claims to have fired. Every risk
below is weighted accordingly.

| Risk | Verdict | Proof |
|---|---|---|
| A1 Detection counts ordinary progress as suspicion | **FIXED** | `tests/test_agent_tasks.py::test_recheck_requires_the_same_subject` |
| A2 The injected failure is undiscoverable in principle | **CLEAR** | `tests/test_discoverability.py::test_pair_is_discoverable` |
| A3 A corrupted result is detectable by its shape, not its content | **CLEAR** | `tests/test_inject.py::test_corrupt_value_keeps_the_shape_of_a_real_result` |
| A4 Answer format decides correctness | **FIXED** | `tests/test_agent_tasks.py::test_json_string_answer_is_accepted_for_structures` |
| A5 An injection that never fired is counted as a clean run | **CLEAR** | `tests/test_traj_metrics.py::test_detection_rate_only_counts_trajectories_where_injection_fired` |
| A6 The confound control inflates detection | **CLEAR** | `tests/test_traj_metrics.py::test_confound_control_is_excluded_from_headline_detection` |
| A7 A trajectory false green goes uncounted | **CLEAR** | `tests/test_traj_metrics.py::test_injected_trajectory_false_green_is_counted` |
| A8 The step cap looks like failure to notice | **CLEAR** | G8, step-cap rate gated at 10% (observed 0%) |
| A9 Two clocks conflated in contamination depth | **FIXED** | `tests/test_agent_tasks.py::test_late_injection_threshold_is_defined_on_turns` |
| A10 `late` never fires, so H5 reads as a finding | **FIXED** | RESEARCH.md Amendment A1; CALIBRATION.md stage 1 |
| A11 The verification block leaks what was sabotaged | **CLEAR** | `tests/test_agent_tasks.py::test_verify_block_does_not_name_the_injection` |
| A12 Modes differ by more than the intervention | **CLEAR** | `tests/test_agent_tasks.py::test_modes_differ_only_by_the_verification_block` |
| A13 `answer_consistent_with_poison` read as proven data flow | **SCOPED** | RESEARCH.md, consumption definition |
| A14 A simulated environment is not production | **ACCEPTED** | stated below |

---

## A1 — Detection counting ordinary progress (**was live**)

The most dangerous defect found, and it would have pushed the number in the
*opposite* direction to the published result — which is exactly why it was worth
finding.

Detection originally matched on tool name alone: any `get_customer` call after
the injection counted as the agent re-checking. But a task that walks every
customer calls `get_customer` repeatedly, for *different* customers. On the first
smoke test this reported `detected=True` on a trajectory where the agent had
plainly noticed nothing, and had confidently submitted a wrong answer.

Left in, detection would have run toward 100% and the write-up would have
concluded that agents reliably catch silent tool failures. The published 5% is
what remains once "re-examined **the same subject**" is required — same customer
id, same order id, same filter, same set of ids.

## A2 — Discoverability (**clear**)

If no sequence of tool calls could expose a corruption, the agent would fail
every time, detection would read 0%, and the result would look spectacular while
being entirely ours. `discoverability.py` checks all 16 (task, injection) pairs
before any run, and G7 fails the build otherwise. It has already earned itself
once: T1's `stale` injection targeted an order that was already `pending`, so no
earlier status existed to return.

The environment carries deliberate redundancy for this reason — `count_orders`
answers the same question as `list_orders` by a different route — and a gate
asserts the two agree on every filter, so a corrupted list is distinguishable
from ordinary inconsistency.

## A3 — Shape versus content (**clear**)

A corrupted result must be wrong in its *content*, never in its *form*, or the
agent is detecting a malformed payload rather than reasoning about consistency.
Tests assert every corrupt value keeps the type and key set of a real result and
still differs from the truth.

## A4 — Answer format (**was live**)

T4 submitted the correct numbers as a JSON *string* rather than an object and
was graded wrong. That is the harness measuring itself, and experiment 1 had
already established the principle. Answers are now coerced before checking, with
a test proving coercion cannot rescue a genuinely wrong answer.

## A5 — Injections that never fired (**clear**)

62.5% of stage-1 injection attempts never fired. Folding those into the
denominator as clean runs would have diluted the detection rate; treating them
as detections would have inflated it. They are excluded from the detection
denominator, counted in `injection_not_applicable_rate`, and G8 asserts that
enough fired to bound a rate at all.

## A6 — The confound control (**clear**)

T7's *content* is cross-checking: it asks the agent to compare `count_orders`
against `list_orders`. An agent doing that is following instructions, not
growing suspicious. Its detection is reported separately and excluded from the
headline. Both numbers are published so the difference is visible.

## A7 — The critical test (**clear**)

`test_injected_trajectory_false_green_is_counted` asserts on the number, not on
the absence of a crash, and the negative controls matter as much: an honest
failure — wrong outcome, `claims_success=false` — must **not** be counted, or
the 100% would be an artefact of counting every failure.

## A9 / A10 — Units and the `late` defect (**were live**)

A 12-turn cap produced 22 recorded steps, because one model turn can request
several tool calls, and contamination depth was computed across both units. Both
clocks are now recorded; depth is in tool-call steps.

`late` fired 0 times in 32. It is reported as a **design defect** in
CALIBRATION.md and fixed in Amendment A1 before stage 2, and stage 1's H5 is
marked UNDETERMINED **for a design reason, not an empirical one** — the
distinction is printed in the hypothesis table so it cannot be misread as a
finding about the agent.

## A13 — What `answer_consistent_with_poison` does not prove (**scoped**)

When an agent assembles its final answer in its head, no tool argument carries
the poison fingerprint, so propagation into the answer cannot be proven
mechanically. The field is deliberately named for what it is: the outcome being
*consistent with* the corruption having propagated. It is never reported as
consumption, and no published claim rests on it. Per-step propagation, where the
fingerprint is either in the arguments or is not, is measured precisely.

## A14 — A simulator is not production (**accepted**)

Real tools fail in messier ways than four scripted corruptions, and a synthetic
environment is visibly synthetic. The counter-argument is that ground truth at
*every step* is not computable against a real API — and step-level truth is the
whole point of this design. Production traces are a separate experiment.

## Threats this review does not remove

- **Effective n is small.** Stage 1 bounded the false-green rate on 11 wrong
  trajectories and detection on 20 injected ones. Intervals are wide and are
  always printed.
- **One injection kind per task**, chosen for applicability, so kind is
  confounded with task. No kind-level conclusion is drawn.
- **One model, one scaffold.** A different retry policy or different tool
  descriptions may move every number.
- **The agent is not adversarial.** This measures whether a silent failure is
  noticed, not whether an agent can be made to hide one.
