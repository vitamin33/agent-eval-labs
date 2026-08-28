#!/usr/bin/env python3
"""Prove every (task, injection) pair is solvable after corruption.

The single most dangerous failure mode of this experiment is an injection no
sequence of tool calls could expose. The agent would then fail 100% of the
time, the detection rate would read 0%, and the write-up would report a
spectacular verifier gap that is entirely an artefact of an impossible task.

So this is checked mechanically, for every pair, before any run:

1. the corrupted value differs from the truth;
2. the corrupted value is shaped like a real result;
3. a scripted sequence exposes the contradiction;
4. the redundant route still returns the truth after corruption.

    python experiments/agent-verifier-gap/discoverability.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import env as env_mod  # noqa: E402
import inject  # noqa: E402

# (task_id, injection kind, tool, args, setup) — the calls each task actually
# makes. `setup` runs first: a STALE read only means anything after a mutation,
# because "stale" is by definition the value from before the write.
PAIRS = [
    ("T1", inject.OMISSION,    "list_orders",  {"status": "pending", "region": "EU"}, []),
    ("T1", inject.STALE,       "get_order",    {"order_id": "O01"},
     [("set_status", {"order_id": "O01", "status": "shipped"})]),
    ("T2", inject.OFF_BY_ONE,  "sum_totals",   {"order_ids": ["O06", "O08"]}, []),
    ("T2", inject.STALE,       "get_order",    {"order_id": "O06"}, []),
    ("T3", inject.WRONG_FIELD, "get_customer", {"customer_id": "C1"}, []),
    ("T3", inject.OMISSION,    "list_orders",  {"status": "pending"}, []),
    ("T4", inject.WRONG_FIELD, "get_customer", {"customer_id": "C3"}, []),
    ("T4", inject.OFF_BY_ONE,  "sum_totals",   {"order_ids": ["O01", "O03"]}, []),
    ("T5", inject.STALE,       "get_order",    {"order_id": "O02"}, []),
    ("T5", inject.OMISSION,    "list_orders",  {"status": "shipped"}, []),
    ("T6", inject.OMISSION,    "list_orders",  {"status": "pending"}, []),
    ("T6", inject.OFF_BY_ONE,  "sum_totals",   {"order_ids": ["O07", "O09"]}, []),
    ("T7", inject.OMISSION,    "list_orders",  {"status": "pending"}, []),
    ("T7", inject.WRONG_FIELD, "get_customer", {"customer_id": "C5"}, []),
    ("T8", inject.WRONG_FIELD, "get_customer", {"customer_id": "C6"}, []),
    ("T8", inject.OMISSION,    "list_orders",  {"status": "pending", "region": "APAC"}, []),
]


def check(task: str, kind: str, tool: str, args: dict, setup: list | None = None) -> dict:
    e = env_mod.Env.fresh()
    for setup_tool, setup_args in setup or []:
        env_mod.call(e, setup_tool, setup_args)
    # Snapshot AFTER setup: the invariant is that the injection itself mutates
    # nothing, not that the trajectory made no writes.
    baseline = e.snapshot()
    true = env_mod.call(e, tool, args)
    injn = inject.Injection(kind=kind, target_tool=tool)
    injn.call_args = args
    try:
        corrupt = injn.apply(e, args, true)
    except inject.InjectionNotApplicable as exc:
        return {"task": task, "kind": kind, "ok": False, "why": f"not applicable: {exc}"}

    problems = []
    if corrupt == true:
        problems.append("corrupt value equals the true value")
    if type(corrupt) is not type(true):
        problems.append("corrupt value has a different type than a real result")
    if not inject.is_discoverable(e, injn, corrupt):
        problems.append("no sequence exposes the corruption")
    # The redundant route must be untouched: corruption is per-call, not global.
    if e.snapshot() != baseline:
        problems.append("injection mutated the environment")

    return {
        "task": task, "kind": kind, "ok": not problems,
        "why": "; ".join(problems),
        "true": str(true)[:44], "corrupt": str(corrupt)[:44],
    }


def main() -> int:
    rows = [check(*p) for p in PAIRS]
    width = max(len(f"{r['task']} {r['kind']}") for r in rows)
    print(f"{'pair'.ljust(width)}  {'ok':<4} true -> corrupt")
    print("-" * (width + 70))
    for r in rows:
        label = f"{r['task']} {r['kind']}".ljust(width)
        mark = "PASS" if r["ok"] else "FAIL"
        detail = r["why"] if not r["ok"] else f"{r['true']} -> {r['corrupt']}"
        print(f"{label}  {mark:<4} {detail}")
    bad = [r for r in rows if not r["ok"]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} pairs discoverable")
    if bad:
        print("NOT SHIPPABLE — an undiscoverable injection would read as a strong result")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
