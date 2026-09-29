#!/usr/bin/env python3
"""Run the experiment 3 matrix.

    python experiments/agent-checkpoint/ckpt_runner.py --dry-run --stage 1
    python experiments/agent-checkpoint/ckpt_runner.py --live --stage 0

Stage 0 is the pilot: clean only, one run per task, used for the ceiling and
the firing check. Stages 1 and 2 run the full matrix at k = 2 and k = 5.
Records are appended one JSON object per line and never rewritten.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "agent-verifier-gap", HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ckpt_agent  # noqa: E402
import ckpt_config  # noqa: E402
import ckpt_mock  # noqa: E402
import ckpt_tasks  # noqa: E402
import config as config1  # noqa: E402
from provider import build_provider  # noqa: E402

RESULTS_DIR = HERE / "results"


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


HARNESS_COMMIT = _git_head()


def cells(stage: int, runs: int, arms=ckpt_config.MODES):
    """(task, mode, run_index) for the stage. Stage 0 is the clean pilot;
    every other stage runs the config's arms at the stage's k."""
    for task in ckpt_tasks.TASKS:
        if stage == 0:
            yield task, "clean", 0
            continue
        for mode in arms:
            for run_i in range(runs):
                yield task, mode, run_i


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--dry-run", action="store_true")
    which.add_argument("--live", action="store_true")
    ap.add_argument("--stage", type=int, default=1, choices=[0, 1, 2, 3, 4],
                    help="0 pilot; 1/2 the DeepSeek matrix; 3/4 the replication stages (k from config)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=str(ckpt_config.DEFAULT_CONFIG))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    config1.load_dotenv()
    cfg = ckpt_config.load(args.config)
    stages = ckpt_config.stage_runs(cfg)
    if args.stage not in stages:
        print(f"stage {args.stage} is not declared in {cfg.path} (stage_runs: {stages})", file=sys.stderr)
        return 2
    runs = stages[args.stage]
    step_cap = ckpt_config.step_cap(cfg)
    plan = list(cells(args.stage, runs, cfg.modes))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = f"ckpt-stage{args.stage}-{stamp}" if args.stage <= 2 else \
        f"ckpt-stage{args.stage}-{ckpt_config.tag(cfg)}-{stamp}"
    out_path = Path(args.out) if args.out else RESULTS_DIR / f"{label}.jsonl"
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"refusing to append to existing results file: {out_path}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)

    provider = ckpt_mock.build(cfg) if args.dry_run else build_provider(cfg, dry_run=False, tasks={})
    print(f"stage={args.stage} arms={list(cfg.modes)} runs_per_cell={runs} trajectories={len(plan)} "
          f"model={cfg.model} max_tokens={cfg.max_tokens} step_cap={step_cap} "
          f"pricing_tier={cfg.pricing_tier} harness={HARNESS_COMMIT and HARNESS_COMMIT[:8]}")
    print(f"writing {out_path}")

    spent = 0.0
    with out_path.open("a", encoding="utf-8") as fh:
        for n, (task, mode, run_i) in enumerate(plan, 1):
            rec = ckpt_agent.run_trajectory(
                provider, cfg, task, mode, run_i, step_cap=step_cap,
                harness_commit=HARNESS_COMMIT,
            )
            rec["stage"] = args.stage
            rec["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            fh.flush()
            spent += rec["cost_usd"]
            if not args.quiet:
                inj = rec.get("injection") or {}
                print(
                    f"  [{n:3d}/{len(plan)}] {rec['trajectory_id']:24s} "
                    f"ok={str(rec['outcome_correct']):5s} claims={str(rec['claims_success']):5s} "
                    f"silent={str(rec['silent_failure']):5s} det={str(rec['detected']):5s} "
                    f"fired={str(inj.get('applicable')):5s} rec={rec['reconcile_calls']} "
                    f"steps={rec['n_steps']:2d} ${rec['cost_usd']:.4f} {rec['wall_clock_s']:.1f}s",
                    flush=True,
                )
    print(f"\n{len(plan)} trajectories -> {out_path}  (${spent:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
