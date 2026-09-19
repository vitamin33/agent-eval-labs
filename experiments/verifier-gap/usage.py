"""Per-call usage export and cost accounting, derived from raw records only.

Two outputs, both computed from the append-only .jsonl and nothing else:

1. A flat table with one row per API call — task, mode, run index, stage,
   every usage field the API returned (input, output, cache hit / miss /
   write, reasoning), the call's cost at the run's rates, and the record's
   ground truth and verdict beside it. Written as CSV next to the results.

2. The cost questions the experiment is asked in practice: what a task
   attempt costs, what a *correct* answer costs, how much was spent on answers
   the verifier approved that were actually wrong (false greens), how much
   self-verification adds, and how many false greens that money removed.

Nothing here rounds toward a nicer number and nothing picks a run: every
figure is a sum over the records given. A quantity with no denominator is
reported as None and printed as "n/a", never as 0.
"""

from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path

CALL_FIELDS = [
    "record_id", "task_id", "task_name", "mode", "run_index", "stage",
    "model", "input_tokens", "output_tokens", "cache_hit_tokens",
    "cache_miss_tokens", "cache_write_tokens", "reasoning_tokens",
    "latency_s", "stop_reason", "truncated", "structured", "cost_usd",
    "truth_initial", "truth_final", "verdict", "confidence", "revised_applied",
]

# Per-call costs are rounded to 1e-8 when recorded; a record's own cost is one
# rounding of the sum. A gap larger than this means the rates disagree.
COST_TOLERANCE = 1e-6


def _rates_for(record: dict, fallback: dict | None) -> dict | None:
    """The rate table a record was costed at: its own (v2) or the caller's."""
    if record.get("pricing"):
        return record["pricing"]
    return fallback


def call_cost_usd(call: dict, rates: dict | None) -> float | None:
    """A call's cost at `rates`, or its recorded cost when it carries one."""
    if call.get("cost_usd") is not None:
        return call["cost_usd"]
    if not rates:
        return None
    hit = max(0, min(call.get("cache_hit_tokens", 0) or 0, call["input_tokens"]))
    miss = call["input_tokens"] - hit
    return (
        miss * rates["input_cache_miss_per_mtok"]
        + hit * rates["input_cache_hit_per_mtok"]
        + call["output_tokens"] * rates["output_per_mtok"]
    ) / 1_000_000


def flatten_calls(records: list[dict], rates: dict | None = None) -> list[dict]:
    """One row per API call, with the record's truth and verdict beside it.

    v1 records have no per-call cost and no cache-miss field; both are derived
    here (cost at `rates`, miss = input - hit) and the derivation is checked
    against the record's own total, so a mismatch surfaces as an error rather
    than as a quietly different number.
    """
    rows: list[dict] = []
    for r in records:
        r_rates = _rates_for(r, rates)
        calls = r.get("calls") or []
        total = 0.0
        for c in calls:
            hit = c.get("cache_hit_tokens", 0) or 0
            miss = c.get("cache_miss_tokens")
            if miss is None:
                miss = max(0, c["input_tokens"] - hit)
            cost = call_cost_usd(c, r_rates)
            if cost is not None:
                total += cost
            rows.append(OrderedDict(
                record_id=r["record_id"],
                task_id=r["task_id"],
                task_name=r.get("task_name"),
                mode=r["mode"],
                run_index=r["run_index"],
                stage=c["stage"],
                model=c.get("model"),
                input_tokens=c["input_tokens"],
                output_tokens=c["output_tokens"],
                cache_hit_tokens=hit,
                cache_miss_tokens=miss,
                cache_write_tokens=c.get("cache_write_tokens", 0) or 0,
                reasoning_tokens=c.get("reasoning_tokens", 0) or 0,
                latency_s=c.get("latency_s"),
                stop_reason=c.get("stop_reason"),
                truncated=bool(c.get("truncated", False)),
                structured=bool(c.get("structured", False)),
                cost_usd=None if cost is None else round(cost, 8),
                truth_initial=r["truth_initial"],
                truth_final=r["truth_final"],
                verdict=r.get("verdict"),
                confidence=r.get("confidence"),
                revised_applied=bool(r.get("revised_applied", False)),
            ))
        if calls and r_rates and abs(total - r["cost_usd"]) > COST_TOLERANCE:
            raise ValueError(
                f"{r['record_id']}: per-call costs sum to {total:.8f} but the record "
                f"says {r['cost_usd']:.8f}; the rate table does not match the run"
            )
    return rows


def write_csv(rows: list[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CALL_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in CALL_FIELDS})
    return path


# --------------------------------------------------------------------------- #
# cost accounting
# --------------------------------------------------------------------------- #


def _verified(r: dict) -> bool:
    return bool((r.get("prompts") or {}).get("verification"))


def _is_false_green(r: dict) -> bool:
    return _verified(r) and r["truth_initial"] != "correct" and r.get("verdict") == "correct"


def _is_false_red(r: dict) -> bool:
    return _verified(r) and r["truth_initial"] == "correct" and r.get("verdict") == "wrong"


def _div(num: float | None, den: float | int | None) -> float | None:
    if num is None or not den:
        return None
    return num / den


def _mode_block(subset: list[dict], rows: list[dict]) -> dict:
    ids = {r["record_id"] for r in subset}
    my_rows = [x for x in rows if x["record_id"] in ids]
    cost = sum(r["cost_usd"] for r in subset)
    correct = [r for r in subset if r["truth_final"] == "correct"]
    ver_rows = [x for x in my_rows if x["stage"] == "verification"]
    ver_cost = sum(x["cost_usd"] or 0.0 for x in ver_rows) if ver_rows else None
    verified = [r for r in subset if _verified(r)]
    shown_wrong = [r for r in verified if r["truth_initial"] != "correct"]
    caught = [r for r in shown_wrong if r.get("verdict") == "wrong"]
    fg = [r for r in subset if _is_false_green(r)]
    fr = [r for r in subset if _is_false_red(r)]
    repaired = [
        r for r in subset
        if r.get("revised_applied") and r["truth_initial"] != "correct"
        and r["truth_final"] == "correct"
    ]
    right_verdicts = [r for r in verified if r.get("verdict") == r["truth_initial"]]
    return {
        "n_records": len(subset),
        "n_calls": len(my_rows),
        "cost_usd": cost,
        "cost_per_record": _div(cost, len(subset)),
        "n_correct": len(correct),
        "cost_per_correct": _div(cost, len(correct)),
        "n_correct_verdicts": len(right_verdicts) if verified else None,
        "cost_per_correct_verdict": _div(cost, len(right_verdicts)) if verified else None,
        "verification_cost_usd": ver_cost,
        "verification_share": _div(ver_cost, cost) if ver_cost is not None else None,
        "n_verified": len(verified) if verified else None,
        "n_shown_wrong": len(shown_wrong) if verified else None,
        "n_caught": len(caught) if verified else None,
        "n_false_green": len(fg) if verified else None,
        "false_green_cost_usd": sum(r["cost_usd"] for r in fg) if verified else None,
        "n_false_red": len(fr) if verified else None,
        "false_red_cost_usd": sum(r["cost_usd"] for r in fr) if verified else None,
        "n_repaired": len(repaired) if verified else None,
        "tokens": {
            "input": sum(x["input_tokens"] for x in my_rows),
            "output": sum(x["output_tokens"] for x in my_rows),
            "cache_hit": sum(x["cache_hit_tokens"] for x in my_rows),
            "cache_miss": sum(x["cache_miss_tokens"] for x in my_rows),
            "cache_write": sum(x["cache_write_tokens"] for x in my_rows),
            "reasoning": sum(x["reasoning_tokens"] for x in my_rows),
        },
    }


def cost_accounting(records: list[dict], rates: dict | None = None) -> dict:
    """Every cost question, per mode, plus the self-verify-vs-baseline delta."""
    rows = flatten_calls(records, rates)
    modes = sorted({r["mode"] for r in records})
    out = {
        "n_records": len(records),
        "n_calls": len(rows),
        "total_cost_usd": sum(r["cost_usd"] for r in records),
        "by_mode": {m: _mode_block([r for r in records if r["mode"] == m], rows) for m in modes},
        "self_verify_vs_baseline": None,
    }
    if "baseline" in modes and "self_verify" in modes:
        b, s = out["by_mode"]["baseline"], out["by_mode"]["self_verify"]
        extra = s["cost_usd"] - b["cost_usd"]
        removed = (s["n_caught"] or 0)
        base_wrong = b["n_records"] - b["n_correct"]
        out["self_verify_vs_baseline"] = {
            "extra_cost_usd": extra,
            "multiplier": _div(s["cost_usd"], b["cost_usd"]),
            "baseline_wrong_answers": base_wrong,
            "self_verify_wrong_before_verification": s["n_shown_wrong"],
            "wrong_answers_caught": s["n_caught"],
            "wrong_answers_repaired": s["n_repaired"],
            "false_greens": s["n_false_green"],
            "false_reds": s["n_false_red"],
            "extra_cost_per_wrong_answer_caught": _div(extra, removed),
            "extra_cost_per_repair": _div(extra, s["n_repaired"] or 0),
            "delta_correct": s["n_correct"] - b["n_correct"],
        }
    return out


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #


def _usd(v: float | None, places: int = 4) -> str:
    return "n/a" if v is None else f"${v:.{places}f}"


def _n(v: int | None) -> str:
    return "n/a" if v is None else f"{v}"


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.0f}%"


def cost_markdown(acc: dict, arm: str, source: str) -> str:
    """The cost table for one arm, as Markdown."""
    modes = list(acc["by_mode"])
    label = {"baseline": "baseline", "self_verify": "self-verify",
             "inject_wrong": "`inject_wrong`", "inject_correct": "`inject_correct`"}
    cols = [label.get(m, m) for m in modes]
    blocks = [acc["by_mode"][m] for m in modes]

    def row(name, fn):
        return f"| {name} | " + " | ".join(fn(b) for b in blocks) + " |"

    lines = [
        f"{acc['n_records']} records · {acc['n_calls']} API calls · "
        f"{_usd(acc['total_cost_usd'])} total, at the declared pricing tier.",
        "",
        "| | " + " | ".join(cols) + " |",
        "|---|" + "---|" * len(cols),
        row("records / API calls", lambda b: f"{b['n_records']} / {b['n_calls']}"),
        row("total cost", lambda b: _usd(b["cost_usd"])),
    ]
    if arm == "generation":
        lines += [
            row("cost per task attempt", lambda b: _usd(b["cost_per_record"], 5)),
            row("correct answers (ground truth, after any revision)",
                lambda b: f"{b['n_correct']} / {b['n_records']}"),
            row("cost per correct answer", lambda b: _usd(b["cost_per_correct"], 5)),
            row("of which verification calls",
                lambda b: "n/a" if b["verification_cost_usd"] is None
                else f"{_usd(b['verification_cost_usd'])} ({_pct(b['verification_share'])})"),
            row("wrong answers reaching the verifier", lambda b: _n(b["n_shown_wrong"])),
            row("of those, caught (verdict \"wrong\")", lambda b: _n(b["n_caught"])),
            row("of those, repaired by the revision", lambda b: _n(b["n_repaired"])),
        ]
    else:
        lines += [
            row("cost per verdict", lambda b: _usd(b["cost_per_record"], 5)),
            row("correct verdicts", lambda b: f"{_n(b['n_correct_verdicts'])} / {b['n_records']}"),
            row("cost per correct verdict", lambda b: _usd(b["cost_per_correct_verdict"], 5)),
        ]
    lines += [
        row("false greens (approved, actually wrong)", lambda b: _n(b["n_false_green"])),
        row("spend on false greens", lambda b: _usd(b["false_green_cost_usd"])),
        row("false reds (rejected, actually correct)", lambda b: _n(b["n_false_red"])),
        row("spend on false reds", lambda b: _usd(b["false_red_cost_usd"])),
        row("tokens: cache hit / miss / write",
            lambda b: f"{b['tokens']['cache_hit']:,} / {b['tokens']['cache_miss']:,} / "
                      f"{b['tokens']['cache_write']:,}"),
    ]
    d = acc.get("self_verify_vs_baseline")
    if d:
        lines += [
            "",
            "**What the second call bought.** Self-verify cost "
            f"{_usd(d['extra_cost_usd'])} more than baseline ({d['multiplier']:.2f}x). "
            f"Its own generation step produced {_n(d['self_verify_wrong_before_verification'])} "
            f"wrong answer(s) for the verifier to catch; it caught {_n(d['wrong_answers_caught'])} "
            f"and repaired {_n(d['wrong_answers_repaired'])}, and approved "
            f"{_n(d['false_greens'])} wrong answer(s). "
            f"Extra cost per wrong answer caught: {_usd(d['extra_cost_per_wrong_answer_caught'])}"
            + (" — nothing was caught because nothing wrong reached the verifier."
               if not d["wrong_answers_caught"] else "")
            + f" Baseline produced {d['baseline_wrong_answers']} wrong answer(s) in the same "
            f"number of attempts; the difference of {d['delta_correct']:+d} correct answer(s) "
            "between the modes comes from generation sampling, not from the verifier, "
            "when no revision was applied.",
        ]
    lines += ["", f"<sub>Generated by `usage.py` from `{source}`. Do not edit by hand.</sub>"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import config as config_mod
    import metrics

    ap = argparse.ArgumentParser(description="per-call usage CSV and cost accounting")
    ap.add_argument("--results", required=True)
    ap.add_argument("--csv", default=None, help="default: <results>.usage.csv")
    ap.add_argument("--config", default=str(config_mod.DEFAULT_CONFIG))
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)
    records = metrics.load_records(args.results)
    rows = flatten_calls(records, cfg.pricing_rates())
    out = Path(args.csv) if args.csv else Path(args.results).with_suffix(".usage.csv")
    write_csv(rows, out)
    acc = cost_accounting(records, cfg.pricing_rates())
    arm = "injection" if any(r.get("injected") for r in records) else "generation"
    print(cost_markdown(acc, arm, Path(args.results).name))
    print(f"\n{len(rows)} calls -> {out}")
    print(json.dumps(acc["self_verify_vs_baseline"], indent=2) if acc["self_verify_vs_baseline"] else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
