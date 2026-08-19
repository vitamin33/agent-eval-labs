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
        verdict = FALSIFIED if fg["ci_high"] < T["H1_false_green_rate_min"] else (
            SUPPORTED if fg["value"] >= T["H1_false_green_rate_min"] else UNDETERMINED
        )
        out.append(Result("H1", "false-green rate >= 15%", verdict,
                          f"{fg['value']:.1%} [{fg['ci_low']:.1%}, {fg['ci_high']:.1%}]",
                          f">= {T['H1_false_green_rate_min']:.0%}"))

    # H2 — small accuracy gain at large cost. Both conjuncts must hold.
    delta, mult = summary["delta_pass_at_1_pp"], summary["cost_multiplier"]
    if delta is None or mult is None:
        out.append(Result("H2", "Δpass@1 < 10pp AND cost >= 1.8x", UNDETERMINED,
                          "missing delta or cost", "both"))
    else:
        holds = delta < T["H2_delta_pass_at_1_max_pp"] and mult >= T["H2_cost_multiplier_min"]
        out.append(Result("H2", "Δpass@1 < 10pp AND cost >= 1.8x",
                          SUPPORTED if holds else FALSIFIED,
                          f"Δ={delta:+.2f}pp, cost={mult:.2f}x",
                          f"< {T['H2_delta_pass_at_1_max_pp']:.0f}pp and "
                          f">= {T['H2_cost_multiplier_min']}x"))

    # H3 — the confidence number does not track correctness.
    ece = summary["ece"]
    if ece is None:
        out.append(Result("H3", "ECE > 0.15", UNDETERMINED, "no parsed confidences",
                          f"> {T['H3_ece_min']}"))
    else:
        out.append(Result("H3", "ECE > 0.15",
                          SUPPORTED if ece > T["H3_ece_min"] else FALSIFIED,
                          f"{ece:.3f}", f"> {T['H3_ece_min']}"))

    # H4 — per-run accuracy overstates reliability.
    base = summary["by_mode"]["baseline"]
    p1, pk = base["pass_at_1"]["value"], base["pass_hat_k"]["value"]
    if p1 is None or pk is None:
        out.append(Result("H4", "baseline pass@1 − pass^k >= 20pp", UNDETERMINED,
                          "missing pass rates", f">= {T['H4_reliability_gap_min_pp']:.0f}pp"))
    else:
        gap = round(100 * (p1 - pk), 9)
        out.append(Result("H4", "baseline pass@1 − pass^k >= 20pp",
                          SUPPORTED if gap >= T["H4_reliability_gap_min_pp"] else FALSIFIED,
                          f"{gap:.2f}pp ({p1:.1%} vs {pk:.1%})",
                          f">= {T['H4_reliability_gap_min_pp']:.0f}pp"))

    # H5 — false greens arrive with high confidence.
    conf, n_fg = summary["mean_confidence_on_false_greens"], summary["n_false_greens"]
    if conf is None or n_fg < T["H5_min_false_greens"]:
        out.append(Result("H5", "mean confidence on false greens >= 70", UNDETERMINED,
                          f"only {n_fg} false greens (need >= {T['H5_min_false_greens']})",
                          f">= {T['H5_mean_confidence_min']:.0f}"))
    else:
        out.append(Result("H5", "mean confidence on false greens >= 70",
                          SUPPORTED if conf >= T["H5_mean_confidence_min"] else FALSIFIED,
                          f"{conf:.1f} (n={n_fg})", f">= {T['H5_mean_confidence_min']:.0f}"))

    return out


def to_markdown(results: list[Result]) -> str:
    lines = ["| Hypothesis | Claim | Threshold | Observed | Verdict |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.id} | {r.claim} | {r.threshold} | {r.observed} | **{r.verdict}** |")
    return "\n".join(lines)
