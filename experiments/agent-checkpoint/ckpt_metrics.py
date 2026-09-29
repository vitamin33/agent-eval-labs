"""Metrics for experiment 3, computed from raw trajectory records only.

Uncertainty machinery (`Rate`, Wilson) is experiment 1's, so all three
experiments report intervals identically. Every function returns `Rate` with
`None` on an empty denominator; nothing is read back from a summary.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from metrics import Rate, wilson  # noqa: E402,F401

INJECT_MODES = ("inject", "inject_tool", "inject_enforced")
MODES = ("clean",) + INJECT_MODES
BASELINE = "inject"
CONFOUND_CONTROL = "T7"


def load(path: str | Path) -> list[dict]:
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{i}: malformed trajectory: {exc}") from exc
    return out


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #


def _mode(records: list[dict], mode: str | None) -> list[dict]:
    return records if mode is None else [r for r in records if r.get("mode") == mode]


def fired(records: list[dict], mode: str | None = None) -> list[dict]:
    """Trajectories where an injection actually fired. One whose targeted tool
    was never called is not a clean run and must not dilute a denominator."""
    return [
        r for r in _mode(records, mode)
        if r.get("mode") in INJECT_MODES and (r.get("injection") or {}).get("applicable")
    ]


# --------------------------------------------------------------------------- #
# rates
# --------------------------------------------------------------------------- #


def silent_failure_rate(records: list[dict], mode: str | None = None) -> Rate:
    """The headline: P(outcome wrong AND claims success | injection fired)."""
    subset = fired(records, mode)
    return Rate(sum(1 for r in subset if r.get("silent_failure")), len(subset))


def false_green_rate(records: list[dict], mode: str | None = None) -> Rate:
    """Experiment 2's conditional rate: P(claims success | outcome wrong),
    over every trajectory of the mode that finished wrong."""
    wrong = [r for r in _mode(records, mode) if not r.get("outcome_correct")]
    return Rate(sum(1 for r in wrong if r.get("claims_success")), len(wrong))


def outcome_pass_rate(records: list[dict], mode: str | None = None) -> Rate:
    subset = _mode(records, mode)
    return Rate(sum(1 for r in subset if r.get("outcome_correct")), len(subset))


def outcome_pass_rate_fired(records: list[dict], mode: str | None = None) -> Rate:
    subset = fired(records, mode)
    return Rate(sum(1 for r in subset if r.get("outcome_correct")), len(subset))


def detection_rate(records: list[dict], mode: str | None = None,
                   include_control: bool = False) -> Rate:
    """P(agent re-examined the corrupted subject | fired), T7 excluded."""
    subset = [r for r in fired(records, mode)
              if include_control or r.get("task_id") != CONFOUND_CONTROL]
    return Rate(sum(1 for r in subset if r.get("detected")), len(subset))


def reconcile_usage_rate(records: list[dict]) -> Rate:
    """P(at least one reconcile call | inject_tool trajectory)."""
    subset = _mode(records, "inject_tool")
    return Rate(sum(1 for r in subset if r.get("reconcile_used")), len(subset))


def reconcile_on_subject_rate(records: list[dict]) -> Rate:
    """P(a reconcile call re-asked the corrupted question | fired, inject_tool)."""
    subset = fired(records, "inject_tool")
    return Rate(sum(1 for r in subset if r.get("reconcile_on_subject")), len(subset))


def injection_not_applicable_rate(records: list[dict]) -> Rate:
    attempted = [r for r in records if r.get("mode") in INJECT_MODES]
    na = [r for r in attempted if not (r.get("injection") or {}).get("applicable")]
    return Rate(len(na), len(attempted))


def step_cap_rate(records: list[dict]) -> Rate:
    return Rate(sum(1 for r in records if r.get("hit_step_cap")), len(records))


def truncation_rate(records: list[dict]) -> Rate:
    return Rate(sum(1 for r in records if r.get("truncated")), len(records))


# --------------------------------------------------------------------------- #
# contamination
# --------------------------------------------------------------------------- #


def contamination_depths(records: list[dict], mode: str | None = None) -> list[int]:
    return [r["contamination_depth"] for r in fired(records, mode)
            if r.get("contamination_depth") is not None
            and r.get("task_id") != CONFOUND_CONTROL]


def contamination_summary(records: list[dict], mode: str | None = None) -> dict:
    d = contamination_depths(records, mode)
    if not d:
        return {"n": 0, "median": None, "min": None, "max": None, "distribution": {}}
    dist: dict[int, int] = {}
    for x in d:
        dist[x] = dist.get(x, 0) + 1
    return {"n": len(d), "median": statistics.median(d), "min": min(d), "max": max(d),
            "mean": round(statistics.fmean(d), 2), "distribution": dict(sorted(dist.items()))}


# --------------------------------------------------------------------------- #
# cost
# --------------------------------------------------------------------------- #


def total_cost(records: list[dict], mode: str | None = None) -> float:
    return sum(r.get("cost_usd", 0.0) for r in _mode(records, mode))


def mean_cost(records: list[dict], mode: str | None = None) -> float | None:
    subset = _mode(records, mode)
    return total_cost(subset) / len(subset) if subset else None


def cost_multiplier(records: list[dict], mode: str, baseline: str = BASELINE) -> float | None:
    """Mean cost per trajectory of `mode` over `baseline`. A ratio of means,
    so unequal cell counts cannot tilt it; with equal counts it is exactly
    the ratio of totals RESEARCH.md names."""
    a, b = mean_cost(records, mode), mean_cost(records, baseline)
    return (a / b) if (a is not None and b) else None


def cost_per_correct(records: list[dict], mode: str) -> float | None:
    subset = _mode(records, mode)
    correct = sum(1 for r in subset if r.get("outcome_correct"))
    return total_cost(subset) / correct if correct else None


def cost_per_avoided_silent_failure(records: list[dict], mode: str,
                                    baseline: str = BASELINE) -> float | None:
    """Extra spend per silent failure removed, relative to the baseline:
    (mean cost of mode − mean cost of baseline) / (baseline rate − mode rate),
    both per fired trajectory. None when the mode removes nothing."""
    dc = mean_cost(records, mode)
    db = mean_cost(records, baseline)
    rm, rb = silent_failure_rate(records, mode).value, silent_failure_rate(records, baseline).value
    if dc is None or db is None or rm is None or rb is None or rb - rm <= 0:
        return None
    return (dc - db) / (rb - rm)


# --------------------------------------------------------------------------- #
# determinism at temperature 0
# --------------------------------------------------------------------------- #


def signature(record: dict) -> str:
    return json.dumps([(s.get("tool"), s.get("args")) for s in record.get("steps", [])],
                      sort_keys=True)


def distinct_trajectories_per_cell(records: list[dict]) -> dict:
    """How much k actually buys: cells with more than one distinct tool
    sequence across their runs, over cells with more than one run."""
    cells: dict[tuple, set] = {}
    counts: dict[tuple, int] = {}
    for r in records:
        key = (r.get("task_id"), r.get("mode"))
        cells.setdefault(key, set()).add(signature(r))
        counts[key] = counts.get(key, 0) + 1
    multi = [k for k, n in counts.items() if n > 1]
    varied = [k for k in multi if len(cells[k]) > 1]
    return {"cells_with_repeats": len(multi), "cells_with_variation": len(varied),
            "rate": Rate(len(varied), len(multi)).to_dict()}


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #


def summarize(records: list[dict]) -> dict:
    modes = [m for m in MODES if any(r.get("mode") == m for r in records)]
    out = {
        "n_trajectories": len(records),
        "modes_present": modes,
        "providers": sorted({r.get("provider") for r in records}),
        "models_requested": sorted({r.get("model_requested") for r in records
                                    if r.get("model_requested")}),
        "models_resolved": sorted({r.get("model_resolved") for r in records
                                   if r.get("model_resolved")}),
        "reconcile_usage_rate": reconcile_usage_rate(records).to_dict(),
        "reconcile_on_subject_rate": reconcile_on_subject_rate(records).to_dict(),
        "injection_not_applicable_rate": injection_not_applicable_rate(records).to_dict(),
        "step_cap_rate": step_cap_rate(records).to_dict(),
        "truncation_rate": truncation_rate(records).to_dict(),
        "variation": distinct_trajectories_per_cell(records),
        "total_cost_usd": round(total_cost(records), 6),
        "by_mode": {},
        "per_task": {},
    }
    for m in modes:
        subset = _mode(records, m)
        out["by_mode"][m] = {
            "n": len(subset),
            "n_fired": len(fired(subset)) if m != "clean" else None,
            "outcome_pass_rate": outcome_pass_rate(subset).to_dict(),
            "outcome_pass_rate_fired": outcome_pass_rate_fired(subset).to_dict(),
            "silent_failure_rate": silent_failure_rate(subset).to_dict(),
            "false_green_rate": false_green_rate(subset).to_dict(),
            "detection_rate": detection_rate(subset).to_dict(),
            "contamination": contamination_summary(subset),
            "mean_steps": round(statistics.fmean([r["n_steps"] for r in subset]), 1) if subset else None,
            "cost_usd": round(total_cost(subset), 6),
            "mean_cost_usd": round(mean_cost(subset) or 0.0, 8),
            "cost_multiplier": cost_multiplier(records, m),
            "cost_per_correct_usd": cost_per_correct(records, m),
            "cost_per_avoided_silent_failure_usd": cost_per_avoided_silent_failure(records, m),
            "tokens": {k: sum(r.get("tokens", {}).get(k, 0) for r in subset)
                       for k in ("input", "output", "cache_hit", "cache_miss", "reasoning")},
        }
    for tid in sorted({r["task_id"] for r in records}):
        t = [r for r in records if r["task_id"] == tid]
        out["per_task"][tid] = {
            "n": len(t),
            "outcome_pass": outcome_pass_rate(t).to_dict(),
            "silent_failure_by_mode": {m: silent_failure_rate(t, m).to_dict()
                                       for m in modes if m != "clean"},
            "fired_by_mode": {m: len(fired(t, m)) for m in modes if m != "clean"},
            "detected": detection_rate(t, include_control=True).to_dict(),
            "is_confound_control": tid == CONFOUND_CONTROL,
        }
    return out
