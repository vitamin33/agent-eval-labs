"""The eight orderdesk tasks over experiment 3's fixtures, plus the naive
solver for each that the answer-relevance gate runs.

Wording and checks are experiment 2's. `expected()` is computed from a fresh
environment, never typed by hand. Each task names one primary injection kind;
`relevance.py` proves, for every pair, that the injection both fires on the
task's obvious path and changes the correct answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "agent-verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ckpt_env  # noqa: E402
import inject  # noqa: E402

Call = Callable[[str, dict], Any]


def coerce(answer):
    """Accept a JSON-encoded string where a structure was asked for (experiment
    2's rule R2: grading tests the substance, not the presentation)."""
    if isinstance(answer, str):
        try:
            return json.loads(answer)
        except ValueError:
            return answer
    return answer


ANSWER_SHAPES = {
    "count": "an integer",
    "total": "a number rounded to 2 decimals",
    "order_id": "a single order id string, e.g. \"O07\"",
    "order_ids": "a list of order id strings, sorted",
    "mapping": "an object mapping string keys to numbers",
    # Experiment 2 gave T8 the `mapping` shape, whose wording says "numbers";
    # the agent obeyed and submitted "1" for "O01". Found at stage 1
    # (CALIBRATION.md), fixed as Amendment A2 before stage 2.
    "id_mapping": "an object mapping each region to one order id string, e.g. {\"EU\": \"O07\"}",
    "bool_mapping": "an object mapping each status to true or false",
}

THRESHOLD = 80.0


def _fresh() -> ckpt_env.Env3:
    return ckpt_env.Env3.fresh()


def _ids(answer) -> list | None:
    answer = coerce(answer)
    got = [answer] if isinstance(answer, str) else answer
    return got if isinstance(got, list) else None


# --------------------------------------------------------------------------- #
# T1 reconcile
# --------------------------------------------------------------------------- #

def _t1_expected():
    e = _fresh()
    ids = e.list_orders("pending", "EU")
    return {"answer": len(ids), "mutated": ids}


def _t1_check(e, answer):
    answer = coerce(answer)
    exp = _t1_expected()
    if answer != exp["answer"]:
        return False, f"count {answer!r} != {exp['answer']}"
    for oid in exp["mutated"]:
        if e.orders[oid]["status"] != "shipped":
            return False, f"{oid} was not set to shipped"
    untouched = _fresh()
    for oid, o in e.orders.items():
        if oid not in exp["mutated"] and o["status"] != untouched.orders[oid]["status"]:
            return False, f"{oid} was changed but should not have been"
    return True, ""


def _t1_naive(call: Call):
    ids = call("list_orders", {"status": "pending", "region": "EU"})
    for oid in ids:
        call("set_status", {"order_id": oid, "status": "shipped"})
    return len(ids)


# --------------------------------------------------------------------------- #
# T2 audit-total
# --------------------------------------------------------------------------- #

def _t2_expected():
    e = _fresh()
    ids = [o["id"] for o in e.orders.values()
           if o["status"] == "shipped" and o["customer_id"] == "C4"]
    return round(sum(e.orders[i]["total"] for i in ids), 2)


def _t2_check(e, answer):
    answer = coerce(answer)
    exp = _t2_expected()
    try:
        got = round(float(answer), 2)
    except (TypeError, ValueError):
        return False, f"answer {answer!r} is not a number"
    return (got == exp, "" if got == exp else f"total {got} != {exp}")


def _t2_naive(call: Call):
    shipped = call("list_orders", {"status": "shipped"})
    mine = [oid for oid in shipped
            if call("get_order", {"order_id": oid})["customer_id"] == "C4"]
    return call("sum_totals", {"order_ids": mine})


# --------------------------------------------------------------------------- #
# T3 find-orphan
# --------------------------------------------------------------------------- #

def _t3_expected():
    e = _fresh()
    return sorted(o["id"] for o in e.orders.values()
                  if o["customer_id"] not in e.customers)


def _t3_check(e, answer):
    exp = _t3_expected()
    got = _ids(answer)
    if got is None:
        return False, f"answer {answer!r} is not an id or list of ids"
    ok = sorted(got) == exp
    return (ok, "" if ok else f"{sorted(got)} != {exp}")


def _t3_naive(call: Call):
    orphans = []
    for oid in call("list_orders", {}):
        cid = call("get_order", {"order_id": oid})["customer_id"]
        try:
            call("get_customer", {"customer_id": cid})
        except ckpt_env.ToolError:
            orphans.append(oid)
    return sorted(orphans)


# --------------------------------------------------------------------------- #
# T4 region-rollup
# --------------------------------------------------------------------------- #

def _t4_expected():
    e = _fresh()
    out: dict[str, float] = {}
    for o in e.orders.values():
        if o["status"] != "pending":
            continue
        region = e._region_of(o)
        if region is None:
            continue
        out[region] = round(out.get(region, 0.0) + o["total"], 2)
    return out


def _t4_check(e, answer):
    answer = coerce(answer)
    exp = _t4_expected()
    if not isinstance(answer, dict):
        return False, f"answer {answer!r} is not an object"
    got = {}
    for k, v in answer.items():
        try:
            got[str(k)] = round(float(v), 2)
        except (TypeError, ValueError):
            return False, f"value for {k!r} is not a number"
    return (got == exp, "" if got == exp else f"{got} != {exp}")


def _region_of_via(call: Call, cid: str, cache: dict) -> str | None:
    if cid not in cache:
        try:
            cache[cid] = call("get_customer", {"customer_id": cid})["region"]
        except ckpt_env.ToolError:
            cache[cid] = None
    return cache[cid]


def _t4_naive(call: Call):
    out: dict[str, float] = {}
    regions: dict = {}
    for oid in call("list_orders", {"status": "pending"}):
        o = call("get_order", {"order_id": oid})
        region = _region_of_via(call, o["customer_id"], regions)
        if region is None:
            continue
        out[region] = round(out.get(region, 0.0) + o["total"], 2)
    return out


# --------------------------------------------------------------------------- #
# T5 stale-status
# --------------------------------------------------------------------------- #

def _t5_expected():
    e = _fresh()
    return sorted(o["id"] for o in e.orders.values()
                  if o["status"] == "shipped" and e.get_shipment(o["id"]) is None)


def _t5_check(e, answer):
    exp = _t5_expected()
    got = _ids(answer)
    if got is None:
        return False, f"answer {answer!r} is not a list of ids"
    ok = sorted(got) == exp
    return (ok, "" if ok else f"{sorted(got)} != {exp}")


def _t5_naive(call: Call):
    return sorted(oid for oid in call("list_orders", {"status": "shipped"})
                  if call("get_shipment", {"order_id": oid}) is None)


# --------------------------------------------------------------------------- #
# T6 bulk-update
# --------------------------------------------------------------------------- #

def _t6_expected():
    e = _fresh()
    return sorted(o["id"] for o in e.orders.values()
                  if o["status"] == "pending" and o["total"] < THRESHOLD)


def _t6_check(e, answer):
    exp = _t6_expected()
    got = _ids(answer)
    if got is None:
        return False, f"answer {answer!r} is not a list of ids"
    if sorted(got) != exp:
        return False, f"reported {sorted(got)} != {exp}"
    for oid in exp:
        if e.orders[oid]["status"] != "cancelled":
            return False, f"{oid} was not cancelled"
    untouched = _fresh()
    for oid, o in e.orders.items():
        if oid not in exp and o["status"] != untouched.orders[oid]["status"]:
            return False, f"{oid} was changed but should not have been"
    return True, ""


def _t6_naive(call: Call):
    cancelled = []
    for oid in call("list_orders", {"status": "pending"}):
        if call("get_order", {"order_id": oid})["total"] < THRESHOLD:
            call("set_status", {"order_id": oid, "status": "cancelled"})
            cancelled.append(oid)
    return sorted(cancelled)


# --------------------------------------------------------------------------- #
# T7 cross-check  (the confound control: its CONTENT is cross-checking)
# --------------------------------------------------------------------------- #

def _t7_expected():
    return {s: True for s in ("pending", "shipped", "cancelled")}


def _t7_check(e, answer):
    answer = coerce(answer)
    exp = _t7_expected()
    if not isinstance(answer, dict):
        return False, f"answer {answer!r} is not an object"
    got = {str(k): bool(v) for k, v in answer.items()}
    return (got == exp, "" if got == exp else f"{got} != {exp}")


def _t7_naive(call: Call):
    return {s: call("count_orders", {"status": s}) == len(call("list_orders", {"status": s}))
            for s in ("pending", "shipped", "cancelled")}


# --------------------------------------------------------------------------- #
# T8 escalate
# --------------------------------------------------------------------------- #

def _t8_expected():
    e = _fresh()
    best: dict[str, tuple[str, float]] = {}
    for o in sorted(e.orders.values(), key=lambda x: x["id"]):
        if o["status"] != "pending":
            continue
        region = e._region_of(o)
        if region is None:
            continue
        if region not in best or o["total"] > best[region][1]:
            best[region] = (o["id"], o["total"])
    return {r: oid for r, (oid, _) in best.items()}


def _order_id(value) -> str:
    """Normalise a bare order number to its id: 1, "1", "01" -> "O01".

    Grading tests the substance, not the presentation (experiment 2's R2). A
    bare number is unambiguous here because ids are O01..O15, and a wrong
    number stays wrong after normalisation."""
    text = str(value).strip()
    if text.isdigit():
        return f"O{int(text):02d}"
    return text


def _t8_check(e, answer):
    answer = coerce(answer)
    exp = _t8_expected()
    if not isinstance(answer, dict):
        return False, f"answer {answer!r} is not an object"
    got = {str(k): _order_id(v) for k, v in answer.items()}
    return (got == exp, "" if got == exp else f"{got} != {exp}")


def _t8_naive(call: Call):
    best: dict[str, tuple[str, float]] = {}
    regions: dict = {}
    for oid in call("list_orders", {"status": "pending"}):
        o = call("get_order", {"order_id": oid})
        region = _region_of_via(call, o["customer_id"], regions)
        if region is None:
            continue
        if region not in best or o["total"] > best[region][1]:
            best[region] = (oid, o["total"])
    return {r: oid for r, (oid, _) in best.items()}


TASKS = [
    {
        "id": "T1", "name": "reconcile", "answer_shape": "count",
        "goal": ("Every order that is currently pending AND belongs to a customer in "
                 "region EU must be set to status 'shipped'. Change nothing else. "
                 "Submit the number of orders you changed."),
        "check": _t1_check, "expected": _t1_expected, "naive": _t1_naive,
        "mutating": True, "kind": inject.OMISSION,
    },
    {
        "id": "T2", "name": "audit-total", "answer_shape": "total",
        "goal": ("Customer C4 wants an audit. Submit the combined total of every order "
                 "belonging to C4 that has status 'shipped'."),
        "check": _t2_check, "expected": _t2_expected, "naive": _t2_naive,
        "mutating": False, "kind": inject.OFF_BY_ONE,
    },
    {
        "id": "T3", "name": "find-orphan", "answer_shape": "order_ids",
        "goal": ("Some orders reference a customer that no longer exists. Submit the "
                 "list of every such order id."),
        "check": _t3_check, "expected": _t3_expected, "naive": _t3_naive,
        "mutating": False, "kind": inject.OMISSION,
    },
    {
        "id": "T4", "name": "region-rollup", "answer_shape": "mapping",
        "goal": ("Submit an object mapping each region to the combined total of its "
                 "pending orders. Orders whose customer does not exist have no region "
                 "and must be excluded."),
        "check": _t4_check, "expected": _t4_expected, "naive": _t4_naive,
        "mutating": False, "kind": inject.WRONG_FIELD,
    },
    {
        "id": "T5", "name": "stale-status", "answer_shape": "order_ids",
        "goal": ("An order marked 'shipped' should have a shipment record. Submit the "
                 "list of order ids whose status is 'shipped' but which have no "
                 "shipment record."),
        "check": _t5_check, "expected": _t5_expected, "naive": _t5_naive,
        "mutating": False, "kind": inject.OMISSION,
    },
    {
        "id": "T6", "name": "bulk-update", "answer_shape": "order_ids",
        "goal": (f"Cancel every pending order whose total is strictly below {THRESHOLD}. "
                 "Change nothing else. Submit the list of order ids you cancelled."),
        "check": _t6_check, "expected": _t6_expected, "naive": _t6_naive,
        "mutating": True, "kind": inject.OMISSION,
    },
    {
        "id": "T7", "name": "cross-check", "answer_shape": "bool_mapping",
        "goal": ("For each of the statuses 'pending', 'shipped' and 'cancelled', check "
                 "whether count_orders agrees with the length of list_orders. Submit an "
                 "object mapping each status to true if they agree, false if they do not."),
        "check": _t7_check, "expected": _t7_expected, "naive": _t7_naive,
        "mutating": False, "kind": inject.OMISSION,
    },
    {
        "id": "T8", "name": "escalate", "answer_shape": "id_mapping",
        "goal": ("Submit an object mapping each region to the id of its single largest "
                 "pending order by total. Orders whose customer does not exist have no "
                 "region and must be excluded."),
        "check": _t8_check, "expected": _t8_expected, "naive": _t8_naive,
        "mutating": False, "kind": inject.WRONG_FIELD,
    },
]

# T7's content IS cross-checking; excluded from headline detection.
CONFOUND_CONTROL = "T7"

PRIMARY_KIND = {t["id"]: t["kind"] for t in TASKS}


def by_id(task_id: str) -> dict:
    for t in TASKS:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)
