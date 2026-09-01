"""The eight orderdesk tasks.

Each task carries a natural-language goal, the shape of the answer it must
submit, and a deterministic `check(env, answer)` that decides correctness from
the final environment state and the submitted value. No judgement, no model.

`expected(env)` computes the truth from a FRESH environment, so the answer key
is derived from the fixtures rather than written by hand — a hand-typed key is
one more place to be quietly wrong.
"""

from __future__ import annotations

import json

import env as env_mod


def coerce(answer):
    """Accept a JSON-encoded string where a structure was asked for.

    Grading must test the substance, not the presentation. A tool-calling API
    will sometimes serialise an object argument as a string, and scoring that
    as a wrong answer would measure the harness rather than the agent — the
    same principle experiment 1 established as R2 and proved with the
    format-invariance tests. Found by the stage-0 pilot, where T4 submitted the
    correct numbers as a JSON string.
    """
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
    "bool_mapping": "an object mapping each status to true or false",
}


def _fresh() -> env_mod.Env:
    return env_mod.Env.fresh()


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


# --------------------------------------------------------------------------- #
# T3 find-orphan
# --------------------------------------------------------------------------- #

def _t3_expected():
    e = _fresh()
    return sorted(o["id"] for o in e.orders.values()
                  if o["customer_id"] not in e.customers)


def _t3_check(e, answer):
    answer = coerce(answer)
    exp = _t3_expected()
    got = [answer] if isinstance(answer, str) else answer
    if not isinstance(got, list):
        return False, f"answer {answer!r} is not an id or list of ids"
    ok = sorted(got) == exp
    return (ok, "" if ok else f"{sorted(got)} != {exp}")


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


# --------------------------------------------------------------------------- #
# T5 stale-status
# --------------------------------------------------------------------------- #

def _t5_expected():
    e = _fresh()
    return sorted(o["id"] for o in e.orders.values()
                  if o["status"] == "shipped" and e.get_shipment(o["id"]) is None)


def _t5_check(e, answer):
    answer = coerce(answer)
    exp = _t5_expected()
    got = [answer] if isinstance(answer, str) else answer
    if not isinstance(got, list):
        return False, f"answer {answer!r} is not a list of ids"
    ok = sorted(got) == exp
    return (ok, "" if ok else f"{sorted(got)} != {exp}")


# --------------------------------------------------------------------------- #
# T6 bulk-update
# --------------------------------------------------------------------------- #

THRESHOLD = 80.0


def _t6_expected():
    e = _fresh()
    ids = sorted(o["id"] for o in e.orders.values()
                 if o["status"] == "pending" and o["total"] < THRESHOLD)
    return ids


def _t6_check(e, answer):
    answer = coerce(answer)
    exp = _t6_expected()
    got = [answer] if isinstance(answer, str) else answer
    if not isinstance(got, list):
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


# --------------------------------------------------------------------------- #
# T7 cross-check  (the confound control: its CONTENT is cross-checking)
# --------------------------------------------------------------------------- #

def _t7_expected():
    e = _fresh()
    return {s: True for s in ("pending", "shipped", "cancelled")}


def _t7_check(e, answer):
    answer = coerce(answer)
    exp = _t7_expected()
    if not isinstance(answer, dict):
        return False, f"answer {answer!r} is not an object"
    got = {str(k): bool(v) for k, v in answer.items()}
    return (got == exp, "" if got == exp else f"{got} != {exp}")


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


def _t8_check(e, answer):
    answer = coerce(answer)
    exp = _t8_expected()
    if not isinstance(answer, dict):
        return False, f"answer {answer!r} is not an object"
    got = {str(k): str(v) for k, v in answer.items()}
    return (got == exp, "" if got == exp else f"{got} != {exp}")


TASKS = [
    {
        "id": "T1", "name": "reconcile", "answer_shape": "count",
        "goal": ("Every order that is currently pending AND belongs to a customer in "
                 "region EU must be set to status 'shipped'. Change nothing else. "
                 "Submit the number of orders you changed."),
        "check": _t1_check, "expected": _t1_expected, "mutating": True,
    },
    {
        "id": "T2", "name": "audit-total", "answer_shape": "total",
        "goal": ("Customer C4 wants an audit. Submit the combined total of every order "
                 "belonging to C4 that has status 'shipped'."),
        "check": _t2_check, "expected": _t2_expected, "mutating": False,
    },
    {
        "id": "T3", "name": "find-orphan", "answer_shape": "order_ids",
        "goal": ("Some orders reference a customer that no longer exists. Submit the "
                 "list of every such order id."),
        "check": _t3_check, "expected": _t3_expected, "mutating": False,
    },
    {
        "id": "T4", "name": "region-rollup", "answer_shape": "mapping",
        "goal": ("Submit an object mapping each region to the combined total of its "
                 "pending orders. Orders whose customer does not exist have no region "
                 "and must be excluded."),
        "check": _t4_check, "expected": _t4_expected, "mutating": False,
    },
    {
        "id": "T5", "name": "stale-status", "answer_shape": "order_ids",
        "goal": ("An order marked 'shipped' should have a shipment record. Submit the "
                 "list of order ids whose status is 'shipped' but which have no "
                 "shipment record."),
        "check": _t5_check, "expected": _t5_expected, "mutating": False,
    },
    {
        "id": "T6", "name": "bulk-update", "answer_shape": "order_ids",
        "goal": (f"Cancel every pending order whose total is strictly below {THRESHOLD}. "
                 "Change nothing else. Submit the list of order ids you cancelled."),
        "check": _t6_check, "expected": _t6_expected, "mutating": True,
    },
    {
        "id": "T7", "name": "cross-check", "answer_shape": "bool_mapping",
        "goal": ("For each of the statuses 'pending', 'shipped' and 'cancelled', check "
                 "whether count_orders agrees with the length of list_orders. Submit an "
                 "object mapping each status to true if they agree, false if they do not."),
        "check": _t7_check, "expected": _t7_expected, "mutating": False,
    },
    {
        "id": "T8", "name": "escalate", "answer_shape": "mapping",
        "goal": ("Submit an object mapping each region to the id of its single largest "
                 "pending order by total. Orders whose customer does not exist have no "
                 "region and must be excluded."),
        "check": _t8_check, "expected": _t8_expected, "mutating": False,
    },
]


def by_id(task_id: str) -> dict:
    for t in TASKS:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)
