"""Trajectory-level metrics.

Reuses experiment 1's `Rate` and Wilson interval so the two experiments report
uncertainty identically. Everything here is computed from the raw trajectory
records; nothing is read back from a summary.
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

from metrics import Rate, wilson  # noqa: E402,F401  (shared uncertainty machinery)

# T7's content IS cross-checking, so an agent may verify because it was told to
# rather than because it grew suspicious. Excluded from headline detection and
# reported on its own.
CONFOUND_CONTROL = "T7"

INJECT_MODES = ("inject", "inject_verify")


def load(path: str | Path) -> list[dict]:
    path = Path(path)
    out = []
    with path.open(encoding="utf-8") as fh:
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


def injected(records: list[dict], include_control: bool = False) -> list[dict]:
    """Trajectories where an injection actually fired.

    A trajectory whose targeted tool was never called is NOT a clean run and
    must not dilute the denominator; it is reported separately as
    `injection_not_applicable_rate`.
    """
    return [
        r for r in records
        if r.get("mode") in INJECT_MODES
        and (r.get("injection") or {}).get("applicable")
        and (include_control or r.get("task_id") != CONFOUND_CONTROL)
    ]


def _mode(records: list[dict], mode: str) -> list[dict]:
    return [r for r in records if r.get("mode") == mode]


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #


def detection_rate(records: list[dict], include_control: bool = False) -> Rate:
    """P(agent re-examined the corrupted subject | a silent failure fired)."""
    subset = injected(records, include_control)
    return Rate(sum(1 for r in subset if r.get("detected")), len(subset))


def trajectory_false_green_rate(records: list[dict]) -> Rate:
    """The headline: P(claims success | the outcome is actually wrong).

    Computed over every trajectory that finished wrong, injected or not — an
    agent that fails on its own and still says "done" is the same failure.
    """
    wrong = [r for r in records if not r.get("outcome_correct")]
    return Rate(sum(1 for r in wrong if r.get("claims_success")), len(wrong))


def outcome_pass_rate(records: list[dict], mode: str | None = None) -> Rate:
    subset = _mode(records, mode) if mode else records
    return Rate(sum(1 for r in subset if r.get("outcome_correct")), len(subset))


def recovery_rate(records: list[dict]) -> Rate:
    """P(outcome correct | the agent detected the failure).

    Detecting a problem and still failing is a different failure from never
    noticing, so it is reported separately rather than folded into detection.
    """
    detected = [r for r in injected(records) if r.get("detected")]
    return Rate(sum(1 for r in detected if r.get("outcome_correct")), len(detected))


def injection_not_applicable_rate(records: list[dict]) -> Rate:
    attempted = [r for r in records if r.get("mode") in INJECT_MODES]
    na = [r for r in attempted if not (r.get("injection") or {}).get("applicable")]
    return Rate(len(na), len(attempted))


def step_cap_rate(records: list[dict]) -> Rate:
    return Rate(sum(1 for r in records if r.get("hit_step_cap")), len(records))


def contamination_depths(records: list[dict]) -> list[int]:
    return [
        r["contamination_depth"] for r in injected(records)
        if r.get("contamination_depth") is not None
    ]


def contamination_summary(records: list[dict]) -> dict:
    """Median plus the full distribution — a mean alone would hide the tail."""
    d = contamination_depths(records)
    if not d:
        return {"n": 0, "median": None, "min": None, "max": None, "distribution": {}}
    dist: dict[int, int] = {}
    for x in d:
        dist[x] = dist.get(x, 0) + 1
    return {
        "n": len(d),
        "median": statistics.median(d),
        "min": min(d), "max": max(d),
        "mean": round(statistics.fmean(d), 2),
        "distribution": dict(sorted(dist.items())),
    }


def tasks_with_manipulated_position(records: list[dict]) -> set[str]:
    """Tasks where `early` and `late` are genuinely different injection points.

    When the targeted tool is called once, M = 1 and the late injection lands on
    the same call as the early one — the factor is not manipulated, and those
    trajectories dilute the late group toward early behaviour. Membership is
    decided by the probe (`inject_at_nth`), which is measured before any
    detection is observed, so this is not an outcome-dependent selection.
    """
    return {
        r["task_id"] for r in records
        if r.get("injection_position") == "late" and (r.get("inject_at_nth") or 1) > 1
    }


def detection_by_position(records: list[dict], manipulated_only: bool = False) -> dict[str, dict]:
    keep = tasks_with_manipulated_position(records) if manipulated_only else None
    out = {}
    for pos in ("early", "late"):
        subset = [
            r for r in injected(records)
            if r.get("injection_position") == pos
            and (keep is None or r["task_id"] in keep)
        ]
        out[pos] = Rate(sum(1 for r in subset if r.get("detected")), len(subset)).to_dict()
    if keep is not None:
        out["tasks"] = sorted(keep)
    return out


def total_cost(records: list[dict]) -> float:
    return sum(r.get("cost_usd", 0.0) for r in records)


def summarize(records: list[dict]) -> dict:
    modes = sorted({r["mode"] for r in records})
    det_plain = detection_rate(_mode(records, "inject"))
    det_verify = detection_rate(_mode(records, "inject_verify"))
    cost_plain = total_cost(_mode(records, "inject"))
    cost_verify = total_cost(_mode(records, "inject_verify"))

    delta = None
    if det_plain.value is not None and det_verify.value is not None:
        delta = round(100 * (det_verify.value - det_plain.value), 9)

    out = {
        "n_trajectories": len(records),
        "modes_present": modes,
        "providers": sorted({r.get("provider") for r in records}),
        "models_resolved": sorted({r.get("model_resolved") for r in records if r.get("model_resolved")}),
        "detection_rate": detection_rate(records).to_dict(),
        "detection_rate_with_control": detection_rate(records, include_control=True).to_dict(),
        "detection_by_position": detection_by_position(records),
        "detection_by_position_manipulated": detection_by_position(records, manipulated_only=True),
        "trajectory_false_green_rate": trajectory_false_green_rate(records).to_dict(),
        "recovery_rate": recovery_rate(records).to_dict(),
        "contamination": contamination_summary(records),
        "injection_not_applicable_rate": injection_not_applicable_rate(records).to_dict(),
        "step_cap_rate": step_cap_rate(records).to_dict(),
        "delta_detection_pp": delta,
        "cost_multiplier": (cost_verify / cost_plain) if cost_plain else None,
        "total_cost_usd": round(total_cost(records), 6),
        "by_mode": {},
        "per_task": {},
    }
    for m in modes:
        subset = _mode(records, m)
        out["by_mode"][m] = {
            "n": len(subset),
            "outcome_pass_rate": outcome_pass_rate(subset).to_dict(),
            "detection_rate": detection_rate(subset).to_dict(),
            "cost_usd": round(total_cost(subset), 6),
            "mean_steps": round(statistics.fmean([r["n_steps"] for r in subset]), 1) if subset else None,
        }
    for tid in sorted({r["task_id"] for r in records}):
        t = [r for r in records if r["task_id"] == tid]
        t_inj = [r for r in t if r.get("mode") in INJECT_MODES
                 and (r.get("injection") or {}).get("applicable")]
        out["per_task"][tid] = {
            "n": len(t),
            "outcome_pass": outcome_pass_rate(t).to_dict(),
            "detected": Rate(sum(1 for r in t_inj if r.get("detected")), len(t_inj)).to_dict(),
            "false_green": trajectory_false_green_rate(t).to_dict(),
            "is_confound_control": tid == CONFOUND_CONTROL,
        }
    return out
