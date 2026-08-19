# Adversarial review — verifier-gap harness

A separate pass whose job is to break the harness, not to confirm it. The
question throughout: **could this experiment report a result that is an
artefact of the measuring apparatus?**

Three exploitable defects were found and fixed. Every risk below carries a
verdict and a link to the test or code that settles it.

| Risk | Verdict | Proof |
|---|---|---|
| R1.1a Candidate forges a passing verdict via `sys.exit` | **FIXED** | `tests/test_adversarial.py::test_candidate_cannot_forge_a_verdict_via_sys_exit` |
| R1.1b Candidate forges a passing verdict via `os._exit` | **FIXED** | `tests/test_adversarial.py::test_candidate_cannot_forge_a_verdict_via_os_exit` |
| R1.2 Candidate rigs `__eq__` so every assert passes | **FIXED** | `tests/test_adversarial.py::test_rigged_equality_is_caught_on_every_python_task` |
| R1.3 Refusal or empty answer graded as a pass | **CLEAR** | `tests/test_extract.py::test_refusal_returns_none_not_empty_string` |
| R1.4 Unparseable verdict silently counted | **CLEAR** | `tests/test_false_green.py::test_unparsed_verdict_counts_as_neither_green_nor_red` |
| R2 Ground truth depends on output format | **CLEAR** | `tests/test_adversarial.py::test_grade_is_invariant_to_response_formatting` |
| R3 Seeds claimed to reproduce live runs | **SCOPED** | `tests/test_reproducibility.py::test_the_api_is_never_sent_a_seed_parameter` |
| R4 Conclusions rest on the two hardest tasks | **PENDING LIVE DATA** | `experiments/verifier-gap/sensitivity.py` |
| R5 Float noise flips a hypothesis verdict | **FIXED** | `tests/test_hypotheses.py::test_h2_boundary_is_strict_not_float_noisy` |
| R6 Executing model-generated code | **ACCEPTED** | `grade.py` module docstring |

---

## R1 — Can the harness itself produce false greens?

This is the review's central question. The experiment's headline number is a
false-green rate; if the *harness* can turn a wrong answer into a `correct`
grade, that number measures the harness rather than the model.

Three attacks were run against `grade_artifact` before any of the defences
below existed. Two of them succeeded.

### R1.1 — Forged verdicts (**was exploitable**)

**Attack.** The grader child ran the candidate's code in-process and printed
its verdict to stdout, which the parent parsed as "last line of stdout". A
candidate that printed a well-formed passing verdict and then terminated the
interpreter before grading finished won outright:

```python
import sys
print('{"outcome": "correct", "n_asserts": 7, "n_passed": 7, ...}')
sys.exit(0)            # -> graded "correct"
```

`os._exit(0)` did the same while also skipping every `finally` and `atexit`
path. Both produced a **fully fabricated pass** on a task the candidate never
attempted. `SystemExit` slipped through because it derives from
`BaseException`, not `Exception`, so the `except Exception` around `exec` never
saw it.

**Fix** (`_grade_child.py`, `grade.py`):

1. The verdict is written to a **file**, never stdout, so printing cannot
   impersonate it.
2. The parent generates a per-call **nonce**, passes it on stdin, and rejects
   any verdict that does not carry it back. A candidate that never reads the
   payload cannot produce an authenticated verdict.
3. `exec` is guarded by `except BaseException`, so `SystemExit` is an error
   outcome rather than an escape hatch.

A candidate that exits early now yields no verdict file at all, which grades
`error` — the fail-closed direction.

### R1.2 — Rigged equality (**was exploitable**)

**Attack.** Ground truth is a list of `<call> == <literal>` expressions. An
artifact returning an object whose `__eq__` is unconditionally `True` satisfies
all of them:

```python
class _Always:
    def __eq__(self, other): return True
def sort_versions(*a, **k): return _Always()   # -> graded "correct"
```

This passed on T01, T02 and T07 — every task whose asserts are pure `==`. It
failed only on tasks that happen to use `is None` / `is False`, which is luck,
not design.

**Fix.** After all asserts pass, the child evaluates one **canary**: the first
assert's left-hand side compared against a sentinel string that nothing
legitimate can equal. If that comparison is true, equality is rigged and the
asserts prove nothing, so the outcome is `error`. The canary runs *last*, so it
cannot perturb the state-dependent tasks (T05), and
`test_canary_does_not_reject_honest_solutions` confirms it costs no true
positives across all ten tasks.

### R1.3 / R1.4 — Extraction and verdict parsing (**clear**)

- A refusal returns `None`, not `""`. An empty string would `exec` cleanly and
  then fail on a missing entrypoint — an `error`, not a pass — but `None` makes
  the distinction explicit and is graded `no_answer`.
- An unterminated fence (a `max_tokens` truncation) still yields its body,
  because a truncated answer is a real answer and should be graded, not
  discarded.
- Multiple fences resolve to the **last** block defining the entrypoint, so a
  "here's the bug / here's the fix" response is graded on the fix.
- A verification response that cannot be parsed is counted as **neither**
  approval nor rejection. Reading it as "wrong" would flatter the false-green
  rate; reading it as "correct" would inflate it. It is counted in
  `verdict_parse_failure_rate`, and gate G4 fails the run above 2%.

## R2 — Is ground truth independent of the agent's output format?

**Verdict: clear.** Grading runs on the extracted artifact's *behaviour*, so
presentation cannot change the outcome:

- The same solution grades identically across six response formats — bare,
  three fence styles, and prose on either side
  (`test_grade_is_invariant_to_response_formatting`).
- Wrong answers stay wrong in every one of those formats
  (`test_wrong_answers_stay_wrong_in_every_format`).
- A correct solution with entirely different internals, parameter names and
  comments still passes (`test_grade_is_invariant_to_internal_naming_and_comments`).
- SQL is compared on result sets, not query text: a `NOT IN ... IS NOT NULL`
  formulation grades the same as the `NOT EXISTS` reference
  (`test_sql_grade_is_invariant_to_style`).
- Extra imports, constants and unused helpers do not affect the grade.

The one format dependency that remains is intentional: the artifact must define
the requested entrypoint name, which every task prompt states explicitly. A
solution defining `maxWindowSum` instead of `max_window_sum` grades `error`,
and that is a genuine instruction-following failure, not a harness artefact.

## R3 — Are seeds actually producing reproducible runs?

**Verdict: scoped, and the scope is narrower than "reproducible".**

**The Messages API has no `seed` parameter.** No configuration makes two live
calls return the same tokens, and `test_the_api_is_never_sent_a_seed_parameter`
asserts the provider never pretends otherwise.

What the seed genuinely reproduces:

| Reproducible | Evidence |
|---|---|
| The full 100-record dry run, byte for byte | `test_dry_run_is_byte_reproducible_under_one_seed` |
| Every metric computed from a fixed results file | `test_metrics_are_fully_reproducible_from_a_fixed_results_file` |
| Task ordering and run indexing | `test_matrix_shape` |

And the control that stops this being vacuous: a *different* seed produces
different dry-run completions (`test_a_different_seed_changes_the_dry_run`).

Consequence for the README: `make reproduce-dry` reproduces exactly; a live
rerun reproduces the *distribution*, not the records. Those are advertised as
two different claims.

## R4 — Sensitivity: would conclusions flip if the 2 hardest tasks were removed?

**Verdict: pending live data.** The analysis is implemented and tested
(`sensitivity.py`); it drops the two tasks with the lowest baseline pass@1,
recomputes all five hypotheses, and reports any verdict that flips. Running it
on the mocked dry run exercises the path and correctly detects flips when they
occur. The verdict for the real experiment cannot be written until Phase 4 has
run, and this section will be replaced with its output rather than a
prediction.

Because n = 10, this section is expected to matter. If a conclusion does flip,
it will be reported as sensitive to task selection in the README rather than
dropped.

## R5 — Float noise on a hypothesis boundary (**was a live bug**)

Found while reviewing the sensitivity output, not by a test. With 13/20 and
11/20 correct, `100 * (0.65 - 0.55)` evaluates to `9.999999999999998`. H2's
condition is `Δpass@1 < 10pp`, so a true value of exactly 10 — which does *not*
satisfy the condition — was being reported **SUPPORTED**, and the printed
`Δ=+10.0pp` beside the threshold `< 10pp` looked like a typo rather than a bug.

Fixed by rounding the delta at computation time in `metrics.summarize` and
printing two decimals near thresholds. Regression:
`test_h2_boundary_is_strict_not_float_noisy` and
`test_delta_is_rounded_so_float_noise_cannot_flip_a_verdict`.

The general lesson is recorded because it applies to every threshold in
RESEARCH.md: a hypothesis whose verdict is decided by an exact comparison must
not be fed unrounded floating-point arithmetic.

## R6 — Executing model-generated code

**Verdict: accepted risk, documented rather than solved.** The grader runs
model-generated Python in a subprocess with `-I` and a wall-clock timeout. That
contains hangs and crashes; it is **not** a security boundary — the child has
the same filesystem and network access as the parent. This is stated in
`grade.py`'s docstring and in the README. Anyone running the live matrix is
running arbitrary generated code on their machine.

The nonce defence of R1.1 raises the bar for a candidate *accidentally*
producing a pass, but a genuinely adversarial artifact running in-process could
still inspect its own interpreter. Defending against that would require a real
sandbox and is out of scope for experiment 1.

## Threats this review does not remove

- **n = 10 tasks, one model, one temperature.** Wide intervals; per-task
  breakdown is always published beside the aggregate.
- **Adversarial task distribution.** Every task has a planted silent-failure
  mode, so absolute error rates are higher than on average work. The claim
  under test is the generate-verify *gap*, not the absolute rate.
- **The verifier sees its own answer in its own context window.** That is the
  phenomenon being measured, but it means these results say nothing about a
  *separate* verifier model. That is experiment 2.
