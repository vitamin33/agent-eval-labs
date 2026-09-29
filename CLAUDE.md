# agent-eval-labs — how to work in this repository

Public repository of agent-reliability experiments, and the source of the
blog posts written from them. Two loops live here: the research loop and the
publishing loop. Both are gated; a result or a post that has not passed its
gate is not done.

## The research loop

Phases, in order, each with a gate in `gates.py` (`make gates`):

1. `RESEARCH.md`: hypotheses with numeric thresholds, written before any data
   and held by a test so nobody can move a threshold after the fact. Metrics
   with formulas. Ground truth is ordinary code (asserts, a grader in a
   subprocess), never another model.
2. `PLAN.md`: every task has a runnable verification command.
3. Implementation: pytest green, a dry run with the mock provider, a planted
   false green that the grader catches, a prompt diff.
4. The live run: raw JSONL records with per-call tokens and cost (schema v2:
   cache hit/miss/write, served model, pricing tier, config sha256, harness
   commit). Gate G4 checks the served model against the pinned id; a run
   served off-pin is named, never silently dropped or silently promoted.
5. `RESULTS.md`, `CALIBRATION.md`, `REVIEW.md`: every rate with its Wilson
   95% interval, every failed calibration round written up, every risk with a
   proof that runs.
6. `README.md`: the question, the result, what it means for a team, what it
   does not show, one-command reproduction. Every number in the prose is
   recomputed from the raw records by `tests/test_readme_numbers.py`.

Rules that are not negotiable: pre-register before data; no rounding; no
cherry-picking runs (the published run is the newest on the pinned model,
every other run is a named replication comparison, `pick.py`); cost
accounting per task, per correct answer, per false green; report boring
numbers plainly; the result counts only when it reproduces from scratch.

Experiment 3 (`experiments/agent-checkpoint/`) measured deterministic
checkpoints at hand-off points; stages 1 and 2 are complete. Its stage 3, a
cross-model replication (Claude Haiku 4.5, Gemini 3.8 Flash) plus the
unexplained-wrapper arm on DeepSeek, is pre-registered in RESEARCH.md with
its own configs and waits for `ANTHROPIC_API_KEY` and `GEMINI_API_KEY`.

## The publishing loop

`docs/PUBLISHING.md` is the procedure. The short form:

1. A post may cite only numbers that exist in a published artifact here
   (`make source-pack` lists them). Derive new numbers in the repo, test-held,
   before citing them.
2. Draft in Vitalii's voice with the `/voice` skill (installed from the
   private ascend repo; this repo never vendors the voice rules). Shape in
   `docs/templates/post.mdx`: number-first claim, short-version block,
   why, what, Monday actions, what this does not show, FAQ, one lesson.
   Complicated things in ordinary words: a CTO must be able to repeat the
   claim with its number after the first screen.
3. `make post-check POST=<path>`: frontmatter, shape (no tables, FAQ shape,
   limits section, repo link), number grounding (unit-bearing numbers must
   be in the sources), then `/voice`, `/audience-clarity` and ascend's slop
   gate. SKIPPED is not PASS.
4. Persona round: six fresh readers per post via subagents
   (`docs/templates/persona_round_prompt.md`). Bar: all six understand the
   claim on the first screen, engineer value >= 4, no losing sentence shared
   by two readers. Fix by glossing, never by cutting a number.
5. Publish to serbyn-pro `main` (Vercel deploys), confirm the live title.

## Conventions

- Python 3.12 and 3.14 in CI; stdlib for tools; tests in `tests/`.
- Experiments live in `experiments/<name>/` (hyphenated, put on `sys.path` by
  `tests/conftest.py`). Raw results are committed. Drafts go in `drafts/`
  (gitignored) or on a branch of the site repo, never only in the scratchpad.
- Commit on a branch; `main` moves by fast-forward after gates and tests.
- Memory for cross-session facts about this repo is in the Claude Code
  project memory; the model rename of September 2026 is recorded there.
