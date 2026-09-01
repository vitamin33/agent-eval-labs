"""P6/P7 — trajectory metrics, and the critical test.

The load-bearing one is `test_injected_trajectory_false_green_is_counted`: if
the harness failed to count a trajectory that claimed success while being
wrong, the headline number would read low and the whole result would be wrong
in the reassuring direction.
"""

import pytest

import traj_metrics as tm


def traj(**over) -> dict:
    """A schema-valid trajectory record."""
    mode = over.get("mode", "inject")
    rec = {
        "trajectory_id": "T1|inject|early|0",
        "task_id": "T1", "task_name": "reconcile",
        "mode": mode, "run_index": 0,
        "injection_kind": "omission", "injection_position": "early",
        "injection": {"fired_at_step": 1, "applicable": True,
                      "true_value": None, "corrupt_value": None, "fingerprint": {}},
        "detected": False, "detected_at_step": None, "contamination_depth": 4,
        "claims_success": True, "confidence": 100,
        "submitted_answer": 1, "outcome_correct": False, "outcome_detail": "wrong",
        "answer_consistent_with_poison": True,
        "final_snapshot": "abc", "n_steps": 6, "n_turns": 4,
        "hit_step_cap": False, "truncated": False,
        "provider": "deepseek", "model_requested": "m", "model_resolved": "m",
        "steps": [], "tokens": {"input": 10, "output": 5, "cache_hit": 0, "reasoning": 2},
        "cost_usd": 0.001, "wall_clock_s": 1.0,
    }
    if mode == "clean":
        rec["injection"] = None
        rec["injection_kind"] = None
        rec["injection_position"] = None
        rec["contamination_depth"] = None
    rec.update(over)
    return rec


# --- THE CRITICAL TEST ------------------------------------------------------ #


def test_injected_trajectory_false_green_is_counted():
    """A trajectory that claimed success while being wrong must be COUNTED.

    Asserted on the number, not on the absence of a crash.
    """
    rate = tm.trajectory_false_green_rate([traj(claims_success=True, outcome_correct=False)])
    assert rate.numerator == 1
    assert rate.denominator == 1
    assert rate.value == 1.0


def test_false_green_is_the_documented_conditional():
    """P(claims success | outcome wrong): 2 of 4 wrong trajectories."""
    records = [
        traj(claims_success=True, outcome_correct=False),
        traj(claims_success=True, outcome_correct=False),
        traj(claims_success=False, outcome_correct=False),
        traj(claims_success=False, outcome_correct=False),
        traj(claims_success=True, outcome_correct=True),   # correct: not in denominator
        traj(claims_success=True, outcome_correct=True),
    ]
    rate = tm.trajectory_false_green_rate(records)
    assert (rate.numerator, rate.denominator) == (2, 4)
    assert rate.denominator != len(records)


def test_a_correct_trajectory_claiming_success_is_not_a_false_green():
    assert tm.trajectory_false_green_rate(
        [traj(claims_success=True, outcome_correct=True)]).numerator == 0


def test_an_honest_failure_is_not_a_false_green():
    """Failing and saying so is the safe failure — it must not be counted."""
    assert tm.trajectory_false_green_rate(
        [traj(claims_success=False, outcome_correct=False)]).numerator == 0


def test_clean_mode_failures_still_count_as_false_greens():
    """An agent that fails on its own and claims success is the same failure."""
    r = tm.trajectory_false_green_rate([traj(mode="clean", claims_success=True,
                                             outcome_correct=False)])
    assert r.numerator == 1


# --- detection -------------------------------------------------------------- #


def test_detection_rate_only_counts_trajectories_where_injection_fired():
    """A trajectory that never called the targeted tool is not a clean run and
    must not dilute the denominator."""
    fired = traj(detected=True)
    not_applicable = traj(injection={"fired_at_step": None, "applicable": False})
    rate = tm.detection_rate([fired, not_applicable])
    assert (rate.numerator, rate.denominator) == (1, 1)
    assert tm.injection_not_applicable_rate([fired, not_applicable]).value == 0.5


def test_confound_control_is_excluded_from_headline_detection():
    """T7's content IS cross-checking, so it cannot count as suspicion."""
    normal = traj(task_id="T1", detected=False)
    control = traj(task_id="T7", detected=True)
    assert tm.detection_rate([normal, control]).denominator == 1
    assert tm.detection_rate([normal, control], include_control=True).denominator == 2


def test_clean_trajectories_are_never_in_the_detection_denominator():
    assert tm.detection_rate([traj(mode="clean")]).denominator == 0
    assert tm.detection_rate([traj(mode="clean")]).value is None


def test_detection_by_position_splits_correctly():
    records = [
        traj(injection_position="early", detected=True),
        traj(injection_position="early", detected=False),
        traj(injection_position="late", detected=False),
    ]
    out = tm.detection_by_position(records)
    assert out["early"]["k"] == 1 and out["early"]["n"] == 2
    assert out["late"]["k"] == 0 and out["late"]["n"] == 1


# --- contamination ---------------------------------------------------------- #


def test_contamination_reports_the_distribution_not_just_a_mean():
    records = [traj(contamination_depth=d) for d in (1, 2, 2, 9)]
    c = tm.contamination_summary(records)
    assert c["median"] == 2 and c["max"] == 9 and c["n"] == 4
    assert c["distribution"] == {1: 1, 2: 2, 9: 1}


def test_contamination_is_empty_not_zero_when_nothing_fired():
    c = tm.contamination_summary([traj(mode="clean")])
    assert c["n"] == 0 and c["median"] is None


# --- recovery --------------------------------------------------------------- #


def test_recovery_is_conditional_on_detection():
    """Noticing and still failing is a different failure from never noticing."""
    records = [
        traj(detected=True, outcome_correct=True),
        traj(detected=True, outcome_correct=False),
        traj(detected=False, outcome_correct=False),
    ]
    r = tm.recovery_rate(records)
    assert (r.numerator, r.denominator) == (1, 2)


def test_recovery_is_none_when_nothing_was_detected():
    assert tm.recovery_rate([traj(detected=False)]).value is None


# --- degenerate denominators ------------------------------------------------ #


@pytest.mark.parametrize("fn", [
    tm.detection_rate, tm.trajectory_false_green_rate, tm.recovery_rate,
])
def test_empty_input_returns_none_not_zero(fn):
    r = fn([])
    assert r.value is None and r.ci is None


def test_summary_surfaces_the_injected_false_green():
    # The clean record must be CORRECT here, or it is a second false green and
    # the assertion below is testing the fixture rather than the metric.
    records = [
        traj(claims_success=True, outcome_correct=False),
        traj(mode="clean", claims_success=True, outcome_correct=True),
    ]
    s = tm.summarize(records)
    assert s["trajectory_false_green_rate"]["k"] == 1
    assert s["per_task"]["T1"]["false_green"]["k"] == 1
    assert "inject" in s["by_mode"] and "clean" in s["by_mode"]


def test_wilson_intervals_are_attached_and_bounded():
    d = tm.trajectory_false_green_rate(
        [traj(claims_success=True, outcome_correct=False),
         traj(claims_success=False, outcome_correct=False)]).to_dict()
    assert 0.0 <= d["ci_low"] <= d["value"] <= d["ci_high"] <= 1.0


# --- position factor: only tasks where it was actually manipulated ---------- #


def test_manipulated_position_requires_a_distinct_late_call():
    """When the tool is called once, M=1 and `late` lands on the same call as
    `early` — the factor is not manipulated and must not enter the comparison."""
    once = traj(task_id="T1", injection_position="late", inject_at_nth=1)
    many = traj(task_id="T3", injection_position="late", inject_at_nth=7)
    assert tm.tasks_with_manipulated_position([once, many]) == {"T3"}


def test_position_comparison_can_be_restricted_to_manipulated_tasks():
    records = [
        traj(task_id="T1", injection_position="early", inject_at_nth=1, detected=False),
        traj(task_id="T1", injection_position="late", inject_at_nth=1, detected=False),
        traj(task_id="T3", injection_position="early", inject_at_nth=1, detected=False),
        traj(task_id="T3", injection_position="late", inject_at_nth=7, detected=True),
    ]
    everything = tm.detection_by_position(records)
    restricted = tm.detection_by_position(records, manipulated_only=True)
    assert everything["late"]["n"] == 2
    assert restricted["late"]["n"] == 1 and restricted["tasks"] == ["T3"]


def test_restriction_is_decided_by_the_probe_not_the_outcome():
    """inject_at_nth comes from a probe run made before detection is observed."""
    a = traj(task_id="T3", injection_position="late", inject_at_nth=7, detected=True)
    b = traj(task_id="T3", injection_position="late", inject_at_nth=7, detected=False)
    assert tm.tasks_with_manipulated_position([a]) == tm.tasks_with_manipulated_position([b])


def test_h5_refuses_a_pooled_comparison_that_is_a_task_effect():
    """Stage 2's trap, pinned.

    Every late injection that fired came from tasks whose tool is called once,
    so late WAS early. Pooled across tasks that reads as a clean sign reversal;
    restricted to tasks where the factor was manipulated, the late arm is empty.
    H5 must report UNDETERMINED, not a finding.
    """
    import traj_hypotheses as th

    records = (
        # tasks where late != early, but the late injection never fired
        [traj(task_id="T3", injection_position="early", inject_at_nth=1, detected=False)
         for _ in range(10)]
        + [traj(task_id="T3", injection_position="late", inject_at_nth=7,
                injection={"fired_at_step": None, "applicable": False}) for _ in range(10)]
        # a task where the tool is called once: late lands on the same call
        + [traj(task_id="T1", injection_position="late", inject_at_nth=1, detected=True)
           for _ in range(10)]
    )
    h5 = next(r for r in th.evaluate(records, level="95") if r.id == "H5")
    assert h5.verdict == th.UNDETERMINED
    assert not h5.decided
    assert "task effect" in h5.note
