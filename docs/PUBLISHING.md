# Publishing a post from an experiment

The loop that produced the September 2026 series, written down so the next
session does not rediscover it. Every step has a command. The order matters:
numbers first, prose second, readers third, site last.

## 0. Preconditions

- The experiment is complete: `make gates` green, `RESULTS.md` and
  `CALIBRATION.md` written, and every number in `README.md` held by a test
  (`tests/test_readme_numbers.py` is the pattern: recompute from the raw JSONL,
  assert the prose matches). A post may only cite numbers that exist in those
  artifacts. If a post needs a number that is not there, publish it there
  first, test-held, and only then in the post.
- Skills installed from ascend: `make skill-sync` there puts `/voice` and
  `/audience-clarity` in `~/.claude/skills/`. `tools/post_check.py` reports
  them as SKIPPED when absent; a SKIPPED check is not a pass.
- The site checkout is current: `git -C ~/development/serbyn-pro fetch origin`
  and look at `origin/main:content/blog` before deciding a post is new. In
  September a stale checkout hid two live posts and a "new" flagship turned
  out to be a rewrite of a live URL.

## 1. Source pack

```
make source-pack            # every number a post may use, from the artifacts
```

Draft with that list open. Derived numbers (a ratio of two published numbers,
a total across runs) are not in the pack until they are published in the
README or a results file with a test. Do the derivation in the repo, not in
the post.

## 2. Draft, in the voice

`/voice draft` with the compiled voice from ascend. The shape that survived
three persona rounds is in `docs/templates/post.mdx`: claim with its number in
the first sentence, a short-version block, why, what and what came out, what
a team does on Monday, what this does not show, FAQ, one transferable lesson,
the series list, the repo link. Rules that cost the most rewrites:

- One antithesis at most, as the hook. None in the body.
- Labelled bullets (`**Label.** text`) only in the short-version block. In
  the body the point that matters gets a paragraph; minor points get a clause.
- Say "the check", "my own code"; never "gate", "harness" without a gloss.
  A proper name from the repo (G4) needs its plain meaning in the same sentence.
- Every term glossed in the sentence it first appears in.
- No tables (the renderer prints raw pipes), `##`/`###` only, mermaid and
  code fences are fine, links relative (`/blog/<slug>`), FAQ items as
  `**Question?** Answer.` paragraphs so they parse into FAQ schema.
- Keep drafts in a place that survives context compaction: a branch of the
  site repo, or `drafts/` here (gitignored). The scratchpad is wiped.

## 3. Check

```
make post-check POST=~/development/serbyn-pro/content/blog/<slug>.mdx
```

Runs, in order: frontmatter (required fields, category in the four the
publisher accepts, date shape, description length), shape (tables, heading
depth, FAQ, limits and summary sections, repo link), number grounding against
the source pack (unit-bearing numbers FAIL, bare counts WARN), then the
external checkers: `/voice` (score and findings), `/audience-clarity`
(score and findings), ascend's slop gate (banned phrases, burstiness,
ungrounded metrics). Fix every FAIL and every voice `block` before step 4.

## 4. Persona round

Six fresh readers, one subagent per post, in a context that has not seen the
author's reasoning. The prompt is `docs/templates/persona_round_prompt.md`;
run it with a smaller model (Sonnet), one agent per post, in parallel, and
wait for the completion notification. Do not read the transcript file.

Readiness bar (from `personas.md`): every persona "yes" on first-screen
understanding, the engineer persona at value 4 or more, and no losing
sentence quoted by two or more personas. Two rounds is normal. A third means
the structure is wrong; change the structure, do not polish sentences.

Fix by glossing, never by cutting a number. Re-run step 3 after edits.

## 5. Publish

- Commit on a branch of the site repo with the check scores in the message.
- `next build` once (symlink `node_modules` from the main checkout if the
  worktree has none, remove the symlink after).
- Fast-forward `main`, push; Vercel deploys production from `main` within a
  minute. Confirm with the live `<title>`:
  `curl -sL https://serbyn.io/blog/<slug> | grep -o '<title>[^<]*'`.
- A rewrite of a live post keeps slug and date and adds an "Updated <date>"
  line; the title may change.

## Pitfalls this loop has already paid for

- Splicing a body under frontmatter: read the new body before opening the
  target for writing. `open(f, "w").write(open(body).read())` truncates the
  post when the body path is wrong.
- zsh does not word-split `set -- $var`; loop with `read -r a b <<< "$pair"`.
- A git worktree lacks untracked files from the main checkout.
- Subagents on a rate limit die silently; wait for the task notification, do
  not poll the transcript.
- Every number in a post has been questioned by at least one persona. Give it
  a baseline and a consequence in the same sentence.
