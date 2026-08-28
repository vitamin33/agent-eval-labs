"""The `orderdesk` environment: a deterministic in-memory state machine.

Why a simulator rather than real tools: this experiment needs ground truth at
EVERY step, not only at the outcome. A tool result can only be called
"silently wrong" if the true result is known, and a downstream step can only be
called "contaminated" if the true state is known while it runs. Neither is
computable against a real API.

Every tool is a pure function of state, or an explicit mutation. Nothing reads
a clock, a random source, or the filesystem, so `snapshot()` is a total
description of the environment and two runs from the same fixtures are
identical.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import fixtures


class ToolError(Exception):
    """A genuine, visible failure — the opposite of the silent kind this
    experiment injects. Raised for bad ids and bad arguments so that a real
    error is always distinguishable from a corrupted-but-plausible result."""


@dataclass
class Env:
    orders: dict[str, dict] = field(default_factory=dict)
    customers: dict[str, dict] = field(default_factory=dict)
    shipments: dict[str, dict] = field(default_factory=dict)
    call_log: list[dict] = field(default_factory=list)

    # --- construction ----------------------------------------------------- #

    @classmethod
    def fresh(cls) -> "Env":
        return cls(
            orders={o["id"]: dict(o) for o in fixtures.ORDERS},
            customers={c["id"]: dict(c) for c in fixtures.CUSTOMERS},
            shipments={s["order_id"]: dict(s) for s in fixtures.SHIPMENTS},
        )

    def snapshot(self) -> str:
        """Canonical hash of the full state. Ground truth compares these."""
        blob = json.dumps(
            {
                "orders": self.orders,
                "customers": self.customers,
                "shipments": self.shipments,
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # --- helpers ----------------------------------------------------------- #

    def _region_of(self, order: dict) -> str | None:
        cust = self.customers.get(order["customer_id"])
        return cust["region"] if cust else None

    def _matching(self, status: str | None, region: str | None) -> list[dict]:
        out = []
        for o in self.orders.values():
            if status is not None and o["status"] != status:
                continue
            if region is not None and self._region_of(o) != region:
                continue
            out.append(o)
        return sorted(out, key=lambda o: o["id"])

    # --- tools ------------------------------------------------------------- #
    # Each returns JSON-serialisable data and nothing else.

    def list_orders(self, status: str | None = None, region: str | None = None) -> list[str]:
        self._check_status(status)
        return [o["id"] for o in self._matching(status, region)]

    def count_orders(self, status: str | None = None, region: str | None = None) -> int:
        """Deliberately redundant with `list_orders`.

        The two answer the same question by different routes, so a corrupted
        `list_orders` is *discoverable*. Without redundancy the injected failure
        would be undetectable in principle and the experiment would be scoring
        an impossible task as agent failure.
        """
        self._check_status(status)
        return len(self._matching(status, region))

    def get_order(self, order_id: str) -> dict:
        if order_id not in self.orders:
            raise ToolError(f"no such order: {order_id}")
        return dict(self.orders[order_id])

    def get_customer(self, customer_id: str) -> dict:
        if customer_id not in self.customers:
            raise ToolError(f"no such customer: {customer_id}")
        return dict(self.customers[customer_id])

    def get_shipment(self, order_id: str) -> dict | None:
        return dict(self.shipments[order_id]) if order_id in self.shipments else None

    def sum_totals(self, order_ids: list[str]) -> float:
        if not isinstance(order_ids, list):
            raise ToolError("order_ids must be a list")
        missing = [i for i in order_ids if i not in self.orders]
        if missing:
            raise ToolError(f"no such order(s): {missing}")
        return round(sum(self.orders[i]["total"] for i in order_ids), 2)

    def set_status(self, order_id: str, status: str) -> dict:
        if order_id not in self.orders:
            raise ToolError(f"no such order: {order_id}")
        self._check_status(status, allow_none=False)
        self.orders[order_id]["status"] = status
        return {"ok": True}

    @staticmethod
    def _check_status(status: str | None, allow_none: bool = True) -> None:
        if status is None:
            if allow_none:
                return
            raise ToolError("status is required")
        if status not in fixtures.STATUSES:
            raise ToolError(f"unknown status {status!r}; expected one of {fixtures.STATUSES}")


# The tool surface handed to the agent. `submit` is handled by the loop.
TOOL_NAMES = (
    "list_orders", "count_orders", "get_order", "get_customer",
    "get_shipment", "sum_totals", "set_status", "submit",
)


def call(env: Env, tool: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call against the environment."""
    if tool not in TOOL_NAMES:
        raise ToolError(f"unknown tool: {tool}")
    if tool == "submit":
        raise ToolError("submit is handled by the agent loop, not the environment")
    fn = getattr(env, tool)
    return fn(**args)
