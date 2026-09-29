"""Prompts and tool surfaces for the four modes.

The declared differences, and nothing else:

* `inject_tool`     = `inject` + one tool definition (`reconcile`)
* `inject_enforced` = `inject` + one system-prompt block (CHECKPOINT_BLOCK)

A test reconstructs each from `inject` and asserts the residue is exactly
that. The base system prompt and the base tool list are imported from
experiment 2, not copied, so they cannot drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "agent-verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import agent as agent2  # noqa: E402
import ckpt_env  # noqa: E402
import prompts_agent  # noqa: E402
from ckpt_tasks import ANSWER_SHAPES  # noqa: E402

BASE_SYSTEM = prompts_agent.BASE_SYSTEM

CHECKPOINT_BLOCK = (
    "\n\nEvery tool result is delivered as "
    "{\"result\": ..., \"checkpoint\": {\"source_of_record\": ...}}. The checkpoint "
    "is the same query recomputed directly from the system of record, independently "
    "of the tool. If `result` and `checkpoint` disagree, the checkpoint is correct: "
    "use it, and treat the tool result as unreliable."
)

RECONCILE_TOOL = {
    "type": "function",
    "function": {
        "name": "reconcile",
        "description": (
            "Re-run a read tool directly against the system of record and return its "
            "authoritative result, independently of the tool's own answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "enum": list(ckpt_env.READ_TOOLS)},
                "args": {"type": "object",
                         "description": "The arguments you would pass to that tool."},
            },
            "required": ["tool", "args"],
        },
    },
}


def system_prompt(mode: str) -> str:
    if mode == "inject_enforced":
        return BASE_SYSTEM + CHECKPOINT_BLOCK
    return BASE_SYSTEM


def tool_schemas(mode: str) -> list[dict]:
    """Order is fixed per mode so the prompt prefix stays cacheable."""
    base = agent2.tool_schemas()
    if mode != "inject_tool":
        return base
    # Before `submit`, so the finishing tool stays last in every mode.
    return base[:-1] + [RECONCILE_TOOL] + base[-1:]


def task_prompt(task: dict) -> str:
    return f"{task['goal']}\n\nSubmit `answer` as {ANSWER_SHAPES[task['answer_shape']]}."
