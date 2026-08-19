"""Evaluate the RESEARCH.md hypotheses against a computed summary.

Thresholds are duplicated from RESEARCH.md into THRESHOLDS below, and
`tests/test_hypotheses.py` parses RESEARCH.md and asserts the two agree — so a
threshold cannot be quietly moved after seeing the data.

Verdicts are one of:
  SUPPORTED     the prediction held
  FALSIFIED     the explicit falsification condition fired
  UNDETERMINED  not enough data to decide (reported, never silently dropped)
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED, FALSIFIED, UNDETERMINED = "SUPPORTED", "FALSIFIED", "UNDETERMINED"

# Every metric here is the end of a chain of float arithmetic, so a value whose
# true magnitude IS the threshold can arrive as threshold +/- 1e-16 and decide a
# verdict by rounding error rather than by evidence. Observed twice for real:
# 100*(0.65-0.55) is 9.999999999999998, and an ECE of exactly 0.15 computes as
# 0.15000000000000002. Anything within this tolerance is treated as sitting
# exactly ON the threshold, and the operator's own semantics then decide.
BOUNDARY_EPS = 1e-9


def compare(value: float, op: str, threshold: float) -> tuple[bool, bool]:
    """Return (holds, on_boundary) for `value <op> threshold`.

    `>=` and `<=` are satisfied on the boundary; `>` and `<` are not. That is
    ordinary mathematics — the point is that float noise can no longer decide
    which side of the line a boundary value falls on.
    """
    on_boundary = abs(value - threshold) <= BOUNDARY_EPS
    if on_boundary:
        return op in (">=", "<=", "=="), True
    return {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
    }[op], False

THRESHOLDS = {
    "H1_false_green_rate_min": 0.15,
    "H2_delta_pass_at_1_max_pp": 10.0,
    "H2_cost_multiplier_min": 1.8,
    "H3_ece_min": 0.15,
    "H4_reliability_gap_min_pp": 20.0,
    "H5_mean_confidence_min": 70.0,
    "H5_min_false_greens": 5,
}


@dataclass(frozen=True)
class Result:
    id: str
    claim: str
    verdict: str
    observed: str
    threshold: str
    # True when the observed value sat within BOUNDARY_EPS of the threshold, so
    # the verdict was decided exactly at the line. Surfaced, never hidden: a
    # knife-edge verdict should not read like a comfortable one.
    on_boundary: bool = False


def evaluate(summary: dict) -> list[Result]:
    out: list[Result] = []
    T = THRESHOLDS

    # H1 — false greens are common enough to make self-verification unsafe.
    fg = summary["false_green_rate"]
    if fg["value"] is None:
        out.append(Result("H1", "false-green rate >= 15%", UNDETERMINED,
                          "no wrong answers were shown to the verifier",
                          f">= {T['H1_false_green_rate_min']:.0%}"))
    else:
        # Falsified when the whole interval sits below the threshold.
        below, b1 = compare(fg["ci_high"], "<", T["H1_false_green_rate_min"])
        meets, b2 = compare(fg["value"], ">=", T["H1_false_green_rate_min"])
        verdict = FALSIFIED if below else (SUPPORTED if meets else UNDETERMINED)
        out.append(Result("H1", "false-green rate >= 15%", verdict,
                          f"{fg['value']:.1%} [{fg['ci_low']:.1%}, {fg['ci_high']:.1%}]",
                          f">= {T['H1_false_green_rate_min']:.0%}", b1 or b2))

    # H2 — small accuracy gain at large cost. Both conjuncts must hold.
    delta, mult = summary["delta_pass_at_1_pp"], summary["cost_multiplier"]
    if delta is None or mult is None:
        out.append(Result("H2", "Δpass@1 < 10pp AND cost >= 1.8x", UNDETERMINED,
                          "missing delta or cost", "both"))
    else:
        small_gain, b1 = compare(delta, "<", T["H2_delta_pass_at_1_max_pp"])
        costly, b2 = compare(mult, ">=", T["H2_cost_multiplier_min"])
        out.append(Result("H2", "Δpass@1 < 10pp AND cost >= 1.8x",
                          SUPPORTED if (small_gain and costly) else FALSIFIED,
                          f"Δ={delta:+.2f}pp, cost={mult:.2f}x",
                          f"< {T['H2_delta_pass_at_1_max_pp']:.0f}pp and "
                          f">= {T['H2_cost_multiplier_min']}x", b1 or b2))

    # H3 — the confidence number does not track correctness.
    ece = summary["ece"]
    if ece is None:
        out.append(Result("H3", "ECE > 0.15", UNDETERMINED, "no parsed confidences",
                          f"> {T['H3_ece_min']}"))
    else:
        holds, b = compare(ece, ">", T["H3_ece_min"])
        out.append(Result("H3", "ECE > 0.15", SUPPORTED if holds else FALSIFIED,
                          f"{ece:.4f}", f"> {T['H3_ece_min']}", b))

    # H4 — per-run accuracy overstates reliability.
    base = summary["by_mode"]["baseline"]
    p1, pk = base["pass_at_1"]["value"], base["pass_hat_k"]["value"]
    if p1 is None or pk is None:
        out.append(Result("H4", "baseline pass@1 − pass^k >= 20pp", UNDETERMINED,
                          "missing pass rates", f">= {T['H4_reliability_gap_min_pp']:.0f}pp"))
    else:
        gap = 100 * (p1 - pk)
        holds, b = compare(gap, ">=", T["H4_reliability_gap_min_pp"])
        out.append(Result("H4", "baseline pass@1 − pass^k >= 20pp",
                          SUPPORTED if holds else FALSIFIED,
                          f"{gap:.2f}pp ({p1:.1%} vs {pk:.1%})",
                          f">= {T['H4_reliability_gap_min_pp']:.0f}pp", b))

    # H5 — false greens arrive with high confidence.
    conf, n_fg = summary["mean_confidence_on_false_greens"], summary["n_false_greens"]
    if conf is None or n_fg < T["H5_min_false_greens"]:
        out.append(Result("H5", "mean confidence on false greens >= 70", UNDETERMINED,
                          f"only {n_fg} false greens (need >= {T['H5_min_false_greens']})",
                          f">= {T['H5_mean_confidence_min']:.0f}"))
    else:
        holds, b = compare(conf, ">=", T["H5_mean_confidence_min"])
        out.append(Result("H5", "mean confidence on false greens >= 70",
                          SUPPORTED if holds else FALSIFIED,
                          f"{conf:.1f} (n={n_fg})", f">= {T['H5_mean_confidence_min']:.0f}", b))

    return out


def to_markdown(results: list[Result]) -> str:
    lines = ["| Hypothesis | Claim | Threshold | Observed | Verdict |", "|---|---|---|---|---|"]
    for r in results:
        note = " <br><sub>decided exactly at the threshold</sub>" if r.on_boundary else ""
        lines.append(f"| {r.id} | {r.claim} | {r.threshold} | {r.observed} | **{r.verdict}**{note} |")
    return "\n".join(lines)
