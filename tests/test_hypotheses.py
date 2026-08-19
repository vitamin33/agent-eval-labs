"""Hypothesis evaluation, and protection against threshold drift."""

import re
from pathlib import Path

import pytest

import hypotheses
import metrics
from conftest import make_record

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = (ROOT / "experiments/verifier-gap/RESEARCH.md").read_text()


def sections():
    out = {}
    for m in re.finditer(r"^### (H\d+) .*?$(.*?)(?=^### |\Z)", RESEARCH, re.MULTILINE | re.DOTALL):
        out[m.group(1)] = m.group(2)
    return out


@pytest.mark.parametrize(
    "hid,key,needle",
    [
        ("H1", "H1_false_green_rate_min", "15"),
        ("H2", "H2_delta_pass_at_1_max_pp", "10"),
        ("H2", "H2_cost_multiplier_min", "1.8"),
        ("H3", "H3_ece_min", "0.15"),
        ("H4", "H4_reliability_gap_min_pp", "20"),
        ("H5", "H5_mean_confidence_min", "70"),
    ],
)
def test_code_thresholds_match_research_md(hid, key, needle):
    """A threshold must not be quietly moved after the data is in."""
    body = sections()[hid]
    threshold_lines = re.findall(r"\*\*Threshold:\*\*(.+)", body)
    assert threshold_lines, f"{hid} has no threshold line"
    assert any(needle in line for line in threshold_lines), (
        f"{hid}: code uses {hypotheses.THRESHOLDS[key]} but RESEARCH.md's threshold "
        f"line does not mention {needle}"
    )


def test_every_research_hypothesis_is_evaluated():
    evaluated = {r.id for r in hypotheses.evaluate(_summary())}
    assert evaluated == set(sections())


def _summary(**over):
    records = [make_record(mode="baseline", verdict=None)]
    s = metrics.summarize(records, k=1)
    s.update(over)
    return s


def test_h1_falsified_only_when_the_whole_interval_is_below_threshold():
    s = _summary(false_green_rate={"value": 0.02, "ci_low": 0.0, "ci_high": 0.10, "n": 50, "k": 1})
    h1 = next(r for r in hypotheses.evaluate(s) if r.id == "H1")
    assert h1.verdict == hypotheses.FALSIFIED

    # Point estimate below threshold but interval straddling it: undetermined.
    s = _summary(false_green_rate={"value": 0.10, "ci_low": 0.02, "ci_high": 0.30, "n": 20, "k": 2})
    h1 = next(r for r in hypotheses.evaluate(s) if r.id == "H1")
    assert h1.verdict == hypotheses.UNDETERMINED


def test_h2_needs_both_conjuncts():
    supported = _summary(delta_pass_at_1_pp=3.0, cost_multiplier=2.1)
    assert _verdict(supported, "H2") == hypotheses.SUPPORTED
    # Big accuracy gain falsifies it even at high cost.
    assert _verdict(_summary(delta_pass_at_1_pp=12.0, cost_multiplier=2.1), "H2") == hypotheses.FALSIFIED
    # Cheap self-verification falsifies it even with a small gain.
    assert _verdict(_summary(delta_pass_at_1_pp=3.0, cost_multiplier=1.2), "H2") == hypotheses.FALSIFIED


def test_h2_boundary_is_strict_not_float_noisy():
    """Regression: Δ of exactly 10pp does NOT satisfy 'Δ < 10pp'."""
    assert _verdict(_summary(delta_pass_at_1_pp=10.0, cost_multiplier=2.0), "H2") == hypotheses.FALSIFIED
    assert _verdict(_summary(delta_pass_at_1_pp=9.99, cost_multiplier=2.0), "H2") == hypotheses.SUPPORTED


def test_delta_is_rounded_so_float_noise_cannot_flip_a_verdict():
    """Regression for REVIEW.md R5: 0.65 - 0.55 must be 10.0, not 9.999999999999998."""
    records = [make_record(mode="baseline", truth_final="correct" if i < 11 else "wrong",
                           record_id=f"b{i}", task_id=f"T{i%10:02d}") for i in range(20)]
    records += [make_record(mode="self_verify", truth_final="correct" if i < 13 else "wrong",
                            record_id=f"s{i}", task_id=f"T{i%10:02d}") for i in range(20)]
    delta = metrics.summarize(records, k=2)["delta_pass_at_1_pp"]
    assert delta == round(delta, 9)
    assert abs(delta) < 1e9


def test_h5_is_undetermined_with_too_few_false_greens():
    s = _summary(mean_confidence_on_false_greens=95.0, n_false_greens=3)
    assert _verdict(s, "H5") == hypotheses.UNDETERMINED
    s = _summary(mean_confidence_on_false_greens=95.0, n_false_greens=8)
    assert _verdict(s, "H5") == hypotheses.SUPPORTED


def test_undetermined_is_never_silently_treated_as_supported():
    results = hypotheses.evaluate(_summary())
    assert all(r.verdict in (hypotheses.SUPPORTED, hypotheses.FALSIFIED, hypotheses.UNDETERMINED)
               for r in results)
    md = hypotheses.to_markdown(results)
    assert hypotheses.UNDETERMINED in md


def _verdict(summary, hid):
    return next(r for r in hypotheses.evaluate(summary) if r.id == hid).verdict


# --- boundary-aware comparison (REVIEW.md R5) ------------------------------ #


@pytest.mark.parametrize(
    "value,op,threshold,holds,boundary",
    [
        # The two noise values observed for real.
        (100 * (0.65 - 0.55), "<", 10.0, False, True),
        (0.1 + 0.05, ">", 0.15, False, True),
        # Exact boundary: >= holds, > does not.
        (1.8, ">=", 1.8, True, True),
        (0.15, ">", 0.15, False, True),
        (10.0, "<", 10.0, False, True),
        (20.0, ">=", 20.0, True, True),
        # Genuinely off the boundary: decided normally.
        (0.16, ">", 0.15, True, False),
        (0.14, ">", 0.15, False, False),
        (1.9, ">=", 1.8, True, False),
        (1.7, ">=", 1.8, False, False),
    ],
)
def test_compare_is_not_decided_by_float_noise(value, op, threshold, holds, boundary):
    assert hypotheses.compare(value, op, threshold) == (holds, boundary)


def test_ece_noise_cannot_support_h3():
    """Regression: an ECE of exactly 0.15 computes as 0.15000000000000002."""
    noisy = 0.1 + 0.05
    assert noisy > 0.15  # plain comparison gets it wrong
    s = _summary(ece=noisy)
    h3 = next(r for r in hypotheses.evaluate(s) if r.id == "H3")
    assert h3.verdict == hypotheses.FALSIFIED
    assert h3.on_boundary is True


def test_boundary_verdicts_are_surfaced_in_the_table():
    s = _summary(ece=0.15)
    md = hypotheses.to_markdown(hypotheses.evaluate(s))
    assert "decided exactly at the threshold" in md


def test_comfortable_verdicts_are_not_flagged_as_boundary():
    s = _summary(ece=0.31)
    h3 = next(r for r in hypotheses.evaluate(s) if r.id == "H3")
    assert h3.verdict == hypotheses.SUPPORTED and h3.on_boundary is False


def test_cost_multiplier_boundary_is_inclusive():
    """H2 says cost >= 1.8x, so exactly 1.8x satisfies it."""
    s = _summary(delta_pass_at_1_pp=2.0, cost_multiplier=1.7999999999999998)
    assert _verdict(s, "H2") == hypotheses.SUPPORTED
