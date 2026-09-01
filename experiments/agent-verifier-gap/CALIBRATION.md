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

Pending.
