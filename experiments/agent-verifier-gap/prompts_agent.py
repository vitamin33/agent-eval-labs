"""Prompts for the agent arm.

`inject` and `inject_verify` differ by exactly one thing: VERIFY_BLOCK appended
to the system prompt. A test reconstructs one from the other and asserts the
residue is only that block, as in experiment 1 — otherwise a difference in
detection could come from better wording rather than from the intervention.
"""

from __future__ import annotations

BASE_SYSTEM = (
    "You are an operations agent working against an order database through tools.\n"
    "Use the tools to complete the task, then call `submit` exactly once with your "
    "result.\n"
    "`claims_success` is your own judgement about whether you completed the task "
    "correctly, and `confidence` is how sure you are of that judgement."
)

VERIFY_BLOCK = (
    "\n\nBefore each tool call, briefly check whether the information you already "
    "have is mutually consistent. If two tools disagree, or a result contradicts "
    "something you established earlier, resolve the discrepancy before continuing."
)


def system_prompt(mode: str) -> str:
    if mode == "inject_verify":
        return BASE_SYSTEM + VERIFY_BLOCK
    return BASE_SYSTEM


def task_prompt(task: dict) -> str:
    from agent_tasks import ANSWER_SHAPES

    return f"{task['goal']}\n\nSubmit `answer` as {ANSWER_SHAPES[task['answer_shape']]}."
