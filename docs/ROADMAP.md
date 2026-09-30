# Roadmap: where the experiments go next, and who each one is for

> Written 2026-09-30 after experiment 3 shipped. Each candidate states the
> question, the number a reader could repeat, who pays attention, what it
> costs, and what must be true before it runs. Order is a recommendation;
> every entry is pre-registered on its own before any data.

## What is established (three experiments, 1101 records, $6.80)

- A model checking a single answer catches every planted bug (0 of 50
  approved) and rejects some good ones (5 of 50). Self-verification on short
  answers is a tax with no refund at 1.64x.
- An agent over a twelve-step task does not notice a silently wrong tool
  result (8 of 70), keeps working on it (median 8 steps), and when it ends
  wrong it says "done" every time (45 of 45, then 22 of 22, then 20 of 20,
  on two model versions). A "double-check yourself" prompt changes nothing.
- A deterministic checkpoint in the code around the agent removes every
  silent failure (0 of 40, twice) at the cost of no checkpoint (1.00x,
  0.86x). The same checkpoint as an optional tool is used constantly (38 of
  40), costs 1.94x, and leaves 6 of 40. Without the one sentence naming the
  checkpoint as authoritative: 4 of 40, all on the task where "the two
  disagree" is itself an answer, at 1.58x.

## Next, in order

### 1. Cross-model replication (exp3 stage 3, pre-registered, code ready)

**Question.** Is "every wrong run claims success" and "the enforced
checkpoint removes them" a property of one cheap model or of tool-calling
agents. **Number a reader repeats.** Silent failure rate with and without
the checkpoint on Claude Haiku 4.5 and Gemini 3.8 Flash. **For whom.** CTO
and head of AI (which model to trust, what to mandate), investors (is the
risk general). **Cost.** ~$9 at k = 5 on both models, ceiling $10.
**Blocked on.** `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`. Run
`tools/ping_provider.py --config <cfg>` first, then stage 0, 3, 4.

### 2. The checkpoint that is sometimes wrong (exp4)

**Question.** Production sources of truth are slow, partial, and sometimes
wrong. If the checkpoint disagrees with a correct tool result X% of the
time, does the agent, told the checkpoint is authoritative, follow it into a
wrong answer? Is there a new failure mode: blind trust in the check.
**Number.** Silent failures per fired injection when the checkpoint is
right 100 / 95 / 80% of the time, plus the new false-red count (correct
results overridden). **For whom.** CTO and AI builders (the deployable
pattern has a precondition: the source of record must be better than the
tool, and by how much). **Cost.** DeepSeek, three noise levels, ~$2.
**Design note.** The checkpoint noise is planted by code with a fingerprint,
like the injections, so every override is attributable.

### 3. Where to put the checkpoint: the cost curve (exp5)

**Question.** Every call was free here because the agent stopped
re-deriving. Is checkpointing only writes, only the last read before
`submit`, or every third call cheaper, and what does each miss? **Number.**
Cost per avoided silent failure at four placements. **For whom.** CTO and
business owner (a budget line per policy), AI builders (which hook to
wrap). **Cost.** DeepSeek, four arms, ~$3. **Design note.** "Writes only"
is pre-registered to catch nothing on six of eight tasks; that is the point,
not a flaw.

### 4. Confidence is not a signal (derived, no new run)

**Question.** Can a team route human review by the agent's own confidence
score? **Number.** Across every silent failure in exp2 and exp3, the
reported confidence, next to the confidence on correct runs (in exp3 all 28
silent failures scored 95 to 100). **For whom.** CEO and business owner
(the review policy most teams have is "check the ones the agent is unsure
about"; the data says that policy reviews nothing). **Cost.** $0, computed
from the raw records, test-held like every README number. A short post.

### 5. Hand-offs between agents (exp6, flagship candidate)

**Question.** Where does a silent failure go when one agent hands work to
another: is the boundary where it propagates or where it can be caught?
**Number.** Silent failure rate after a hand-off with the checkpoint at the
boundary, inside the first agent, inside the second, and nowhere. **For
whom.** Everyone building multi-agent systems, and every buyer of one.
**Cost.** DeepSeek, ~$5. **Blocked on.** A two-agent version of the loop:
the first agent's `submit` becomes the second's task prompt, and the
injection is the first agent's output.

### 6. Longer, messier trajectories (exp7)

**Question.** Do the rates hold at 30 to 50 steps over a realistic API
surface, with tools that sometimes fail loudly as well as silently?
**Number.** Silent failure rate and checkpoint cost multiplier at 3x the
trajectory length. **For whom.** AI builders and the engineer persona who
asked "does this hold outside a toy". **Cost.** ~$6 on DeepSeek; more
elsewhere. **Blocked on.** A second environment (ticketing or inventory)
with 40+ records and a scripted fault-injection layer.

## Two things that are not experiments

- **A drop-in checkpoint wrapper.** The enforced arm is forty lines: wrap
  every tool call, re-run the read against the record, return both, add the
  sentence. Packaged as a library with the exp3 tests, it is the artefact an
  AI-builder reader adopts on Monday and the thing a business owner can ask
  a vendor to show.
- **The silent failure rate as the number to ask for.** Per fired injection,
  with its interval. The posts already say it; a one-page definition with
  the formula and the three measured baselines gives a CTO something to put
  in a vendor questionnaire.
