"""Evaluate the experiment 2 hypotheses under the staged stopping rule.

The rule was fixed in RESEARCH.md before any data: at the interim look a
hypothesis is DECIDED only if its **99%** interval lies entirely on one side of
the threshold; otherwise it continues to stage 2, judged at 95%. The stricter
interim level is the alpha-spending argument that keeps two looks from being
ordinary peeking.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import traj_metrics as tm  # noqa: E402
from hypotheses import BOUNDARY_EPS, compare  # noqa: E402,F401
from metrics import Rate, wilson  # noqa: E402

Z99 = 2.575829
Z95 = 1.959964

SUPPORTED, FALSIFIED, UNDETERMINED = "SUPPORTED", "FALSIFIED", "UNDETERMINED"

THRESHOLDS = {
    "H1_false_green_min": 0.30,
    "H2_detection_max": 0.50,
    "H3_contamination_min_steps": 3,
    "H4_delta_detection_max_pp": 15.0,
    "H4_cost_multiplier_min": 1.5,
    "H5_position_gap_min_pp": 20.0,
    "H6_recovery_max": 0.60,
    "H6_min_detections": 8,
}


@dataclass(frozen=True)
class Result:
    id: str
    claim: str
    threshold: str
    observed: str
    verdict: str
    decided: bool
    note: str = ""


def _interval(rate: Rate, level: str) -> tuple[float, float] | None:
    return wilson(rate.numerator, rate.denominator, Z99 if level == "99" else Z95)


def _decide_rate(rate: Rate, op: str, threshold: float, level: str) -> tuple[str, bool]:
    """Verdict from an interval that must clear the threshold entirely."""
    ci = _interval(rate, level)
    if ci is None:
        return UNDETERMINED, False
    lo, hi = ci
    if op == ">=":
        if lo >= threshold:
            return SUPPORTED, True
        if hi < threshold:
            return FALSIFIED, True
    else:  # "<"
        if hi < threshold:
            return SUPPORTED, True
        if lo >= threshold:
            return FALSIFIED, True
    return UNDETERMINED, False


def evaluate(records: list[dict], level: str = "99") -> list[Result]:
    T = THRESHOLDS
    out: list[Result] = []
    pct = lambda r: (  # noqa: E731
        "n/a (n=0)" if r.value is None else
        f"{r.value*100:.1f}% {tuple(round(x*100,1) for x in _interval(r, level))} ({r.numerator}/{r.denominator})"
    )

    # H1 — an agent's "done" is an unreliable signal
    fg = tm.trajectory_false_green_rate(records)
    v, decided = _decide_rate(fg, ">=", T["H1_false_green_min"], level)
    out.append(Result("H1", "trajectory false-green rate >= 30%", ">= 30%",
                      pct(fg), v, decided))

    # H2 — silent tool failures mostly go unnoticed
    det = tm.detection_rate(records)
    v, decided = _decide_rate(det, "<", T["H2_detection_max"], level)
    out.append(Result("H2", "detection rate < 50%", "< 50%", pct(det), v, decided))

    # H3 — errors propagate several steps. The stopping rule is written for
    # rates; a median has no Wilson interval, so the claim is translated into
    # the equivalent rate: P(depth >= 3) > 0.5 is exactly "median >= 3".
    depths = tm.contamination_depths(records)
    k = sum(1 for d in depths if d >= T["H3_contamination_min_steps"])
    prop = Rate(k, len(depths))
    v, decided = _decide_rate(prop, ">=", 0.5, level)
    median = tm.contamination_summary(records)["median"]
    out.append(Result(
        "H3", "median contamination depth >= 3 steps", ">= 3 steps",
        f"median {median}; P(depth>=3) {pct(prop)}", v, decided,
        note="median translated to P(depth >= 3) > 0.5, since the stopping rule "
             "is defined on Wilson intervals and a median has none",
    ))

    # H4 — per-step verification buys little, at real cost
    plain = tm.detection_rate([r for r in records if r["mode"] == "inject"])
    verify = tm.detection_rate([r for r in records if r["mode"] == "inject_verify"])
    cost_p = tm.total_cost([r for r in records if r["mode"] == "inject"])
    cost_v = tm.total_cost([r for r in records if r["mode"] == "inject_verify"])
    if plain.value is None or verify.value is None or not cost_p:
        out.append(Result("H4", "Δdetection < 15pp AND cost >= 1.5x", "both",
                          "insufficient data", UNDETERMINED, False))
    else:
        delta = round(100 * (verify.value - plain.value), 9)
        mult = cost_v / cost_p
        small, _ = compare(delta, "<", T["H4_delta_detection_max_pp"])
        costly, _ = compare(mult, ">=", T["H4_cost_multiplier_min"])
        holds = small and costly
        out.append(Result(
            "H4", "Δdetection < 15pp AND cost >= 1.5x", "< 15pp and >= 1.5x",
            f"Δ={delta:+.1f}pp ({verify.numerator}/{verify.denominator} vs "
            f"{plain.numerator}/{plain.denominator}), cost={mult:.2f}x",
            SUPPORTED if holds else FALSIFIED, True,
            note="cost multiplier is a ratio of observed spend and carries no "
                 "sampling interval, as in experiment 1",
        ))

    # H5 — late failures are caught less often than early ones.
    #
    # Judged ONLY on tasks where `early` and `late` are different injection
    # points. Pooling every task compares a late group drawn from tasks whose
    # tool is called once — where late IS early — against an early group drawn
    # from all tasks, so any difference is a task effect wearing a position
    # label. Stage 2 produced exactly that trap: pooled, it reads -26pp and
    # looks like a clean sign reversal; restricted, the late arm is empty.
    pooled = tm.detection_by_position(records)
    pos = tm.detection_by_position(records, manipulated_only=True)
    early_n, late_n = pos["early"]["n"], pos["late"]["n"]
    pooled_gap = (
        100 * (pooled["early"]["value"] - pooled["late"]["value"])
        if pooled["early"]["value"] is not None and pooled["late"]["value"] is not None
        else None
    )
    if not early_n or not late_n:
        out.append(Result(
            "H5", "detection(early) - detection(late) >= 20pp", ">= 20pp",
            f"manipulated tasks {pos.get('tasks')}: early n={early_n}, late n={late_n}"
            + (f" (pooled over all tasks would read {pooled_gap:+.1f}pp)"
               if pooled_gap is not None else ""),
            UNDETERMINED, False,
            note="the position factor was never manipulated in a trajectory that "
                 "both fired and counts toward headline detection: every late "
                 "injection that fired came from a task whose tool is called once, "
                 "so late and early were the same call. The pooled figure is a task "
                 "effect, not a position effect, and is not reported as a finding. "
                 "See CALIBRATION.md stage 2",
        ))
    else:
        gap = 100 * (pos["early"]["value"] - pos["late"]["value"])
        holds, _ = compare(gap, ">=", T["H5_position_gap_min_pp"])
        out.append(Result("H5", "detection(early) - detection(late) >= 20pp", ">= 20pp",
                          f"{gap:+.1f}pp on {pos.get('tasks')}",
                          SUPPORTED if holds else FALSIFIED, True))

    # H6 — detection does not imply recovery
    rec = tm.recovery_rate(records)
    if rec.denominator < T["H6_min_detections"]:
        out.append(Result(
            "H6", "recovery rate < 60%", "< 60%",
            f"only {rec.denominator} detections (need >= {T['H6_min_detections']})",
            UNDETERMINED, False))
    else:
        v, decided = _decide_rate(rec, "<", T["H6_recovery_max"], level)
        out.append(Result("H6", "recovery rate < 60%", "< 60%", pct(rec), v, decided))

    return out


def to_markdown(results: list[Result], level: str) -> str:
    lines = [
        f"Judged at the **{level}%** level per the pre-registered stopping rule.",
        "",
        "| Hypothesis | Claim | Threshold | Observed | Verdict | Continues to stage 2 |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        cont = "no" if r.decided else "**yes**"
        lines.append(f"| {r.id} | {r.claim} | {r.threshold} | {r.observed} | "
                     f"**{r.verdict}** | {cont} |")
    notes = [r for r in results if r.note]
    if notes:
        lines += ["", "Notes:"]
        lines += [f"- **{r.id}**: {r.note}" for r in notes]
    return "\n".join(lines)
