# Persona round prompt

One subagent per post, a smaller model (Sonnet), fresh context. Replace
`<POST>`. Launch the posts in parallel and wait for the completion
notifications; never read the transcript files.

---

You are running a simulated read-through of a blog draft by six reader personas. You have NOT seen the author's reasoning; only the text is evidence.

1. Read `~/.claude/skills/audience-clarity/personas.md` in full. It defines six personas, the exact answer shape for each, and the readiness bar.
2. Read the draft `<POST>` in full (skip the YAML frontmatter).
3. Play each persona in turn, in a single pass, without letting one persona's answer leak into the next. For each persona answer in EXACTLY the shape personas.md gives (first-screen understanding yes/partly/no plus a one-sentence restatement of the main claim with its number; value 1-5; kept reading yes/no plus the deciding sentence; two sentences where this reader was lost or stopped trusting, quoted verbatim; one question they would ask the author).
4. Then write a "Round summary" section: whether the readiness bar is met (every persona "yes" on first-screen understanding, engineer value >= 4, no losing sentence shared by two or more personas), the losing sentences shared by two or more personas (quoted), and at most five concrete fixes ranked by how many personas they help, each with the quoted text and a replacement that keeps every number.

Do not rewrite the post. Do not run any scripts. Report only the persona answers and the round summary, in English, as plain markdown without tables.

---

When applying a suggested replacement, rewrite it in the voice first: no
em-dash, no antithesis, one notation per number, and check that every number
in it exists in the source pack (`make source-pack`).
