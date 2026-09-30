#!/usr/bin/env python3
"""One tiny tool-calling round trip against a provider config, before a run.

    python tools/ping_provider.py --config experiments/agent-checkpoint/config.haiku45.yaml

Prints the served model id, whether it matches the pin, the token accounting
the provider reported (cache fields included) and the priced cost of the
call. Costs a fraction of a cent. It exists so a missing key, a retired
model id, a rejected `temperature`, or an endpoint that reports no cache
fields is found here and not 40 trajectories into a stage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "experiments" / "agent-checkpoint", ROOT / "experiments" / "agent-verifier-gap",
          ROOT / "experiments" / "verifier-gap"):
    sys.path.insert(0, str(p))

import ckpt_config  # noqa: E402
import ckpt_prompts  # noqa: E402
import config as config1  # noqa: E402
from provider import build_provider  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    args = ap.parse_args(argv)

    config1.load_dotenv()
    cfg = ckpt_config.load(args.config)
    try:
        provider = build_provider(cfg, dry_run=False, tasks={})
    except RuntimeError as exc:
        print(f"NOT READY: {exc}")
        return 2

    messages = [
        {"role": "system", "content": ckpt_prompts.system_prompt("inject")},
        {"role": "user", "content": "Call count_orders with status 'pending', then submit the number "
                                    "with claims_success true and confidence 50."},
    ]
    tools = ckpt_prompts.tool_schemas("inject")
    message, acct = provider.chat_tools(messages, tools)
    calls = [(c.function.name, c.function.arguments) for c in (message.tool_calls or [])]
    cost = cfg.cost_usd(acct.input_tokens, acct.output_tokens, acct.cache_hit_tokens,
                        acct.cache_write_tokens)
    on_pin = acct.model == cfg.model or acct.model.startswith(cfg.model)
    print(json.dumps({
        "provider": provider.name,
        "requested": cfg.model, "served": acct.model, "on_pin": on_pin,
        "tool_calls": calls, "stop_reason": acct.stop_reason,
        "tokens": {"input": acct.input_tokens, "output": acct.output_tokens,
                   "cache_hit": acct.cache_hit_tokens, "cache_miss": acct.cache_miss_tokens,
                   "cache_write": acct.cache_write_tokens, "reasoning": acct.reasoning_tokens},
        "cost_usd": round(cost, 8), "latency_s": round(acct.latency_s, 2),
    }, indent=2))
    if not calls:
        print("WARNING: the model made no tool call; check the tool schema translation")
        return 1
    if not on_pin:
        print("WARNING: served model differs from the pin; gate G10 will name this run off-pin")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
