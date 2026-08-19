#!/usr/bin/env python3
"""Run the verifier-gap matrix.

    python experiments/verifier-gap/runner.py --dry-run          # offline, mocked
    python experiments/verifier-gap/runner.py --live             # calls the API

Modes:
  baseline     one generation call; the answer is graded.
  self_verify  the identical generation call, then a second call carrying the
               verification block. If the verifier says "wrong" and supplies a
               revision, the revision becomes the final answer.

Records are appended one JSON object per line and never rewritten.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import config as config_mod  # noqa: E402
import prompts  # noqa: E402
from grade import CORRECT, Grade, grade_completion  # noqa: E402
from provider import VERDICT_SCHEMA, build_provider  # noqa: E402
from tasks import load_tasks  # noqa: E402
from verdict import parse_verdict  # noqa: E402

SCHEMA_VERSION = 1
RESULTS_DIR = HERE / "results"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_record(provider, cfg, task: dict, mode: str, run_index: int) -> dict:
    """Execute one (task, mode, run_index) cell and return its record."""
    t_start = time.perf_counter()
    trace = {"task_id": task["id"], "mode": mode, "run_index": run_index}
    calls: list[dict] = []

    # --- generation: identical request in both modes ----------------------- #
    gen_messages = prompts.generation_messages(task)
    gen = provider.complete(
        prompts.SYSTEM, gen_messages, trace={**trace, "stage": "generation"}
    )
    calls.append(
        {
            "stage": "generation",
            "input_tokens": gen.input_tokens,
            "output_tokens": gen.output_tokens,
            "latency_s": round(gen.latency_s, 4),
            "stop_reason": gen.stop_reason,
            "model": gen.model,
        }
    )

    grade_initial: Grade = grade_completion(gen.text, task, timeout_s=cfg.grading_timeout_s)
    grade_final = grade_initial
    verification_prompt = None
    verification_text = None
    v = None
    revised_applied = False

    # --- verification: the ONLY difference between the two modes ----------- #
    if mode == "self_verify":
        ver_messages = prompts.verification_messages(task, gen.text)
        verification_prompt = prompts.VERIFICATION_BLOCK
        ver = provider.complete(
            prompts.SYSTEM,
            ver_messages,
            schema=VERDICT_SCHEMA,
            trace={
                **trace,
                "stage": "verification",
                "truth_correct": grade_initial.is_correct,
                "revision_code": task["reference"].strip(),
            },
        )
        verification_text = ver.text
        calls.append(
            {
                "stage": "verification",
                "input_tokens": ver.input_tokens,
                "output_tokens": ver.output_tokens,
                "latency_s": round(ver.latency_s, 4),
                "stop_reason": ver.stop_reason,
                "model": ver.model,
            }
        )
        v = parse_verdict(ver.text, structured=ver.structured)
        if v.verdict == "wrong" and v.revised:
            grade_final = grade_completion(v.revised, task, timeout_s=cfg.grading_timeout_s)
            revised_applied = True

    in_tok = sum(c["input_tokens"] for c in calls)
    out_tok = sum(c["output_tokens"] for c in calls)
    models = {c["model"] for c in calls}

    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": f"{task['id']}|{mode}|{run_index}",
        "task_id": task["id"],
        "task_name": task["name"],
        "task_type": task["type"],
        "task_kind": task["kind"],
        "mode": mode,
        "run_index": run_index,
        "provider": provider.name,
        "model_requested": cfg.model,
        "model_resolved": sorted(models)[0] if len(models) == 1 else "|".join(sorted(models)),
        "temperature": cfg.temperature,
        "seed": cfg.seed,
        "prompts": {
            "system": prompts.SYSTEM,
            "generation": prompts.generation_prompt(task),
            "verification": verification_prompt,
        },
        "completion_generation": gen.text,
        "completion_verification": verification_text,
        "grade_initial": grade_initial.to_dict(),
        "grade_final": grade_final.to_dict(),
        "truth_initial": CORRECT if grade_initial.is_correct else "wrong",
        "truth_final": CORRECT if grade_final.is_correct else "wrong",
        "verdict": v.verdict if v else None,
        "confidence": v.confidence if v else None,
        "verdict_source": v.source if v else None,
        "revised_applied": revised_applied,
        "calls": calls,
        "tokens": {"input": in_tok, "output": out_tok},
        "cost_usd": round(cfg.cost_usd(in_tok, out_tok), 8),
        "wall_clock_s": round(time.perf_counter() - t_start, 4),
        "timestamp": _now(),
    }


def run_matrix(cfg, *, dry_run: bool, out_path: Path, progress=True) -> list[dict]:
    tasks = load_tasks()
    provider = build_provider(cfg, dry_run=dry_run, tasks={t["id"]: t for t in tasks})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    total = len(tasks) * len(cfg.modes) * cfg.runs_per_cell
    n = 0
    # Deterministic order: task, then mode, then run index.
    with out_path.open("a", encoding="utf-8") as fh:
        for task in tasks:
            for mode in cfg.modes:
                for run_index in range(cfg.runs_per_cell):
                    rec = run_record(provider, cfg, task, mode, run_index)
                    fh.write(json.dumps(rec, sort_keys=True) + "\n")
                    fh.flush()
                    records.append(rec)
                    n += 1
                    if progress:
                        print(
                            f"  [{n:3d}/{total}] {rec['record_id']:22s} "
                            f"truth={rec['truth_final']:8s} verdict={str(rec['verdict']):8s} "
                            f"tok={rec['tokens']['input']}/{rec['tokens']['output']}",
                            flush=True,
                        )
    return records


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="offline, seeded mock responses")
    mode.add_argument("--live", action="store_true", help="call the Anthropic API")
    ap.add_argument("--config", default=str(config_mod.DEFAULT_CONFIG))
    ap.add_argument("--out", default=None, help="output .jsonl path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        kind = "dry" if args.dry_run else "live"
        out_path = RESULTS_DIR / f"run-{kind}-{stamp}.jsonl"

    # A results file is append-only; refuse to reopen a completed run.
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"refusing to append to existing results file: {out_path}", file=sys.stderr)
        return 2

    print(f"model={cfg.model} temperature={cfg.temperature} k={cfg.runs_per_cell} "
          f"provider={'mock' if args.dry_run else 'anthropic'}")
    print(f"writing {out_path}")
    records = run_matrix(cfg, dry_run=args.dry_run, out_path=out_path, progress=not args.quiet)

    cost = sum(r["cost_usd"] for r in records)
    print(f"\n{len(records)} records -> {out_path}")
    print(f"total cost: ${cost:.4f}" + ("  (synthetic — mock provider)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
