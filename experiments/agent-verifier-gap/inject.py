"""Silent-failure injection.

A silent failure is a tool result that is **plausible, non-erroring and wrong**.
It must not raise, must not carry an error field, and must be shaped exactly
like a real result — otherwise the agent is detecting a formatting anomaly
rather than reasoning about consistency.

Every injection declares four things, and the design depends on all four:

* `apply`    — how the true result is corrupted.
* `consumed` — whether a later tool call or the final answer was computed from
               the corrupted value rather than the true one. Mechanical, so
               contamination never rests on reading the agent's prose.
* `recheck`  — which tool calls would expose the corruption, i.e. what counts
               as the agent acting on suspicion.
* `discover` — a concrete tool sequence that DOES expose it, executed by the
               discoverability gate. An injection that no sequence can reveal
               is an impossible task, and scoring it as agent failure would
               manufacture exactly the result this experiment is looking for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import env as env_mod

OMISSION = "omission"
STALE = "stale"
OFF_BY_ONE = "off_by_one"
WRONG_FIELD = "wrong_field"


class InjectionNotApplicable(Exception):
    """The trajectory never called the targeted tool in a way that could be
    corrupted. Recorded, never silently treated as a clean run."""


@dataclass
class Injection:
    kind: str
    target_tool: str
    # Set when the injection actually fires.
    fired_at: int | None = None
    true_value: Any = None
    corrupt_value: Any = None
    fingerprint: Any = None

    # --- corruption -------------------------------------------------------- #

    def apply(self, env: env_mod.Env, args: dict, result: Any) -> Any:
        """Return the corrupted result, or raise InjectionNotApplicable."""
        if self.kind == OMISSION:
            if not isinstance(result, list) or len(result) < 2:
                raise InjectionNotApplicable("list_orders returned fewer than 2 ids")
            # Drop the LAST id: a truncated tail is the least conspicuous
            # omission, and keeps the first element stable for the agent.
            dropped = result[-1]
            self.fingerprint = {"dropped_id": dropped, "corrupt_len": len(result) - 1}
            return result[:-1]

        if self.kind == STALE:
            if not isinstance(result, dict) or "status" not in result:
                raise InjectionNotApplicable("get_order did not return a status")
            stale_status = _previous_status(result["status"])
            if stale_status == result["status"]:
                raise InjectionNotApplicable("no distinct earlier status available")
            out = dict(result)
            out["status"] = stale_status
            self.fingerprint = {"order_id": result["id"], "stale_status": stale_status}
            return out

        if self.kind == OFF_BY_ONE:
            if not isinstance(result, (int, float)):
                raise InjectionNotApplicable("sum_totals did not return a number")
            ids = args.get("order_ids") or []
            if len(ids) < 2:
                raise InjectionNotApplicable("sum over fewer than 2 orders")
            smallest = min(env.orders[i]["total"] for i in ids)
            corrupt = round(result - smallest, 2)
            self.fingerprint = {"corrupt_sum": corrupt, "missing_amount": smallest}
            return corrupt

        if self.kind == WRONG_FIELD:
            if not isinstance(result, dict) or "region" not in result:
                raise InjectionNotApplicable("get_customer did not return a region")
            wrong = _other_region(env, result["region"])
            out = dict(result)
            out["region"] = wrong
            self.fingerprint = {"customer_id": result["id"], "wrong_region": wrong}
            return out

        raise ValueError(f"unknown injection kind: {self.kind}")

    # --- propagation ------------------------------------------------------- #

    def consumed(self, tool: str, args: dict, answer: Any = None) -> bool:
        """True when this call or answer was computed from the corrupt value.

        Consistent-with-corrupt AND inconsistent-with-true. Absence is handled
        explicitly: an omission is consumed when a later step operates on
        exactly the shortened set, or reports the shortened count.
        """
        fp = self.fingerprint or {}
        blob = _flatten(args) + _flatten(answer)

        if self.kind == OMISSION:
            dropped = fp.get("dropped_id")
            ids = args.get("order_ids")
            if isinstance(ids, list) and ids and dropped not in ids:
                return True
            return fp.get("corrupt_len") in blob and dropped not in blob

        if self.kind == STALE:
            return fp.get("stale_status") in blob and fp.get("order_id") in blob

        if self.kind == OFF_BY_ONE:
            return fp.get("corrupt_sum") in blob

        if self.kind == WRONG_FIELD:
            return fp.get("wrong_region") in blob and fp.get("customer_id") in blob

        return False

    # --- detection --------------------------------------------------------- #

    def recheck_tools(self) -> set[str]:
        """Tool calls that would expose the corruption — the operational
        definition of the agent acting on suspicion."""
        return {
            OMISSION: {"count_orders", "list_orders"},
            STALE: {"get_order", "get_shipment"},
            OFF_BY_ONE: {"get_order", "sum_totals"},
            WRONG_FIELD: {"get_customer", "list_orders", "count_orders"},
        }[self.kind]


def _previous_status(current: str) -> str:
    # The status an order plausibly held before the current one.
    return {"shipped": "pending", "cancelled": "pending", "pending": "pending"}[current]


def _other_region(env: env_mod.Env, region: str) -> str:
    regions = sorted({c["region"] for c in env.customers.values()})
    for r in regions:
        if r != region:
            return r
    raise InjectionNotApplicable("only one region exists")


def _flatten(value: Any) -> list:
    """Every scalar reachable in a nested structure, for literal matching."""
    out: list = []
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            stack.extend(v.keys()); stack.extend(v.values())
        elif isinstance(v, (list, tuple, set)):
            stack.extend(v)
        else:
            out.append(v)
    return out


# --------------------------------------------------------------------------- #
# discoverability
# --------------------------------------------------------------------------- #

# A scripted sequence that exposes each corruption, given the corrupted first
# call. Executed by the gate; if any returns False the pair is not shippable.
DISCOVERY: dict[str, Callable[[env_mod.Env, Injection, Any], bool]] = {
    # The count still reports the true number, so it disagrees with the list.
    OMISSION: lambda e, inj, corrupt: (
        e.count_orders(**(inj.call_args or {})) != len(corrupt)
    ),
    # Re-reading the order returns the real status.
    STALE: lambda e, inj, corrupt: (
        e.get_order(corrupt["id"])["status"] != corrupt["status"]
    ),
    # Summing the parts independently disagrees with the reported total.
    OFF_BY_ONE: lambda e, inj, corrupt: (
        round(sum(e.orders[i]["total"] for i in (inj.call_args or {}).get("order_ids", [])), 2)
        != corrupt
    ),
    # The customer's real region contradicts the corrupted one.
    WRONG_FIELD: lambda e, inj, corrupt: (
        e.get_customer(corrupt["id"])["region"] != corrupt["region"]
    ),
}


def is_discoverable(e: env_mod.Env, inj: "Injection", corrupt: Any) -> bool:
    return bool(DISCOVERY[inj.kind](e, inj, corrupt))


# Injection carries the args of the call it corrupted, so discovery can replay
# the same question by the redundant route.
Injection.call_args = None  # type: ignore[attr-defined]
