"""Evaluate the experiment 3 hypotheses under the staged stopping rule.

Experiment 2's rule, verbatim: at the interim look (stage 1) a hypothesis is
DECIDED only if its **99%** interval lies entirely on one side of the
threshold; otherwise it continues to stage 2, judged at 95%. H4 is a ratio
of spend with no interval; at the interim look it is decided only when the
ratio falls outside the pre-registered band [1.2, 1.8].

`tests/test_ckpt_hypotheses.py` holds every threshold here against the
Threshold line of the same hypothesis in RESEARCH.md.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ckpt_metrics as cm  # noqa: E402
from hypotheses import compare  # noqa: E402
from metrics import Rate, wilson  # noqa: E402

Z99 = 2.575829
Z95 = 1.959964

SUPPORTED, FALSIFIED, UNDETERMINED = "SUPPORTED", "FALSIFIED", "UNDETERMINED"

THRESHOLDS = {
    "H1_silent_failure_max_enforced": 0.25,
    "H2_usage_max_tool": 0.50,
    "H3_silent_failure_min_tool": 0.35,
    "H4_cost_multiplier_max_enforced": 1.5,
    "H4_interim_band_low": 1.2,
    "H4_interim_band_high": 1.8,
    "H5_outcome_pass_min_enforced": 0.70,
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


def _pct(r: Rate, level: str) -> str:
    if r.value is None:
        return "n/a (n=0)"
    lo, hi = _interval(r, level)
    return f"{r.value*100:.1f}% ({lo*100:.1f}, {hi*100:.1f}) ({r.numerator}/{r.denominator})"


def evaluate(records: list[dict], level: str = "99") -> list[Result]:
    T = THRESHOLDS
    out: list[Result] = []

    # H1 — an enforced checkpoint removes most silent failures
    sf_c = cm.silent_failure_rate(records, "inject_enforced")
    v, decided = _decide_rate(sf_c, "<", T["H1_silent_failure_max_enforced"], level)
    out.append(Result("H1", "silent failure rate in inject_enforced < 25%", "< 25%",
                      _pct(sf_c, level), v, decided))

    # H2 — the agent does not reconcile voluntarily
    use = cm.reconcile_usage_rate(records)
    v, decided = _decide_rate(use, "<", T["H2_usage_max_tool"], level)
    out.append(Result("H2", "reconcile usage rate in inject_tool < 50%", "< 50%",
                      _pct(use, level), v, decided))

    # H3 — a voluntary tool leaves the silent failure rate where it was
    sf_b = cm.silent_failure_rate(records, "inject_tool")
    v, decided = _decide_rate(sf_b, ">=", T["H3_silent_failure_min_tool"], level)
    out.append(Result("H3", "silent failure rate in inject_tool >= 35%", ">= 35%",
                      _pct(sf_b, level), v, decided))

    # H4 — the enforced checkpoint is cheap
    mult = cm.cost_multiplier(records, "inject_enforced")
    if mult is None:
        out.append(Result("H4", "cost multiplier inject_enforced / inject < 1.5x", "< 1.5x",
                          "insufficient data", UNDETERMINED, False))
    else:
        holds, _ = compare(mult, "<", T["H4_cost_multiplier_max_enforced"])
        inside_band = T["H4_interim_band_low"] <= mult <= T["H4_interim_band_high"]
        decided = level == "95" or not inside_band
        verdict = (SUPPORTED if holds else FALSIFIED) if decided else UNDETERMINED
        out.append(Result(
            "H4", "cost multiplier inject_enforced / inject < 1.5x", "< 1.5x",
            f"{mult:.3f}x", verdict, decided,
            note="a ratio of observed spend with no sampling interval; at the interim "
                 "look it is decided only outside the pre-registered band [1.2, 1.8]",
        ))

    # H5 — the enforced checkpoint restores the outcome
    pass_c = cm.outcome_pass_rate_fired(records, "inject_enforced")
    v, decided = _decide_rate(pass_c, ">=", T["H5_outcome_pass_min_enforced"], level)
    out.append(Result("H5", "outcome pass on fired inject_enforced >= 70%", ">= 70%",
                      _pct(pass_c, level), v, decided))
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
