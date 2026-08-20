"""Prompt text for both modes.

The experiment's central methodological constraint lives here: the generation
prompt is byte-identical in both modes. `self_verify` differs from `baseline`
by exactly one thing — an extra conversational turn containing
VERIFICATION_BLOCK. Nothing else may differ, and `tests/test_prompt_diff.py`
reconstructs one mode's messages from the other's to prove it.
"""

from __future__ import annotations

SYSTEM = (
    "You are a careful software engineer. You write correct, complete code and "
    "you pay attention to edge cases."
)

GENERATION_TEMPLATE = """{task_prompt}"""

VERIFICATION_BLOCK = """Now verify the solution you just wrote.

Re-read the task requirements and check your solution against each one, \
including the edge cases the task calls out explicitly.

Reply with a JSON object and nothing else:

{"verdict": "correct" | "wrong", "confidence": <integer 0-100>, "revised": <string or null>}

- "verdict" is your judgement about the solution above. Use "correct" if you \
believe it satisfies every requirement, "wrong" otherwise.
- "confidence" is how confident you are in that judgement, from 0 to 100.
- "revised" is the corrected solution when the verdict is "wrong", or null \
when the verdict is "correct"."""


def generation_prompt(task: dict) -> str:
    """The user turn that asks for the solution. Identical in both modes."""
    return GENERATION_TEMPLATE.format(task_prompt=task["prompt"])


def generation_messages(task: dict) -> list[dict]:
    """Messages for the generation call. Identical in both modes."""
    return [{"role": "user", "content": generation_prompt(task)}]


def verification_messages(task: dict, assistant_answer: str) -> list[dict]:
    """Generation messages, the model's answer, then the verification block."""
    return generation_messages(task) + [
        {"role": "assistant", "content": assistant_answer},
        {"role": "user", "content": VERIFICATION_BLOCK},
    ]


def as_assistant_answer(code: str, kind: str) -> str:
    """Format supplied code the way the model formats its own answers.

    The injection arm replaces the model's answer with a known-correct or
    known-buggy one. It must be indistinguishable in FORM from a real answer,
    or the verifier is reacting to presentation rather than to the code — so it
    is fenced exactly as the model's own completions are.
    """
    lang = "sql" if kind == "sql" else "python"
    return f"```{lang}\n{code.strip()}\n```"
