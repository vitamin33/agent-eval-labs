#!/usr/bin/env python3
"""Compare two runs of the same arm — the replication check.

The API has no seed, so a live run cannot be reproduced record for record.
What can be checked is whether the *conclusions* survive resampling: run the
same matrix again and ask whether each rate lands inside the other run's
interval, and whether every hypothesis keeps its verdict.

    python experiments/verifier-gap/replicate.py --a run-live-A.jsonl --b run-live-B.jsonl

A disagreement is printed as a disagreement. This script never picks the
better run, and it has no notion of which run is "the" result.
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


def _overlap(a: dict, b: dict) -> bool:
    """Do two Wilson intervals overlap? Non-overlap is the interesting case."""
    if a.get("value") is None or b.get("value") is None:
        return False
    return not (a["ci_high"] < b["ci_low"] or b["ci_high"] < a["ci_low"])


def _fmt(rate: dict) -> str:
    if rate is None or rate.get("value") is None:
        return "n/a"
    return f"{rate['k']}/{rate['n']} = {rate['value']*100:.1f}% [{rate['ci_low']*100:.1f}, {rate['ci_high']*100:.1f}]"


# (label, accessor) for the rates worth comparing across runs.
RATES = [
    ("baseline pass@1", lambda s: s["by_mode"].get("baseline", {}).get("pass_at_1")),
    ("baseline pass^k", lambda s: s["by_mode"].get("baseline", {}).get("pass_hat_k")),
    ("self-verify pass@1", lambda s: s["by_mode"].get("self_verify", {}).get("pass_at_1")),
    ("self-verify pass^k", lambda s: s["by_mode"].get("self_verify", {}).get("pass_hat_k")),
    ("false-green rate", lambda s: s["false_green_rate"]),
    ("false-red rate", lambda s: s["false_red_rate"]),
    ("verifier accuracy", lambda s: s["verifier_accuracy"]),
    ("verdict parse failure", lambda s: s["verdict_parse_failure_rate"]),
    ("truncation rate", lambda s: s.get("truncation_rate")),
]


def compare(sa: dict, sb: dict, name_a: str, name_b: str) -> tuple[str, bool]:
    """Markdown comparison, and whether every comparable figure agrees."""
    agree = True
    lines = [
        f"| Metric | {name_a} | {name_b} | intervals overlap |",
        "|---|---|---|---|",
    ]
    for label, get in RATES:
        ra, rb = get(sa), get(sb)
        if ra is None or rb is None or ra.get("value") is None or rb.get("value") is None:
            if (ra or {}).get("value") is None and (rb or {}).get("value") is None:
                continue
            lines.append(f"| {label} | {_fmt(ra)} | {_fmt(rb)} | n/a |")
            continue
        ok = _overlap(ra, rb)
        agree = agree and ok
        lines.append(f"| {label} | {_fmt(ra)} | {_fmt(rb)} | {'yes' if ok else '**NO**'} |")

    for label, key, fmt in (
        ("ECE", "ece", "{:.4f}"),
        ("Δpass@1 (pp)", "delta_pass_at_1_pp", "{:+.2f}"),
        ("cost multiplier", "cost_multiplier", "{:.2f}x"),
    ):
        va, vb = sa.get(key), sb.get(key)
        if va is None and vb is None:
            continue
        lines.append(
            f"| {label} | {fmt.format(va) if va is not None else 'n/a'} | "
            f"{fmt.format(vb) if vb is not None else 'n/a'} | — |"
        )

    # Hypothesis verdicts are the thing that must not move.
    ha = {r.id: r.verdict for r in hypotheses.evaluate(sa)}
    hb = {r.id: r.verdict for r in hypotheses.evaluate(sb)}
    lines += ["", f"| Hypothesis | {name_a} | {name_b} | same verdict |", "|---|---|---|---|"]
    for hid in sorted(set(ha) | set(hb)):
        same = ha.get(hid) == hb.get(hid)
        agree = agree and same
        lines.append(
            f"| {hid} | {ha.get(hid, 'n/a')} | {hb.get(hid, 'n/a')} | "
            f"{'yes' if same else '**NO**'} |"
        )
    return "\n".join(lines), agree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--a", required=True, help="first results .jsonl")
    ap.add_argument("--b", required=True, help="second results .jsonl")
    ap.add_argument("--k", type=int, default=None)
    args = ap.parse_args(argv)

    ra = metrics.load_records(args.a)
    rb = metrics.load_records(args.b)
    arms = {
        "a": "injection" if any(r.get("injected") for r in ra) else "generation",
        "b": "injection" if any(r.get("injected") for r in rb) else "generation",
    }
    if arms["a"] != arms["b"]:
        print(f"refusing to compare a {arms['a']} run with a {arms['b']} run", file=sys.stderr)
        return 2

    k = args.k or max(r["run_index"] for r in ra) + 1
    sa, sb = metrics.summarize(ra, k=k), metrics.summarize(rb, k=k)
    md, agree = compare(sa, sb, Path(args.a).name, Path(args.b).name)
    print(f"Replication check — {arms['a']} arm, k={k}\n")
    print(md)
    print()
    print(
        "Every comparable figure agrees and no hypothesis changed verdict."
        if agree
        else "DISAGREEMENT: a figure or a verdict moved between the two runs. "
        "Both runs stand; neither is discarded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
