# Adversarial review — verifier-gap harness

A separate pass whose job is to break the harness, not to confirm it. The
question throughout: **could this experiment report a result that is an
artefact of the measuring apparatus?**

Three exploitable defects were found and fixed. Every risk below carries a
verdict and a link to the test or code that settles it.

| Risk | Verdict | Proof |
|---|---|---|
| R1.1a Forged verdict via `sys.exit` | **FIXED** | `tests/test_adversarial.py::test_candidate_cannot_forge_a_verdict_via_sys_exit` |
| R1.1b Forged verdict via `os._exit` | **FIXED** | `tests/test_adversarial.py::test_candidate_cannot_forge_a_verdict_via_os_exit` |
| R1.2 Candidate rigs `__eq__` so every assert passes | **FIXED** | `tests/test_adversarial.py::test_rigged_equality_is_caught_on_every_python_task` |
| R1.3 Refusal or empty answer graded as a pass | **CLEAR** | `tests/test_extract.py::test_refusal_returns_none_not_empty_string` |
| R1.4 Unparseable verdict silently counted | **CLEAR** | `tests/test_false_green.py::test_unparsed_verdict_counts_as_neither_green_nor_red` |
| R1.5a Candidate reads the nonce from `__main__` | **FIXED** | `tests/test_adversarial.py::test_candidate_cannot_read_the_nonce_from_main` |
| R1.5b Candidate replaces `emit` | **FIXED** | `tests/test_adversarial.py::test_candidate_cannot_replace_the_emit_function` |
| R1.5c `atexit` hook forges a verdict after grading | **FIXED** | `tests/test_adversarial.py::test_atexit_cannot_forge_a_verdict_after_grading` |
| R1.6 Candidate rebinds builtins the grader uses | **FIXED** | `tests/test_adversarial.py::test_rebinding_a_builtin_is_detected` |
| R1.7 Targeted `__eq__` rigging that evades the canary | **FIXED** | `tests/test_adversarial.py::test_targeted_equality_rigging_is_caught` |
| R1.8 Solution hardcoded to the assert inputs | **FIXED** | `tests/test_adversarial.py::test_lookup_table_keyed_on_the_visible_cases_is_caught` |
| R2 Ground truth depends on output format | **CLEAR** | `tests/test_adversarial.py::test_grade_is_invariant_to_response_formatting` |
| R3 Seeds claimed to reproduce live runs | **SCOPED** | `tests/test_reproducibility.py::test_the_api_is_never_sent_a_seed_parameter` |
| R4 Conclusions rest on the two hardest tasks | **CLEAR** | `experiments/verifier-gap/sensitivity.py` |
| R5 Float noise flips a hypothesis verdict | **FIXED** | `tests/test_hypotheses.py::test_ece_noise_cannot_support_h3` |
| R6 Executing model-generated code | **ACCEPTED** | `grade.py` module docstring |

## Threat model

The harness defends against **reward-hacking-shaped failures**: a model that
takes a shortcut which happens to satisfy the oracle, without intending to
attack anything. Hardcoding to the examples (R1.8) is the realistic member of
this family; returning an object that compares equal to everything (R1.2) is the
exotic one. Both are now caught.

It does **not** defend against a hostile artifact. The candidate executes in the
grader child's interpreter, so a sufficiently determined artifact can walk the
GC or the frame stack to reach the verdict channel that R1.5 removed from
ordinary reach. The defences below raise the cost of an accidental pass from
"trivial" to "requires deliberate introspection of the harness"; they are not a
security boundary. **The only real boundary is OS-level isolation** — a separate
uid, a container, seccomp — which experiment 1 does not attempt and does not
claim.

Stating this precisely matters more than the defences themselves. The first
version of this document claimed a nonce made verdicts unforgeable. The nonce
was stored in the child's `__main__`, where any candidate could read it, so the
claim was false while sounding rigorous — the same failure mode the experiment
is about.

### The attack probe

Twelve vectors, run against the grader on every change. Five passed against the
original implementation:

| # | Vector | Before | After |
|---|---|---|---|
| A4 | Read nonce from `__main__`, write the verdict file | **breach** | wrong |
| A5 | Rebind `builtins.eval` | error | error (named) |
| A6 | Rebind `builtins.bool` | error | error (named) |
| A7 | Rebind `builtins.open` | wrong | error (named) |
| A8 | Replace `__main__.emit` | **breach** | error |
| A9 | Raise `SystemExit` during assert evaluation | wrong | wrong |
| A11 | Lookup table keyed on the assert inputs | **breach** | wrong (hardcoded) |
| A12 | `__eq__` true only for the real expected values | **breach** | wrong |
| A13 | Rewrite the asserts list in `__main__` | wrong | wrong |
| A14 | `atexit` hook writes a forged verdict | **breach** | wrong |
| A15 | Hardcode the examples stated in the prompt | — | wrong |
| A16 | SQL query hardcoding the fixture's names | — | wrong (hardcoded) |

Zero breaches remain. Every row is a test in `tests/test_adversarial.py`.

---

## R1 — Can the harness itself produce false greens?

This is the review's central question. The experiment's headline number is a
false-green rate; if the *harness* can turn a wrong answer into a `correct`
grade, that number measures the harness rather than the model.

### R1.1 / R1.5 — Forged verdicts (**two rounds, both were exploitable**)

**Round one.** The grader child printed its verdict to stdout, which the parent
parsed as "last line of stdout". A candidate that printed a well-formed passing
verdict and terminated the interpreter before grading finished won outright:

```python
import sys
print('{"outcome": "correct", "n_asserts": 7, "n_passed": 7, ...}')
sys.exit(0)            # -> graded "correct"
```

`SystemExit` slipped through because it derives from `BaseException`, not
`Exception`. The fix was a verdict file authenticated with a per-call nonce.

**Round two — the fix was largely theatre.** The nonce was stored as
`__main__._NONCE` and the output path sat in `sys.argv[1]`, both inside the very
interpreter running the candidate. Three vectors defeated it: read the nonce and
write the file (A4), wrap `__main__.emit` (A8), or register an `atexit` hook
that overwrites the verdict after grading finishes (A14).

**Fix.** The verdict channel is now unreachable by ordinary means: `emit`, the
output path and the nonce exist only as locals of `main`/`_bootstrap`, never as
module attributes; `sys.argv` is truncated before candidate code runs; and the
file is created `O_EXCL` so a second writer cannot silently replace a verdict
that was already reported.

### R1.2 / R1.7 — Rigged comparisons (**two rounds**)

**Round one.** Ground truth was a list of `<call> == <literal>` expressions. An
artifact returning an object whose `__eq__` is unconditionally `True` satisfied
all of them, passing T01, T02 and T07 — every task whose asserts are pure `==`.
It failed elsewhere only because those tasks happen to use `is`, which is luck,
not design. Patched with a sentinel canary.

**Round two.** The canary only catches *unconditional* rigging. An `__eq__` that
returns `True` for the real expected values and `False` for the sentinel walks
straight past it (A12).

**Fix — structural comparison.** The oracle no longer calls the candidate's
`__eq__` at all. A top-level comparison is split by AST: the left side evaluates
in the candidate's namespace, the right in a clean one, and the two are compared
as **canonical values** the grader computes itself from exactly-typed primitives.
`type(x) is int`, not `isinstance` — a subclass that overrides equality is
precisely the attack, so it canonicalises as opaque and cannot match. Numeric
`int`/`float` equality is preserved, so a solution returning `7.0` where `7` is
expected still passes (`test_int_and_float_still_compare_equal`).

### R1.6 — Rebound builtins

`builtins.eval`, `bool` and `open` are all used by the grader's own evaluation
loop, so rebinding one compromises the oracle. A snapshot is taken before the
candidate runs and checked after; tampering is an `error` naming the rebound
builtin, rather than a result.

### R1.8 — Hardcoding to the assert inputs (**the realistic one**)

Every defence above concerns an artifact attacking the harness. This one is a
shortcut a real model can take without any such intent: a lookup table keyed on
the exact inputs the asserts use, or — for SQL — a query written around the
fixture's data. It passed every task it was tried on.

This is the same silent-failure class the experiment exists to measure, and the
harness had it: the oracle could not distinguish "solved the requirement" from
"matched the examples".

**Fix — held-out asserts.** Every task carries a `hidden_asserts` set drawn from
inputs that appear nowhere in the prompt, and SQL tasks carry a second fixture
against which the same query is re-run. An artifact is `correct` only if it
passes both phases. Failing only in the held-out phase is recorded as
`hardcoded=True` and reported as `hardcode_rate`, a validity metric published
beside pass@1 — because if that rate is high, pass@1 is measuring
example-matching and should not be read as anything else.

`test_hidden_asserts_use_inputs_absent_from_the_prompt` enforces the property
that makes the held-out set held out.

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

**Verdict: clear. No conclusion is sensitive to them.**

This is the leave-hardest-out sensitivity analysis. Both arms are dropped
together, so the combined verdicts are recomputed on a
genuinely smaller task set rather than a mismatched pair of them. Dropping T01
and T02 (the two lowest by baseline pass@1) takes 200 records to 160:

| Hypothesis | Full set | Hardest two removed | Flips? |
|---|---|---|---|
| H1 | FALSIFIED (0.0% [0.0, 7.1]) | FALSIFIED (0.0% [0.0, 8.8]) | no |
| H2 | FALSIFIED (Δ=+2.00pp, cost=1.64x) | FALSIFIED (Δ=+0.00pp, cost=1.49x) | no |
| H3 | FALSIFIED (0.0391) | FALSIFIED (0.0401) | no |
| H4 | FALSIFIED (8.00pp) | FALSIFIED (0.00pp) | no |
| H5 | UNDETERMINED (0 false greens) | UNDETERMINED (0 false greens) | no |

The result is robust in the direction that matters least and most: the
falsifications hold, and H5 stays honestly undetermined rather than becoming
decidable through a smaller denominator.

One caveat worth stating: with baseline pass@1 at 98%, "hardest" is a weak
ordering — T01 (4/5) is the only task with any miss at all, and the second pick
is a tie broken by task id. The analysis is therefore less informative here than
it would be on a task set that produced a spread of difficulties.

## R5 — Float noise on a hypothesis boundary (**was a live bug, twice**)

Found while reviewing sensitivity output, not by a test. With 13/20 and 11/20
correct, `100 * (0.65 - 0.55)` evaluates to `9.999999999999998`. H2's condition
is `Δpass@1 < 10pp`, so a true value of exactly 10 — which does *not* satisfy the
condition — was reported **SUPPORTED**, and the printed `Δ=+10.0pp` beside the
threshold `< 10pp` looked like a typo rather than a bug.

The first fix rounded that one metric. Probing the rest showed the same class
elsewhere: an ECE of exactly 0.15 computes as `0.15000000000000002`, so H3's
`ECE > 0.15` reported **SUPPORTED** on a value that does not satisfy it. The
`cost_multiplier` ratio and the Wilson bound have the same exposure.

**Fix.** Every threshold comparison goes through `hypotheses.compare`, which
treats a value within `1e-9` of the threshold as sitting exactly on it and lets
the operator decide from there — `>=` and `<=` hold on the boundary, `>` and `<`
do not. No threshold moved; noise simply can no longer pick a side. Verdicts
decided within that tolerance are flagged `on_boundary` and rendered as
"decided exactly at the threshold", so a knife-edge result does not read like a
comfortable one.

The general lesson applies to every threshold in RESEARCH.md: a verdict decided
by an exact comparison must not be fed unrounded floating-point arithmetic.

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
