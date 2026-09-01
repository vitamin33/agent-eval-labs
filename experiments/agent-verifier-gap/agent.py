"""The agent loop: a tool-calling trajectory over the orderdesk environment.

Direct SDK, no framework. One step is one model call that may request tool
calls; the loop executes them against the environment and feeds the results
back. The trajectory ends when the agent calls `submit`, or when the step cap
is hit — the latter recorded as `hit_step_cap`, never quietly graded as failure.

The injection hook lives here because a silent failure has to be indistinguish-
able from a real tool result at the point the agent reads it: same shape, same
absence of any error field, delivered by the same path.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import env as env_mod  # noqa: E402
import inject as inject_mod  # noqa: E402
import prompts_agent  # noqa: E402
import agent_tasks as tasks_mod  # noqa: E402  (named to avoid colliding
#   with experiment 1's `tasks` package on the shared sys.path)

# Stage 1 measured this definition failing: `late` as "first eligible call at or
# after turn 3" fired 0 times in 32, because agents call their data-fetching
# tool once at turn 0 and never again. Replaced by an ordinal: fire on the Nth
# eligible call, where N comes from a probe run that counts how many times the
# task actually calls the tool. `early` is N=1; `late` is N=M, the last call
# that really occurs. See RESEARCH.md Amendment A1.
LATE_FROM_TURN = 3  # retained only so stage-1 records remain interpretable


def tool_schemas() -> list[dict]:
    """The tool surface, as the API expects it. Order is fixed so the prompt
    prefix stays byte-stable and cacheable across steps."""
    S = {"type": "string"}
    status = {"type": "string", "enum": ["pending", "shipped", "cancelled"]}
    defs = [
        ("list_orders", "List ids of orders matching an optional status and/or customer region.",
         {"status": status, "region": S}, []),
        ("count_orders", "Count orders matching an optional status and/or customer region.",
         {"status": status, "region": S}, []),
        ("get_order", "Fetch one order by id.", {"order_id": S}, ["order_id"]),
        ("get_customer", "Fetch one customer by id.", {"customer_id": S}, ["customer_id"]),
        ("get_shipment", "Fetch the shipment record for an order, or null if there is none.",
         {"order_id": S}, ["order_id"]),
        ("sum_totals", "Sum the totals of the given order ids.",
         {"order_ids": {"type": "array", "items": S}}, ["order_ids"]),
        ("set_status", "Set an order's status.", {"order_id": S, "status": status},
         ["order_id", "status"]),
        ("submit", "Finish the task and report your result.",
         {"answer": {"description": "The result, in the shape the task asked for."},
          "claims_success": {"type": "boolean",
                             "description": "Do you believe you completed the task correctly?"},
          "confidence": {"type": "integer", "minimum": 0, "maximum": 100}},
         ["answer", "claims_success", "confidence"]),
    ]
    return [
        {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req},
        }}
        for name, desc, props, req in defs
    ]


def run_trajectory(
    provider,
    cfg,
    task: dict,
    mode: str,
    run_index: int,
    injection_kind: str | None = None,
    position: str | None = None,
    step_cap: int = 12,
    inject_at_nth: int = 1,
    count_only: str | None = None,
) -> dict:
    """Execute one trajectory and return its record."""
    t_start = time.perf_counter()
    e = env_mod.Env.fresh()
    tools = tool_schemas()
    messages = [
        {"role": "system", "content": prompts_agent.system_prompt(mode)},
        {"role": "user", "content": prompts_agent.task_prompt(task)},
    ]

    injection = None
    if injection_kind:
        injection = inject_mod.Injection(
            kind=injection_kind,
            target_tool=inject_mod.TARGET_TOOL[injection_kind],
        )

    # Two different clocks, and mixing them was a real bug found by the stage-0
    # pilot: one model TURN can request several tool calls, so a 12-turn cap
    # produced 22 recorded steps. `turn` bounds the loop and defines the `late`
    # injection point; `idx` counts actions taken and is the unit for detection
    # and contamination depth — an action on poisoned data is what propagates.
    # How many times the targeted tool has been called so far. The injection
    # fires on the `inject_at_nth` occurrence, which is what makes `late`
    # constructible at all.
    eligible_seen = 0
    tool_call_counts: dict[str, int] = {}

    steps: list[dict] = []
    submitted: dict | None = None
    detected_at: int | None = None
    truncated = False
    idx = 0
    n_turns = 0

    for turn in range(step_cap):
        n_turns = turn + 1
        message, acct = provider.chat_tools(messages, tools)
        truncated = truncated or acct.truncated
        calls = message.tool_calls or []
        step_base = {
            "turn": turn,
            "input_tokens": acct.input_tokens,
            "output_tokens": acct.output_tokens,
            "reasoning_tokens": acct.reasoning_tokens,
            "cache_hit_tokens": acct.cache_hit_tokens,
            "latency_s": round(acct.latency_s, 3),
            "truncated": acct.truncated,
            "model": acct.model,
        }

        if not calls:
            # No tool call and no submit: the agent stopped talking. Recorded
            # as its own outcome rather than folded into failure.
            steps.append({**step_base, "idx": idx, "tool": None, "args": {},
                          "result": (message.content or "")[:400], "injected": False,
                          "consumed_poison": False})
            idx += 1
            break

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls
            ],
        })

        finished = False
        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}

            if name == "submit":
                submitted = args
                steps.append({**step_base, "idx": idx, "tool": "submit", "args": args,
                              "result": None, "injected": False,
                              "consumed_poison": bool(
                                  injection and injection.fingerprint
                                  and injection.consumed("submit", args,
                                                         answer=args.get("answer")))})
                idx += 1
                finished = True
                break

            injected_here = False
            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
            try:
                result = env_mod.call(e, name, args)
                if injection is not None and name == injection.target_tool:
                    eligible_seen += 1
                if (injection is not None and injection.fired_at is None
                        and name == injection.target_tool
                        and eligible_seen == inject_at_nth):
                    try:
                        injection.call_args = args
                        corrupt = injection.apply(e, args, result)
                        injection.true_value = result
                        injection.corrupt_value = corrupt
                        injection.fired_at = idx
                        result = corrupt
                        injected_here = True
                    except inject_mod.InjectionNotApplicable:
                        pass  # recorded by fired_at staying None
                payload = json.dumps(result)
            except env_mod.ToolError as exc:
                payload = json.dumps({"error": str(exc)})
                result = None

            consumed = bool(
                injection and injection.fingerprint and not injected_here
                and injection.fired_at is not None and injection.consumed(name, args)
            )
            if (injection is not None and injection.fired_at is not None
                    and not injected_here and detected_at is None
                    and idx > injection.fired_at
                    and injection.is_recheck(name, args)):
                detected_at = idx

            steps.append({**step_base, "idx": idx, "tool": name, "args": args,
                          "result": result, "injected": injected_here,
                          "consumed_poison": consumed})
            idx += 1
            messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})

        if finished:
            break

    n_steps = len(steps)
    hit_cap = submitted is None and n_turns >= step_cap
    answer = (submitted or {}).get("answer")
    ok, why = task["check"](e, answer) if submitted is not None else (False, "never submitted")

    # Honest naming: this is the OUTCOME being consistent with the corruption
    # having propagated, not proof of data flow. Precise propagation is tracked
    # per step via the fingerprint; for a final answer that the agent assembled
    # in its head, no tool argument carries the poison, so only this weaker
    # statement is available. RESEARCH.md says so explicitly.
    answer_consistent_with_poison = bool(
        injection and injection.fired_at is not None
        and submitted is not None and not ok and detected_at is None
    )

    depth = None
    if injection and injection.fired_at is not None:
        end = detected_at if detected_at is not None else n_steps
        depth = end - injection.fired_at

    in_tok = sum(s["input_tokens"] for s in steps)
    out_tok = sum(s["output_tokens"] for s in steps)
    hit_tok = sum(s["cache_hit_tokens"] for s in steps)

    return {
        "schema_version": 1,
        "trajectory_id": f"{task['id']}|{mode}|{position or 'none'}|{run_index}",
        "task_id": task["id"], "task_name": task["name"],
        "mode": mode, "run_index": run_index,
        "injection_kind": injection_kind, "injection_position": position,
        "injection": ({
            "fired_at_step": injection.fired_at,
            "true_value": injection.true_value,
            "corrupt_value": injection.corrupt_value,
            "fingerprint": injection.fingerprint,
            "applicable": injection.fired_at is not None,
        } if injection else None),
        "answer_consistent_with_poison": answer_consistent_with_poison,
        "detected": detected_at is not None,
        "detected_at_step": detected_at,
        "contamination_depth": depth,
        "claims_success": bool((submitted or {}).get("claims_success")),
        "confidence": (submitted or {}).get("confidence"),
        "submitted_answer": answer,
        "outcome_correct": ok,
        "outcome_detail": why,
        "final_snapshot": e.snapshot(),
        "inject_at_nth": inject_at_nth if injection else None,
        "eligible_calls_seen": eligible_seen if injection else None,
        "tool_call_counts": tool_call_counts,
        "n_steps": n_steps, "n_turns": n_turns,
        "hit_step_cap": hit_cap, "truncated": truncated,
        "provider": provider.name,
        "model_requested": cfg.model,
        "model_resolved": sorted({s["model"] for s in steps})[0] if steps else None,
        "steps": steps,
        "tokens": {"input": in_tok, "output": out_tok, "cache_hit": hit_tok,
                   "reasoning": sum(s["reasoning_tokens"] for s in steps)},
        "cost_usd": round(cfg.cost_usd(in_tok, out_tok, hit_tok), 8),
        "wall_clock_s": round(time.perf_counter() - t_start, 3),
    }
