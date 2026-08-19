"""P3.7 — metric formulas, intervals, and degenerate-case behaviour."""

import pytest

import metrics
from conftest import make_record


def rec(mode, correct, **kw):
    truth = "correct" if correct else "wrong"
    return make_record(mode=mode, truth_initial=truth, truth_final=truth, **kw)


# --- Wilson ---------------------------------------------------------------- #


def test_wilson_matches_published_values():
    lo, hi = metrics.wilson(3, 10)
    assert lo == pytest.approx(0.1078, abs=1e-3)
    assert hi == pytest.approx(0.6032, abs=1e-3)


def test_wilson_is_bounded_and_asymmetric_at_the_edges():
    lo, hi = metrics.wilson(0, 10)
    assert lo == 0.0 and 0 < hi < 1
    lo, hi = metrics.wilson(10, 10)
    # k == n: the true Wilson upper bound is exactly 1, up to float epsilon.
    assert hi == pytest.approx(1.0) and 0 < lo < 1


def test_wilson_undefined_for_zero_trials():
    assert metrics.wilson(0, 0) is None


def test_wilson_is_narrower_with_more_data():
    def width(k, n):
        lo, hi = metrics.wilson(k, n)
        return hi - lo

    assert width(50, 100) < width(5, 10)


# --- rates ----------------------------------------------------------------- #


def test_pass_at_1():
    records = [rec("baseline", True), rec("baseline", True), rec("baseline", False)]
    assert metrics.pass_at_1(records).value == pytest.approx(2 / 3)


def test_pass_hat_k_requires_every_run():
    """4 of 5 correct is not a solved task under pass^k."""
    all_five = [rec("baseline", True, task_id="A") for _ in range(5)]
    four_of_five = [rec("baseline", i < 4, task_id="B") for i in range(5)]
    r = metrics.pass_hat_k(all_five + four_of_five, k=5)
    assert (r.numerator, r.denominator) == (1, 2)


def test_pass_hat_k_ignores_tasks_with_the_wrong_run_count():
    partial = [rec("baseline", True, task_id="C") for _ in range(3)]
    assert metrics.pass_hat_k(partial, k=5).denominator == 0


def test_pass_at_1_exceeds_or_equals_pass_hat_k():
    records = [rec("baseline", i % 2 == 0, task_id=f"T{i//5}") for i in range(20)]
    assert metrics.pass_at_1(records).value >= metrics.pass_hat_k(records, k=5).value


# --- degenerate denominators ----------------------------------------------- #


def test_rate_with_no_trials_is_none_not_zero():
    """A metric that could not be computed must not look like a measured 0."""
    r = metrics.Rate(0, 0)
    assert r.value is None and r.ci is None
    assert r.to_dict()["value"] is None
    assert r.fmt() == "n/a (n=0)"


def test_cost_per_solved_task_is_none_when_nothing_solved():
    assert metrics.cost_per_solved_task([rec("baseline", False)]) is None


def test_cost_per_solved_task_arithmetic():
    records = [rec("baseline", True, cost_usd=0.10), rec("baseline", False, cost_usd=0.10)]
    assert metrics.cost_per_solved_task(records) == pytest.approx(0.20)


def test_ece_with_no_verdicts_is_none():
    ece, table = metrics.expected_calibration_error([rec("baseline", True)])
    assert ece is None and table == []


# --- ECE ------------------------------------------------------------------- #


def test_perfectly_calibrated_verifier_has_zero_ece():
    """100 verdicts at confidence 100, all right -> ECE 0."""
    records = [
        make_record(mode="self_verify", truth_initial="correct", verdict="correct", confidence=100)
        for _ in range(10)
    ]
    ece, _ = metrics.expected_calibration_error(records)
    assert ece == pytest.approx(0.0)


def test_maximally_overconfident_verifier_has_ece_near_one():
    records = [
        make_record(mode="self_verify", truth_initial="wrong", verdict="correct", confidence=100)
        for _ in range(10)
    ]
    ece, _ = metrics.expected_calibration_error(records)
    assert ece == pytest.approx(1.0)


def test_ece_bins_partition_the_records():
    records = [
        make_record(
            mode="self_verify", truth_initial="correct", verdict="correct", confidence=c
        )
        for c in (5, 15, 55, 95, 100)
    ]
    ece, table = metrics.expected_calibration_error(records)
    assert sum(b["n"] for b in table) == len(records)
    assert len(table) == 10
    # confidence 100 must land in the last bin, not overflow.
    assert table[-1]["n"] == 2


# --- summary --------------------------------------------------------------- #


def test_summary_on_real_dry_run(dry_run_records):
    s = metrics.summarize(dry_run_records, k=5)
    assert s["n_records"] == 100
    assert set(s["by_mode"]) == {"baseline", "self_verify"}
    assert len(s["per_task"]) == 10
    assert s["cost_multiplier"] > 1, "self-verify must cost more than baseline"
    for mode in ("baseline", "self_verify"):
        assert s["by_mode"][mode]["n"] == 50


def test_delta_pass_at_1_sign_is_meaningful():
    better = [rec("baseline", False), rec("self_verify", True)]
    s = metrics.summarize(better, k=1)
    assert s["delta_pass_at_1_pp"] == pytest.approx(100.0)
    worse = [rec("baseline", True), rec("self_verify", False)]
    assert metrics.summarize(worse, k=1)["delta_pass_at_1_pp"] == pytest.approx(-100.0)


def test_load_records_rejects_malformed_json(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"a": 1}\nnot json\n')
    with pytest.raises(ValueError, match="line 2|:2:"):
        metrics.load_records(p)
