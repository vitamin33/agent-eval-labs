#!/usr/bin/env python3
"""Prove every (task, injection) pair is answer-relevant and discoverable.

Experiment 2's discoverability check ran on a hand-written call the task never
made, and two of its injections fired in every run without touching the
answer. The failure mode is the same as an undiscoverable injection, in the
other direction: an injection that changes nothing measures nothing, and its
trajectories are counted as if the agent had survived a silent failure.

So, for every pair, with no model involved:

1. the task's naive solver, run clean, produces the correct answer
   (this validates the solver);
2. with the injection applied at the first eligible call, the corrupt value
   differs from the truth, keeps its shape, is exposed by a scripted
   sequence, and leaves the environment unchanged;
3. the naive solver's answer is now WRONG.

    python experiments/agent-checkpoint/relevance.py

`fires_on(steps, kind)` replays a recorded trajectory's tool calls against an
injection kind; gate G9 uses it on stage-0 records to confirm the injection
would fire on the path the real agent actually takes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "agent-verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ckpt_env  # noqa: E402
import ckpt_tasks  # noqa: E402
import inject  # noqa: E402


def check_pair(task: dict) -> dict:
    kind = task["kind"]
    out: dict[str, Any] = {"task": task["id"], "kind": kind, "problems": []}

    # 1. the solver is right when nothing interferes
    e = ckpt_env.Env3.fresh()
    answer = task["naive"](lambda t, a: ckpt_env.call(e, t, a))
    ok, why = task["check"](e, answer)
    out["clean_ok"] = ok
    if not ok:
        out["problems"].append(f"naive solver is wrong clean: {why}")

    # 2. inject at the first eligible call, checking fidelity as we go
    e2 = ckpt_env.Env3.fresh()
    inj = inject.Injection(kind=kind, target_tool=inject.TARGET_TOOL[kind])
    state = {"n": 0, "fired": False, "na": None}

    def call(tool: str, args: dict):
        result = ckpt_env.call(e2, tool, args)
        if tool == inj.target_tool and not state["fired"] and state["na"] is None:
            baseline = e2.snapshot()
            inj.call_args = args
            try:
                corrupt = inj.apply(e2, args, result)
            except inject.InjectionNotApplicable as exc:
                state["na"] = str(exc)
                return result
            state["fired"] = True
            inj.fired_at = state["n"]
            out["true"] = str(result)[:44]
            out["corrupt"] = str(corrupt)[:44]
            if corrupt == result:
                out["problems"].append("corrupt value equals the true value")
            if type(corrupt) is not type(result):
                out["problems"].append("corrupt value has a different type than a real result")
            if not inject.is_discoverable(e2, inj, corrupt):
                out["problems"].append("no sequence exposes the corruption")
            if e2.snapshot() != baseline:
                out["problems"].append("injection mutated the environment")
            result = corrupt
        state["n"] += 1
        return result

    answer2 = task["naive"](call)
    out["fired"] = state["fired"]
    if not state["fired"]:
        out["problems"].append(
            f"injection never fired on the naive path"
            + (f": {state['na']}" if state["na"] else ""))
    ok2, _ = task["check"](e2, answer2)
    out["injected_wrong"] = not ok2
    if ok2:
        out["problems"].append("the answer is still correct after the injection")
    out["ok"] = not out["problems"]
    return out


def fires_on(steps: list[dict], kind: str) -> bool:
    """Would this injection fire on a recorded (clean) trajectory?

    Replays the first call to the targeted tool with its recorded arguments
    and true result. Injection applicability depends only on that call and on
    static fixture data, so no earlier state has to be reconstructed.
    """
    target = inject.TARGET_TOOL[kind]
    for s in steps:
        if s.get("tool") != target:
            continue
        e = ckpt_env.Env3.fresh()
        inj = inject.Injection(kind=kind, target_tool=target)
        inj.call_args = s.get("args") or {}
        result = s.get("result")
        if isinstance(result, dict) and "result" in result and "checkpoint" in result:
            result = result["result"]
        try:
            inj.apply(e, inj.call_args, result)
        except (inject.InjectionNotApplicable, KeyError, TypeError):
            return False
        return True
    return False


def main() -> int:
    rows = [check_pair(t) for t in ckpt_tasks.TASKS]
    width = max(len(f"{r['task']} {r['kind']}") for r in rows)
    print(f"{'pair'.ljust(width)}  {'ok':<4} true -> corrupt")
    print("-" * (width + 70))
    for r in rows:
        label = f"{r['task']} {r['kind']}".ljust(width)
        mark = "PASS" if r["ok"] else "FAIL"
        detail = ("; ".join(r["problems"]) if not r["ok"]
                  else f"{r.get('true')} -> {r.get('corrupt')}")
        print(f"{label}  {mark:<4} {detail}")
    bad = [r for r in rows if not r["ok"]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} pairs answer-relevant and discoverable")
    if bad:
        print("NOT SHIPPABLE — an injection that fires and changes nothing measures nothing")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
