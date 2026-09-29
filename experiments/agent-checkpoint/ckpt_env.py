"""Experiment 3 environment: experiment 2's orderdesk plus `reconcile`.

`Env3` subclasses experiment 2's `Env` so every tool keeps its exact
behaviour; only the fixtures and one new primitive differ.

`reconcile(tool, args)` re-runs a read tool directly against the state and
returns its authoritative result. It is the deterministic checkpoint: in
mode (b) the agent may call it, in mode (c) the harness calls it after every
tool call. It is never injected, because the whole point is that it is the
source of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "agent-verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import env as env_mod  # noqa: E402
import ckpt_fixtures  # noqa: E402

ToolError = env_mod.ToolError

READ_TOOLS = (
    "list_orders", "count_orders", "get_order", "get_customer", "get_shipment", "sum_totals",
)


class Env3(env_mod.Env):
    @classmethod
    def fresh(cls) -> "Env3":
        return cls(
            orders={o["id"]: dict(o) for o in ckpt_fixtures.ORDERS},
            customers={c["id"]: dict(c) for c in ckpt_fixtures.CUSTOMERS},
            shipments={s["order_id"]: dict(s) for s in ckpt_fixtures.SHIPMENTS},
        )

    def reconcile(self, tool: str, args: dict | None = None) -> dict:
        """The authoritative result of a read, recomputed from the state."""
        if tool not in READ_TOOLS:
            raise ToolError(f"reconcile: {tool!r} is not a read tool; expected one of {READ_TOOLS}")
        args = args or {}
        if not isinstance(args, dict):
            raise ToolError("reconcile: args must be an object")
        try:
            value = getattr(self, tool)(**args)
        except TypeError as exc:
            raise ToolError(f"reconcile: bad arguments for {tool}: {exc}") from exc
        return {"tool": tool, "args": args, "source_of_record": value}


# The tool surface. `reconcile` is only exposed to the agent in mode (b); the
# dispatcher accepts it in every mode so the harness can use it in (c).
TOOL_NAMES = env_mod.TOOL_NAMES + ("reconcile",)


def call(env: Env3, tool: str, args: dict[str, Any]) -> Any:
    if tool == "reconcile":
        return env.reconcile(args.get("tool"), args.get("args") or {})
    return env_mod.call(env, tool, args)


def checkpoint(env: Env3, tool: str, args: dict[str, Any]) -> dict | None:
    """The harness-side checkpoint for a call that just executed.

    For a read, the same query reconciled. For a write, the written entity
    read back. `submit` and `reconcile` have no checkpoint. Returns None for a
    call that raised, since there is no result to reconcile against.
    """
    if tool in READ_TOOLS:
        return env.reconcile(tool, args)
    if tool == "set_status":
        return env.reconcile("get_order", {"order_id": args.get("order_id")})
    return None
