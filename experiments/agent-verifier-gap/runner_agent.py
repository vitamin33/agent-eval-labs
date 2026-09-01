#!/usr/bin/env python3
"""Run the agent-trajectory matrix.

    python experiments/agent-verifier-gap/runner_agent.py --live --stage 1

Records are appended one JSON object per line and never rewritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import agent  # noqa: E402
import agent_tasks  # noqa: E402
import config as config_mod  # noqa: E402
import inject  # noqa: E402
from provider import build_provider  # noqa: E402

RESULTS_DIR = HERE / "results"

# One injection kind per task, chosen for APPLICABILITY: the tool it corrupts is
# one the task reliably calls. Kind is therefore confounded with task and is not
# a factor in the matrix; no kind-level conclusion is drawn from this design.
PRIMARY_KIND = {
    "T1": inject.OMISSION,
    "T2": inject.OFF_BY_ONE,
    "T3": inject.WRONG_FIELD,
    "T4": inject.WRONG_FIELD,
    "T5": inject.STALE,
    "T6": inject.OMISSION,
    "T7": inject.OMISSION,
    "T8": inject.WRONG_FIELD,
}

STAGE_RUNS = {0: 1, 1: 2, 2: 5}


def cells(cfg, runs: int):
    """(task, mode, kind, position, run_index) for the whole matrix."""
    for task in agent_tasks.TASKS:
        for run_i in range(runs):
            yield task, "clean", None, None, run_i
        for mode in ("inject", "inject_verify"):
            for position in ("early", "late"):
                for run_i in range(runs):
                    yield task, mode, PRIMARY_KIND[task["id"]], position, run_i


def probe_eligible_calls(provider, cfg, task, kind, step_cap) -> int:
    """How many times does this task actually call the tool the injection targets?

    One clean run per task, reused across that task's late cells. Needed because
    `late` means "the last eligible call", which the loop cannot recognise while
    it is still running. Stage 1's turn-based definition fired 0 times in 32.
    """
    rec = agent.run_trajectory(provider, cfg, task, "clean", 0, step_cap=step_cap)
    target = inject.TARGET_TOOL[kind]
    return rec.get("tool_call_counts", {}).get(target, 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--stage", type=int, default=1, choices=[0, 1, 2])
    ap.add_argument("--out", default=None)
    ap.add_argument("--step-cap", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    config_mod.load_dotenv()
    cfg = config_mod.load()
    import dataclasses

    # Sized from the stage-0 pilot: a tool decision costs ~290 output tokens,
    # so experiment 1's 49152 is pure headroom here.
    cfg = dataclasses.replace(cfg, max_tokens=args.max_tokens)

    runs = STAGE_RUNS[args.stage]
    plan = list(cells(cfg, runs))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else RESULTS_DIR / f"traj-stage{args.stage}-{stamp}.jsonl"
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"refusing to append to existing results file: {out_path}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)

    provider = build_provider(cfg, dry_run=args.dry_run, tasks={})
    print(f"stage={args.stage} runs_per_cell={runs} trajectories={len(plan)} "
          f"model={cfg.model} max_tokens={cfg.max_tokens} step_cap={args.step_cap}")
    print(f"writing {out_path}")

    late_n: dict[str, int] = {}
    with out_path.open("a", encoding="utf-8") as fh:
        for n, (task, mode_name, kind, position, run_i) in enumerate(plan, 1):
            nth = 1
            if position == "late":
                if task["id"] not in late_n:
                    late_n[task["id"]] = max(
                        1, probe_eligible_calls(provider, cfg, task, kind, args.step_cap)
                    )
                    print(f"  probe {task['id']}: target tool called "
                          f"{late_n[task['id']]}x -> late injects on that call", flush=True)
                nth = late_n[task["id"]]
            rec = agent.run_trajectory(
                provider, cfg, task, mode_name, run_i,
                injection_kind=kind, position=position, step_cap=args.step_cap,
                inject_at_nth=nth,
            )
            rec["stage"] = args.stage
            rec["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            fh.flush()
            if not args.quiet:
                inj = rec.get("injection") or {}
                print(
                    f"  [{n:3d}/{len(plan)}] {rec['trajectory_id']:26s} "
                    f"ok={str(rec['outcome_correct']):5s} claims={str(rec['claims_success']):5s} "
                    f"det={str(rec['detected']):5s} depth={str(rec['contamination_depth']):4s} "
                    f"appl={str(inj.get('applicable')):5s} steps={rec['n_steps']:2d} "
                    f"{rec['wall_clock_s']:.1f}s",
                    flush=True,
                )
    print(f"\n{len(plan)} trajectories -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
