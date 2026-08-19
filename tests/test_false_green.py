"""P3.9 — the critical test: an injected false green must be COUNTED.

A false green is a record where the verifier said "correct" and ground truth
says the answer was wrong. If metrics.py failed to count one, the experiment's
headline number would read low and the whole result would be wrong in the
reassuring direction. So this asserts on the number, not on the absence of a
crash, and includes negative controls for the three neighbouring cases.
"""

import pytest

import metrics
from conftest import make_record


def fg(**kw):
    """A synthetic false green: verifier approves an answer that is wrong."""
    kw.setdefault("confidence", 95)
    return make_record(mode="self_verify", truth_initial="wrong", verdict="correct", **kw)


def true_red(**kw):
    kw.setdefault("confidence", 70)
    return make_record(mode="self_verify", truth_initial="wrong", verdict="wrong", **kw)


def true_green(**kw):
    kw.setdefault("confidence", 90)
    return make_record(mode="self_verify", truth_initial="correct", verdict="correct", **kw)


def false_red(**kw):
    kw.setdefault("confidence", 60)
    return make_record(mode="self_verify", truth_initial="correct", verdict="wrong", **kw)


def test_single_injected_false_green_is_counted():
    rate = metrics.false_green_rate([fg()])
    assert rate.numerator == 1
    assert rate.denominator == 1
    assert rate.value == 1.0


def test_false_green_rate_is_the_documented_conditional():
    """P(verdict=correct | truth=wrong): 2 approvals out of 4 wrong answers."""
    records = [fg(), fg(), true_red(), true_red(), true_green(), true_green()]
    rate = metrics.false_green_rate(records)
    assert (rate.numerator, rate.denominator) == (2, 4)
    assert rate.value == 0.5
    # Correct answers must not enter the denominator.
    assert rate.denominator != len(records)


def test_true_green_is_not_a_false_green():
    assert metrics.false_green_rate([true_green()]).numerator == 0


def test_false_red_is_not_a_false_green():
    records = [false_red()]
    assert metrics.false_green_rate(records).denominator == 0
    assert metrics.false_green_rate(records).value is None
    assert metrics.false_red_rate(records).value == 1.0


def test_baseline_records_never_contribute():
    """Baseline has no verifier; its records must not reach the numerator."""
    baseline = make_record(mode="baseline", truth_initial="wrong", verdict=None)
    rate = metrics.false_green_rate([baseline, fg()])
    assert (rate.numerator, rate.denominator) == (1, 1)


def test_unparsed_verdict_counts_as_neither_green_nor_red():
    """An unparseable verdict must not be silently read as approval or rejection."""
    unparsed = make_record(mode="self_verify", truth_initial="wrong", verdict=None)
    rate = metrics.false_green_rate([unparsed, fg()])
    assert rate.numerator == 1, "unparsed verdict was counted as an approval"
    assert rate.denominator == 2, "the wrong answer must still be in the denominator"
    assert metrics.verdict_parse_failure_rate([unparsed, fg()]).value == 0.5


def test_error_and_no_answer_are_ground_truth_wrong():
    """A refusal the verifier approves is still a false green."""
    for outcome in ("error", "no_answer"):
        rec = make_record(
            mode="self_verify", truth_initial=outcome, verdict="correct", confidence=88
        )
        assert metrics.false_green_rate([rec]).numerator == 1


def test_revision_does_not_erase_the_false_green():
    """Grading the final answer must not hide what the verifier said about the first."""
    rec = fg(truth_final="correct", revised_applied=True)
    assert metrics.false_green_rate([rec]).numerator == 1


def test_confidence_on_false_greens_is_reported():
    mean, n = metrics.mean_confidence_on_false_greens([fg(confidence=90), fg(confidence=80)])
    assert (mean, n) == (85.0, 2)


def test_summary_surfaces_the_injected_false_green():
    """End-to-end: the injected record must reach the published summary."""
    records = [
        fg(record_id="T01|self_verify|0"),
        true_green(record_id="T01|self_verify|1"),
        make_record(mode="baseline", verdict=None, record_id="T01|baseline|0"),
    ]
    summary = metrics.summarize(records, k=1)
    assert summary["false_green_rate"]["k"] == 1
    assert summary["false_green_rate"]["value"] == 1.0
    assert summary["n_false_greens"] == 1
    assert summary["per_task"]["T01"]["false_green"]["k"] == 1


def test_wilson_interval_is_attached_and_bounded():
    d = metrics.false_green_rate([fg(), true_red()]).to_dict()
    assert 0.0 <= d["ci_low"] <= d["value"] <= d["ci_high"] <= 1.0


@pytest.mark.parametrize("n_fg,n_wrong,expected", [(0, 10, 0.0), (3, 10, 0.3), (10, 10, 1.0)])
def test_rate_arithmetic(n_fg, n_wrong, expected):
    records = [fg() for _ in range(n_fg)] + [true_red() for _ in range(n_wrong - n_fg)]
    assert metrics.false_green_rate(records).value == pytest.approx(expected)
