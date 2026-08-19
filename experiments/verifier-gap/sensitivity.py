#!/usr/bin/env python3
"""Leave-hardest-out sensitivity analysis (REVIEW.md R4).

Ten tasks is a small n. If the headline conclusions rest on the two tasks the
model happened to fail most, they are a property of those tasks rather than of
the generate-verify asymmetry. This recomputes every hypothesis with the two
hardest tasks dropped and reports which verdicts, if any, flip.

    python experiments/verifier-gap/sensitivity.py --results results/run-live-*.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hypotheses  # noqa: E402
import metrics  # noqa: E402


def hardest_tasks(records: list[dict], n: int = 2) -> list[str]:
    """The n tasks with the lowest baseline pass@1; ties broken by task id."""
    per = metrics.pass_at_1_by_task([r for r in records if r["mode"] == "baseline"])
    ranked = sorted(per.items(), key=lambda kv: (kv[1].value if kv[1].value is not None else 1.0, kv[0]))
    return [tid for tid, _ in ranked[:n]]


def analyse(records: list[dict], k: int, n_drop: int = 2) -> dict:
    full = metrics.summarize(records, k=k)
    dropped = hardest_tasks(records, n_drop)
    kept = [r for r in records if r["task_id"] not in dropped]
    reduced = metrics.summarize(kept, k=k)

    before = {r.id: r for r in hypotheses.evaluate(full)}
    after = {r.id: r for r in hypotheses.evaluate(reduced)}
    flips = [
        {"id": hid, "before": before[hid].verdict, "after": after[hid].verdict,
         "observed_before": before[hid].observed, "observed_after": after[hid].observed}
        for hid in before
        if before[hid].verdict != after[hid].verdict
    ]
    return {
        "dropped_tasks": dropped,
        "n_records_full": len(records),
        "n_records_reduced": len(kept),
        "full": before,
        "reduced": after,
        "flips": flips,
        "conclusions_stable": not flips,
    }


def to_markdown(analysis: dict) -> str:
    lines = [
        f"Dropped the {len(analysis['dropped_tasks'])} hardest tasks by baseline pass@1: "
        f"**{', '.join(analysis['dropped_tasks'])}** "
        f"({analysis['n_records_full']} → {analysis['n_records_reduced']} records).",
        "",
        "| Hypothesis | Full set | Hardest two removed | Flips? |",
        "|---|---|---|---|",
    ]
    for hid in sorted(analysis["full"]):
        b, a = analysis["full"][hid], analysis["reduced"][hid]
        flip = "**YES**" if b.verdict != a.verdict else "no"
        lines.append(
            f"| {hid} | {b.verdict} ({b.observed}) | {a.verdict} ({a.observed}) | {flip} |"
        )
    lines += [
        "",
        (
            "**No conclusion depends on the two hardest tasks.**"
            if analysis["conclusions_stable"]
            else f"**{len(analysis['flips'])} conclusion(s) flip** — the result is "
                 "sensitive to task selection and must be reported as such."
        ),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", required=True)
    ap.add_argument("--drop", type=int, default=2)
    args = ap.parse_args(argv)

    records = metrics.load_records(args.results)
    k = max(r["run_index"] for r in records) + 1
    print(to_markdown(analyse(records, k=k, n_drop=args.drop)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
