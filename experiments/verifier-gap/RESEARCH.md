# Experiment 1 — The Verifier Gap

**Status:** design frozen at Phase 1. Numbers below are *predictions*, recorded
before any data was collected. Results live in `../../README.md` and
`results/`; this file is never edited to match them.

> **Superseded in part by [Amendment A3](#a3--provider-and-model-phase-4).** The
> experiment runs on **`deepseek-v4-flash`**, not `claude-haiku-4-5`. The
> Setup table and Model-choice section below record the design as frozen; A3
> records what changed, why, and what it cost. Nothing else in the design moved.

## Thesis

LLM agents are systematically better at *generating* answers than at
*verifying* them. Asking an agent to check its own work raises its stated
confidence more than it raises its accuracy. The failure that matters is not
the wrong answer — it is the wrong answer the agent has marked **correct**. We
call that a **false green**, and we claim it is common enough to make
self-verification unsafe as an autonomous gate.

## Why this is worth measuring

Self-critique ("reflect on your answer and fix it") is standard in agent
frameworks and is generally reported as an accuracy win. Those reports measure
Δaccuracy. They rarely measure what the verification step does to the
*trustworthiness of the agent's own signal* — which is the property you rely on
when you let an agent merge, deploy, or close a ticket unattended. A +4pp
accuracy gain that also produces a 25% false-green rate is a net loss for
autonomy, and the two are not visible in the same metric.

## Setup

| Parameter | Value | Why |
|---|---|---|
| Model | `claude-haiku-4-5` | See "Model choice" below |
| Temperature | `0.0` | Config-controlled; see "What `seed` can and cannot do" |
| Tasks | 10 | See "Task design" |
| Modes | 2 (`baseline`, `self_verify`) | Prompts differ only by the verification block |
| Runs per cell | 5 | Enough for pass^5; small enough to keep CIs honest |
| Records | 10 x 2 x 5 = 100 | |

### Model choice

The experiment needs a model whose baseline pass@1 lands in **50-70%**. Above
that, ceiling effects leave too few wrong answers to compute a false-green rate
over; below it, the tasks are measuring prompt comprehension rather than
verification. `claude-haiku-4-5` is also one of the models that still accepts
`temperature` — the Claude 5 family (`claude-opus-5`, `claude-sonnet-5`) and
Opus 4.7/4.8 **reject `temperature` with HTTP 400**, so a temperature-controlled
experiment cannot use them.

This is the single largest threat to external validity and is listed as such in
the limitations section of the README. The claim under test is about the
*generate-verify asymmetry*, which we predict is a property of the architecture
rather than of one capability tier; testing that prediction across tiers is
experiment 2, not this one.

### Model version pinning

Anthropic model IDs are complete as written (`claude-haiku-4-5`) and are not
date-suffixed. "Pinning" therefore cannot mean pinning a string in config — the
string is stable while the served weights need not be. Instead:

- `config.yaml` fixes the requested ID.
- Every record stores `model_resolved`, the exact `response.model` string the
  API returned for that call.
- Gate G4 fails if the run contains more than one distinct `model_resolved`.

That converts an unverifiable claim ("we pinned the model") into a checked one
("every record in this run was served by the same model string").

### What `seed` can and cannot do

**The Messages API has no `seed` parameter.** No seed value makes two live calls
return the same tokens. Claiming seeded reproducibility over live sampling would
be false, so the config `seed` is scoped explicitly:

| Seeded (reproducible) | Not seeded (irreducible) |
|---|---|
| Task ordering and run indexing | Model token sampling |
| `run_id` / record identity | Which specific answer is produced |
| Mock responses in `--dry-run` | |
| Every metric computed from a fixed `results/*.json` | |

Consequence: `make reproduce-dry` reproduces byte-identically; a live rerun
reproduces the *distribution*, not the records. Phase 5 tests both claims
separately rather than asserting the stronger one.

## Hypotheses

Each hypothesis states a threshold, the metric that decides it, and the
condition under which it is **falsified**. A hypothesis with no falsifying
outcome is not in this list.

### H1 — Self-verification approves wrong answers at a high rate

- **Claim:** the verifier marks wrong answers as correct often enough to be
  unusable as an autonomous gate.
- **Metric:** `false_green_rate`
- **Threshold:** >= **15%**
- **Falsified if:** the upper bound of the Wilson 95% CI for
  `false_green_rate` is below **0.15**.
- **Prediction:** 25-40%.

### H2 — Self-verification buys little accuracy for a lot of cost

- **Claim:** the accuracy gain from self-verification is small relative to its
  token cost, so it is a poor default.
- **Metric:** `delta_pass_at_1` (percentage points) and `cost_multiplier`
- **Threshold:** `delta_pass_at_1` < **10** pp **and** `cost_multiplier` >= **1.8**x
- **Falsified if:** `delta_pass_at_1` >= 10 pp, **or** `cost_multiplier` < 1.8x.
  Both conjuncts must hold for H2 to survive; either one failing falsifies it.
- **Prediction:** delta of 0-6 pp at 2.0-2.6x cost.

### H3 — Verifier confidence is poorly calibrated

- **Claim:** the confidence number the verifier emits does not track the
  probability that it is right.
- **Metric:** `ece` (expected calibration error, 10 equal-width bins)
- **Threshold:** > **0.15**
- **Falsified if:** the point estimate of `ece` is <= **0.15**.
- **Prediction:** 0.20-0.35, driven by mass at confidence >= 90.

### H4 — Per-run accuracy overstates reliability

- **Claim:** an agent that is right most of the time is not an agent you can
  run unattended, because per-task consistency is much lower than per-run
  accuracy.
- **Metric:** `pass_at_1` and `pass_hat_k` (k=5) in the same mode
- **Threshold:** `pass_at_1 - pass_hat_k` >= **20** pp in baseline mode
- **Falsified if:** the gap is < 20 pp.
- **Prediction:** 25-40 pp.

### H5 — The verifier is confidently wrong, not uncertainly wrong

- **Claim:** false greens are not low-confidence guesses; they arrive with high
  stated confidence, which is what makes them dangerous.
- **Metric:** `mean_confidence_on_false_greens`
- **Threshold:** >= **70** (on the 0-100 scale)
- **Falsified if:** mean confidence on false greens is < 70, or fewer than 5
  false greens exist to average over (in which case H5 is *undetermined*, not
  supported — this is reported, not silently dropped).
- **Prediction:** 80-95.

## Metric definitions

Notation: `N` = number of tasks (10). `R` = runs per task per mode (5).
`c_i` = number of correct runs for task `i`. An outcome is **correct** only when
the task's deterministic assert suite passes in full.

### pass_at_1

Mean per-run correctness, averaged over tasks so that no task contributes more
than 1/N regardless of run count.

- **Formula:** `pass_at_1 = (1/N) * sum_i(c_i / R)`
- Reported per mode, with a Wilson 95% CI computed over the `N*R` Bernoulli
  trials.

### pass_hat_k

Fraction of tasks solved on **every** one of the k runs. This is the reliability
measure: it answers "would this task have survived k unattended attempts".

- **Formula:** `pass_hat_k = (1/N) * sum_i(1 if c_i == k else 0)`, with k = R = 5
- Distinct from pass@k (any-of-k). We report pass^k because the question is
  reliability, not best-of-n sampling.

### false_green_rate

The headline metric. Probability that the verifier says "correct" given that
ground truth says the answer is wrong.

- **Formula:** `false_green_rate = |{r : verdict(r)=correct AND truth(r)=wrong}| / |{r : truth(r)=wrong}|`
- Domain: `self_verify` records only, restricted to those whose *pre-revision*
  answer was wrong; the verdict is about the answer the verifier was shown.
- Wilson 95% CI over the denominator.
- Degenerate case: if the denominator is 0 the metric is `null`, never `0.0`.

### false_red_rate

The symmetric error, reported so the verifier is not judged on one tail only.

- **Formula:** `false_red_rate = |{r : verdict(r)=wrong AND truth(r)=correct}| / |{r : truth(r)=correct}|`

### verifier_accuracy

How often the verdict matches ground truth at all.

- **Formula:** `verifier_accuracy = |{r : verdict(r) == truth(r)}| / |{r : verdict(r) is not null}|`

### delta_pass_at_1

- **Formula:** `delta_pass_at_1 = 100 * (pass_at_1(self_verify) - pass_at_1(baseline))`
- Units: percentage points. Sign is meaningful; a negative value means
  self-verification made the agent worse.

### cost_multiplier

- **Formula:** `cost_multiplier = total_cost_usd(self_verify) / total_cost_usd(baseline)`
- where `total_cost_usd = sum over calls of (input_tokens * price_in + output_tokens * price_out) / 1e6`

### cost_per_solved_task

- **Formula:** `cost_per_solved_task = total_cost_usd(mode) / |{r in mode : truth(r) = correct}|`
- `null` when the mode solved nothing.

### ece

Expected calibration error over verifier confidence, 10 equal-width bins on
`confidence/100` with edges at 0.0, 0.1, ..., 1.0.

- **Formula:** `ece = sum_b (n_b / N_conf) * |acc_b - conf_b|`
- where `n_b` = records in bin b, `N_conf` = records with a parsed confidence,
  `acc_b` = fraction of bin b where the verdict matched ground truth,
  `conf_b` = mean stated confidence in bin b (as a 0-1 fraction).
- Empty bins contribute 0.

### mean_confidence_on_false_greens

- **Formula:** `mean_confidence_on_false_greens = mean(confidence(r)) for r in false greens`

### verdict_parse_failure_rate

Harness-health metric. A verification response the harness could not parse is a
potential *harness-manufactured* false green, so it is measured, not swallowed.

- **Formula:** `verdict_parse_failure_rate = |{r : verdict(r) is null}| / |{r in self_verify}|`
- Gate G4 fails if this exceeds 0.02.

### hardcode_rate

Validity metric added in Phase 5 (see Amendments). Fraction of graded artifacts
that satisfied every **visible** assert and then failed a **held-out** one — the
signature of a solution written against the stated examples rather than the
requirement.

- **Formula:** `hardcode_rate = |{r : passes all visible asserts AND fails a hidden assert}| / |{r : produced a gradable artifact}|`
- A high value invalidates pass@1 as a measure of the requirement, so it is
  reported beside it rather than buried.

### Wilson 95% confidence interval

Applied to every rate above. Normal-approximation (Wald) intervals are wrong at
the small `n` and near-0/1 rates this experiment produces, so they are not used.

- **Formula:** for `k` successes in `n` trials, `p = k/n`, `z = 1.959964`:
  `center = (p + z^2/(2n)) / (1 + z^2/n)`,
  `halfwidth = (z / (1 + z^2/n)) * sqrt(p(1-p)/n + z^2/(4n^2))`,
  `CI = [max(0, center - halfwidth), min(1, center + halfwidth)]`

## Task design

Ten tasks. Every task is a Python function or a SQL query with a fixed
signature, so ground truth is a deterministic assert suite executed against the
agent's artifact — never a judgement about it, and never another model.

Each task is built around a **silent-failure mode**: an implementation that is
the natural first thing to write, passes the obvious case, and fails a specific
edge case. That is the property that makes verification hard and generation
easy, which is precisely the asymmetry under test.

**Assert spec** below is the contract; the executable version lives in
`tasks/<id>.py` as `ASSERTS`, and gate G3 checks the two agree in count.

### T01 — csv_quoted

- **Type:** data parsing with edge cases
- **Prompt asks for:** `parse_csv_line(line, delimiter=',')` splitting one CSV record into fields.
- **Silent-failure mode:** `line.split(delimiter)` — correct on `a,b,c`, wrong on a quoted field containing the delimiter, on a doubled `""` escape, and on an unterminated quote. The added delimiter parameter and unterminated-quote rule interact: a parser that special-cases commas passes the first cases and fails the rest.
- **Assert spec:** 8 visible checks, plus 5 held-out checks not shown here or in the prompt (Amendment A1).
```text
parse_csv_line('a,b,c') == ['a', 'b', 'c']
parse_csv_line('"a,b",c') == ['a,b', 'c']
parse_csv_line('"say ""hi""",x') == ['say "hi"', 'x']
parse_csv_line('a,,c') == ['a', '', 'c']
parse_csv_line('a;b;c', ';') == ['a', 'b', 'c']
parse_csv_line('"x;y";z', ';') == ['x;y', 'z']
parse_csv_line(' a , b ') == [' a ', ' b ']
parse_csv_line('"unterminated,rest') == ['unterminated,rest']
```

### T02 — semver_sort

- **Type:** data parsing with edge cases
- **Prompt asks for:** `sort_versions(versions)` ascending by semantic-version precedence, including pre-releases.
- **Silent-failure mode:** Lexicographic `sorted()` — wrong the moment a component reaches 10, and wrong in the opposite direction on pre-releases: `'1.0.0' < '1.0.0-alpha'` as text, while semver ranks the pre-release BELOW the release.
- **Assert spec:** 6 visible checks, plus 4 held-out checks not shown here or in the prompt (Amendment A1).
```text
sort_versions(['1.9.0', '1.10.0']) == ['1.9.0', '1.10.0']
sort_versions(['1.0.0', '1.0.0-alpha']) == ['1.0.0-alpha', '1.0.0']
sort_versions(['1.0.0-beta', '1.0.0-alpha']) == ['1.0.0-alpha', '1.0.0-beta']
sort_versions(['1.0.0-alpha.10', '1.0.0-alpha.2']) == ['1.0.0-alpha.2', '1.0.0-alpha.10']
sort_versions(['2.0.0', '10.0.0', '1.0.0']) == ['1.0.0', '2.0.0', '10.0.0']
sort_versions([]) == []
```

### T03 — sql_left_join_count

- **Type:** SQL with subtle predicates
- **Prompt asks for:** a query returning every customer's name, non-cancelled order count, and spend.
- **Silent-failure mode:** Filtering `status <> 'cancelled'` in `WHERE` instead of inside the aggregate silently converts the LEFT JOIN back into an inner join, dropping every customer with no orders AND every customer whose orders were all cancelled. The query reads as obviously correct. `SUM` over no rows also yields NULL rather than 0.0.
- **Assert spec:** 6 visible checks, plus 3 held-out checks not shown here or in the prompt (Amendment A1). SQL tasks are additionally re-run against a second fixture.
```text
rows == [('Ada', 2, 65.0), ('Linus', 1, 15.0), ('Grace', 0, 0.0)]
len(rows) == 3
[r[0] for r in rows] == ['Ada', 'Linus', 'Grace']
dict((r[0], r[1]) for r in rows)['Grace'] == 0
dict((r[0], r[2]) for r in rows)['Grace'] == 0.0
all(isinstance(r[1], int) for r in rows)
```

### T04 — sql_not_in_null

- **Type:** SQL with subtle predicates
- **Prompt asks for:** products never genuinely ordered, where an order needs a positive quantity.
- **Silent-failure mode:** `WHERE id NOT IN (SELECT product_id ...)` returns the EMPTY set whenever the subquery yields a NULL, because `x NOT IN (..., NULL)` is UNKNOWN. Adding the `qty > 0` condition inside the subquery quietly changes which rows land in the exclusion set.
- **Assert spec:** 6 visible checks, plus 3 held-out checks not shown here or in the prompt (Amendment A1). SQL tasks are additionally re-run against a second fixture.
```text
rows == [('Flange',), ('Sprocket',), ('Widget',)]
len(rows) == 3
rows != []
('Flange',) in rows
('Gizmo',) not in rows
all(len(r) == 1 for r in rows)
```

### T05 — bugfix_mutable_default

- **Type:** small bug fix
- **Prompt asks for:** a fix for `add_item(item, bucket=[], limit=None)` keeping the most recent `limit` items.
- **Silent-failure mode:** Three interacting bugs: the shared mutable default is invisible until the second call; `if limit:` treats a real `limit=0` as 'no limit'; and `bucket[:limit]` keeps the FIRST items where the spec says the last.
- **Assert spec:** 6 visible checks, plus 4 held-out checks not shown here or in the prompt (Amendment A1).
```text
add_item('a') == ['a']
add_item('b') == ['b']
add_item('c', ['x']) == ['x', 'c']
(add_item('a'), add_item('b'))[1] == ['b']
add_item('d', ['a', 'b', 'c'], 2) == ['c', 'd']
add_item('d', ['a', 'b'], 0) == []
```

### T06 — bugfix_half_up_rounding

- **Type:** small bug fix
- **Prompt asks for:** `round_money(x)` rounding to cents half-up, accepting floats and decimal strings.
- **Silent-failure mode:** Python's `round()` is banker's rounding — `round(2.675, 2)` is 2.67 — and it loses money. The string-input requirement adds a second trap: `Decimal(float)` still yields 2.67 because the binary float is 2.67499...; only `Decimal(str(x))` is correct.
- **Assert spec:** 8 visible checks, plus 4 held-out checks not shown here or in the prompt (Amendment A1).
```text
round_money(2.675) == 2.68
round_money(0.125) == 0.13
round_money(1.005) == 1.01
round_money(2.674) == 2.67
round_money(-1.005) == -1.01
round_money('2.675') == 2.68
round_money('0.125') == 0.13
round_money(10.0) == 10.0
```

### T07 — offbyone_insert_position

- **Type:** off-by-one algorithmics
- **Prompt asks for:** `insert_position(sorted_list, target, key=None, descending=False)`, the leftmost index.
- **Silent-failure mode:** A binary search that returns the RIGHTMOST position on duplicates passes on distinct input. `key` and `descending` compound it: the comparison must invert for descending while the leftmost rule stays, which a naive `<=` swap gets backwards.
- **Assert spec:** 8 visible checks, plus 5 held-out checks not shown here or in the prompt (Amendment A1).
```text
insert_position([1, 3, 5], 3) == 1
insert_position([1, 3, 3, 3, 5], 3) == 1
insert_position([1, 3, 5], 0) == 0
insert_position([1, 3, 5], 9) == 3
insert_position([], 4) == 0
insert_position([5, 3, 1], 3, None, True) == 1
insert_position([5, 3, 3, 1], 3, None, True) == 1
insert_position(['a', 'bb', 'ccc'], 'dd', len) == 1
```

### T08 — offbyone_window_max

- **Type:** off-by-one algorithmics
- **Prompt asks for:** `max_window_sum(nums, k)` returning `(best_sum, start_index)`.
- **Silent-failure mode:** `range(len(nums) - k)` drops the final window, so the answer is right whenever the max is not at the tail. Tie-breaking compounds it: `>=` keeps the LAST tied window where the spec demands the earliest, and `k <= 0` must be rejected rather than treated as valid.
- **Assert spec:** 9 visible checks, plus 5 held-out checks not shown here or in the prompt (Amendment A1).
```text
max_window_sum([1, 2, 3, 4], 2) == (7, 2)
max_window_sum([5, 1, 1, 1], 2) == (6, 0)
max_window_sum([1, 1, 1, 9], 2) == (10, 2)
max_window_sum([1, 2, 3], 3) == (6, 0)
max_window_sum([2, 2, 2], 2) == (4, 0)
max_window_sum([1, 2], 3) is None
max_window_sum([], 1) is None
max_window_sum([1, 2, 3], 0) is None
max_window_sum([-5, -1, -9], 2) == (-6, 0)
```

### T09 — json_path_get

- **Type:** data parsing with edge cases
- **Prompt asks for:** `json_get(data, path, default=None)` resolving a dotted path with negative indices.
- **Silent-failure mode:** Truthiness (`if not value: return default`) collapses a legitimate `0`, `False`, `''` or `[]` into the default. Negative indices and numeric-looking DICT keys interact: treating any digit segment as an index breaks `{'1': 'x'}`, while ignoring the sign breaks `'a.-1'`.
- **Assert spec:** 10 visible checks, plus 6 held-out checks not shown here or in the prompt (Amendment A1).
```text
json_get({'a': {'b': 1}}, 'a.b') == 1
json_get({'a': {'b': 0}}, 'a.b', 'D') == 0
json_get({'a': {'b': None}}, 'a.b', 'D') is None
json_get({'a': [10, 20]}, 'a.1') == 20
json_get({'a': [10, 20]}, 'a.-1') == 20
json_get({'a': [10]}, 'a.5', 'D') == 'D'
json_get({'1': 'x'}, '1') == 'x'
json_get({'a': {'b': 1}}, 'a.c', 'D') == 'D'
json_get({'a': {'b': False}}, 'a.b', 'D') is False
json_get({}, 'a', 'D') == 'D'
```

### T10 — offbyone_business_days

- **Type:** off-by-one algorithmics
- **Prompt asks for:** `business_days(start_iso, end_iso, holidays=())` inclusive of both endpoints.
- **Silent-failure mode:** Iterating `start` to `end` exclusive silently undercounts by one whenever the end date is a working day. Holidays compound it: subtracting every holiday in range double-counts a holiday that fell on a weekend and was never counted in the first place.
- **Assert spec:** 8 visible checks, plus 5 held-out checks not shown here or in the prompt (Amendment A1).
```text
business_days('2024-02-26', '2024-03-01') == 5
business_days('2024-02-28', '2024-03-01') == 3
business_days('2024-03-01', '2024-03-01') == 1
business_days('2024-03-02', '2024-03-02') == 0
business_days('2023-12-29', '2024-01-01') == 2
business_days('2024-03-05', '2024-03-04') == 0
business_days('2024-02-26', '2024-03-01', ['2024-02-28']) == 4
business_days('2024-02-26', '2024-03-01', ['2024-03-02']) == 5
```

## Threats to validity, stated up front

1. **Single model, single tier.** Conclusions are about `claude-haiku-4-5`.
2. **n = 10 tasks.** Task-level CIs are wide; per-task breakdown is always
   reported alongside aggregates, never averaged away.
3. **Task distribution is adversarial by construction.** Every task has a
   planted silent-failure mode. This inflates absolute error rates relative to
   average work; it does not affect the *relative* generate-vs-verify gap, which
   is the claim.
4. **Live runs are not seed-reproducible** (see above).
5. **The harness could manufacture false greens** through answer-extraction
   bugs. Phase 5 is dedicated to attacking exactly this.

## Amendments

The design above was frozen at Phase 1 and is not edited to match results. These
are changes made afterwards, each with its date, reason and effect.

### A1 — held-out asserts (Phase 5, adversarial review)

**Reason.** The Phase 5 attack probe found that an artifact containing a lookup
table keyed on the exact assert inputs passed every task it was tried on. The
oracle could not distinguish "solved the requirement" from "matched the
examples", which is the same silent-failure class the experiment exists to
measure — so the harness had it too.

**Change.** Every task gains a `hidden_asserts` set, never shown in the prompt
and drawn from different inputs; SQL tasks additionally gain a
`hidden_fixture`, and the candidate's query is re-run against it. An artifact is
`correct` only if it passes both phases. The visible assert specs above are
unchanged, so every count in the task design still matches.

**Effect on results.** Strictly stricter: some artifacts that would have graded
`correct` now grade `wrong`. Baseline pass@1 can therefore only move down, which
is accounted for in Phase 4 calibration.

### A2 — boundary-aware threshold comparison (Phase 5)

**Reason.** Two hypothesis verdicts were decided by floating-point noise rather
than by evidence: `100 * (0.65 - 0.55)` is `9.999999999999998`, and an ECE of
exactly 0.15 computes as `0.15000000000000002`. Both reported the wrong verdict.

**Change.** All threshold comparisons go through `hypotheses.compare`, which
treats a value within `1e-9` of the threshold as sitting exactly on it and lets
the operator decide from there (`>=` holds, `>` does not). Verdicts decided at
the boundary are flagged as such in the output.

**Effect on results.** No threshold moved. A verdict can no longer be produced
by rounding error, and a knife-edge verdict is now visibly a knife-edge verdict.

### A3 — provider and model (Phase 4)

**Reason.** No Anthropic credentials were available, and a DeepSeek key was.
Phase 4 was otherwise blocked indefinitely, and an experiment that never runs
measures nothing. The provider is now config-selected; `AnthropicProvider`
remains in the code and is the intended path for experiment 2's cross-provider
comparison.

**Change.** `provider: deepseek`, `model: deepseek-v4-flash`, reached through
the OpenAI-compatible endpoint with the `openai` SDK. This is a deliberate
deviation from the original "direct Anthropic SDK" constraint, made at the
maintainer's direction and recorded here rather than absorbed silently.

**What the switch forced, all discovered by probing the API rather than by
assumption:**

1. **`deepseek-v4-flash` is a reasoning model.** Most completion tokens are
   reasoning tokens that never appear in the response. At `max_tokens: 2048`,
   `deepseek-v4-pro` returned `finish_reason="length"` with 2047 reasoning
   tokens and an **empty** response — which this harness would have graded as a
   refusal and scored as a model failure. `max_tokens` is now 4096, `v4-flash`
   is pinned rather than `v4-pro`, and a new `truncation_rate` metric is gated
   by G4 at 2% so this failure mode cannot contaminate a run unnoticed.
2. **`response_format: {"type": "json_schema"}` returns HTTP 400**
   ("This response_format type is unavailable now"). Structured verdicts fall
   back to `json_object` mode, negotiated once per run. The tolerant parser in
   `verdict.py` absorbs the difference and `verdict_parse_failure_rate`
   measures what it cost.
3. **Cache hits are billed ~31x cheaper than misses.** Self-verify's second
   call resends the generation prompt verbatim, so it earns cache hits that
   baseline cannot. Pricing input as a single rate would have overstated
   self-verify's cost and inflated the H2 cost multiplier — the metric H2 turns
   on. Hit and miss tokens are now recorded and priced separately.
4. **Prices double during peak hours** (01:00-04:00 and 06:00-10:00 UTC). Costs
   are computed at a declared tier (`peak`, the conservative choice) so the
   metric is reproducible from raw token counts instead of depending on when
   the run happened to execute.

**Effect on the hypotheses.** None were changed. H2's thresholds are stated in
multiples and percentage points, not dollars, so they transfer unchanged. The
calibration window (baseline pass@1 in 50-70%) is model-dependent by
construction and is what Phase 4 calibrates against.

**Effect on external validity.** The conclusions are now about
`deepseek-v4-flash`. The limitation was always "single model, single tier"; only
the model's identity changed.

### A4 — task difficulty (Phase 4, calibration round 1)

**Reason.** Round 1 measured baseline pass@1 at **98%** (49/50), far above the
50–70% window. Zero wrong answers reached the verifier, so `false_green_rate`
had an empty denominator and H1 was UNDETERMINED. The task set could not produce
the errors the experiment exists to measure.

**Diagnosis.** The tasks were designed against a model that answers quickly.
Each plants a silent-failure mode a naive implementation walks into; a model
spending 11k–30k reasoning tokens per answer finds them. Extended reasoning
closes the generation gap on small self-contained problems.

**Change.** Every task keeps its original silent-failure mode and gains two or
three **interacting** requirements — constraints where satisfying one naturally
breaks another. Uniformly applied to all ten tasks, not only the ones the model
aced, so the adjustment cannot be mistaken for tuning toward a target. Visible
asserts grew 61 → 75; held-out asserts 44. The Task design section above shows
the current specs; CALIBRATION.md records the before/after per task.

**Not changed.** No hypothesis, threshold, metric definition, or oracle
behaviour. Difficulty is the only knob the calibration loop authorises, and it
is the only one that moved.
