"""Experiment 3 metrics: honest denominators, the planted false green, cost
ratios, and a summary that renders from a dry run."""

import pytest

import ckpt_metrics as cm
import ckpt_runner


def rec(mode="inject", task="T1", fired=True, ok=False, claims=True, detected=False,
        cost=0.01, reconcile_used=False, on_subject=False, depth=None, steps=None, run=0):
    injected = mode != "clean"
    return {
        "trajectory_id": f"{task}|{mode}|{run}", "task_id": task, "mode": mode, "run_index": run,
        "injection": {"applicable": fired} if injected else None,
        "outcome_correct": ok, "claims_success": claims,
        "silent_failure": bool(injected and fired and not ok and claims),
        "detected": detected, "contamination_depth": depth,
        "reconcile_used": reconcile_used, "reconcile_on_subject": on_subject,
        "cost_usd": cost, "n_steps": 5, "hit_step_cap": False, "truncated": False,
        "steps": steps or [{"tool": "list_orders", "args": {}}],
        "tokens": {"input": 10, "output": 5, "cache_hit": 4, "cache_miss": 6, "reasoning": 1},
        "provider": "mock", "model_requested": "m", "model_resolved": "m",
    }


def test_planted_false_green_is_counted_once():
    assert cm.silent_failure_rate([rec()]).to_dict()["k"] == 1


def test_silent_failure_needs_wrong_and_claimed_and_fired():
    recs = [rec(ok=True), rec(claims=False), rec(fired=False), rec()]
    r = cm.silent_failure_rate(recs)
    assert (r.numerator, r.denominator) == (1, 3)  # the unfired one is not in the denominator


def test_silent_failure_rate_is_per_mode():
    recs = [rec(mode="inject"), rec(mode="inject_enforced", ok=True)]
    assert cm.silent_failure_rate(recs, "inject").value == 1.0
    assert cm.silent_failure_rate(recs, "inject_enforced").value == 0.0
    assert cm.silent_failure_rate(recs, "clean").value is None


def test_false_green_is_conditional_on_wrong_and_includes_clean():
    recs = [rec(mode="clean", ok=False, claims=True), rec(ok=False, claims=False), rec(ok=True)]
    r = cm.false_green_rate(recs)
    assert (r.numerator, r.denominator) == (1, 2)


def test_detection_excludes_the_confound_control_unless_asked():
    recs = [rec(task="T7", detected=True), rec(task="T1", detected=False)]
    assert cm.detection_rate(recs).to_dict()["n"] == 1
    assert cm.detection_rate(recs, include_control=True).to_dict()["k"] == 1


def test_detection_only_counts_trajectories_where_the_injection_fired():
    recs = [rec(fired=False, detected=True), rec(detected=True)]
    assert cm.detection_rate(recs).to_dict() == pytest.approx(
        {"value": 1.0, "n": 1, "k": 1, "ci_low": cm.detection_rate(recs).ci[0],
         "ci_high": cm.detection_rate(recs).ci[1]})


def test_reconcile_usage_is_over_every_tool_mode_trajectory():
    recs = [rec(mode="inject_tool", reconcile_used=True), rec(mode="inject_tool", fired=False),
            rec(mode="inject", reconcile_used=True)]
    r = cm.reconcile_usage_rate(recs)
    assert (r.numerator, r.denominator) == (1, 2)


def test_cost_multiplier_is_a_ratio_of_means():
    recs = [rec(mode="inject", cost=0.01), rec(mode="inject", cost=0.01, run=1),
            rec(mode="inject_enforced", cost=0.015)]
    assert cm.cost_multiplier(recs, "inject_enforced") == pytest.approx(1.5)
    assert cm.cost_multiplier(recs, "inject") == pytest.approx(1.0)
    assert cm.cost_multiplier([rec(mode="inject_enforced")], "inject_enforced") is None


def test_cost_per_avoided_silent_failure():
    recs = [rec(mode="inject", cost=0.010), rec(mode="inject", cost=0.010, run=1),
            rec(mode="inject_enforced", cost=0.014, ok=True),
            rec(mode="inject_enforced", cost=0.014, ok=True, run=1)]
    # rate 1.0 -> 0.0, extra cost 0.004 per trajectory: $0.004 per avoided failure
    assert cm.cost_per_avoided_silent_failure(recs, "inject_enforced") == pytest.approx(0.004)
    none = [rec(mode="inject"), rec(mode="inject_tool", cost=0.02)]
    assert cm.cost_per_avoided_silent_failure(none, "inject_tool") is None


def test_contamination_excludes_control_and_unfired():
    recs = [rec(depth=3), rec(task="T7", depth=9), rec(fired=False, depth=1), rec(depth=None)]
    assert cm.contamination_depths(recs) == [3]
    assert cm.contamination_summary([])["median"] is None


def test_variation_counts_cells_whose_repeats_differ():
    a = rec(steps=[{"tool": "a", "args": {}}]); b = rec(run=1, steps=[{"tool": "b", "args": {}}])
    c = rec(task="T2", run=0); d = rec(task="T2", run=1)
    v = cm.distinct_trajectories_per_cell([a, b, c, d])
    assert v["cells_with_repeats"] == 2 and v["cells_with_variation"] == 1


@pytest.fixture(scope="module")
def dry_records(tmp_path_factory):
    out = tmp_path_factory.mktemp("dry") / "run.jsonl"
    assert ckpt_runner.main(["--dry-run", "--stage", "1", "--out", str(out), "--quiet"]) == 0
    return cm.load(out)


def test_dry_run_has_the_full_stage_1_matrix(dry_records):
    assert len(dry_records) == 64
    assert {r["mode"] for r in dry_records} == set(cm.MODES)
    assert all(r["provider"] == "mock" for r in dry_records)


def test_summary_renders_from_a_dry_run(dry_records):
    s = cm.summarize(dry_records)
    assert s["n_trajectories"] == 64
    assert set(s["by_mode"]) == set(cm.MODES)
    assert s["by_mode"]["inject_enforced"]["cost_multiplier"] is not None
    assert s["injection_not_applicable_rate"]["k"] == 0
    assert s["by_mode"]["inject_tool"]["silent_failure_rate"]["n"] == 16


def test_runner_refuses_to_append_to_an_existing_file(tmp_path):
    out = tmp_path / "run.jsonl"
    out.write_text("{}\n")
    assert ckpt_runner.main(["--dry-run", "--stage", "0", "--out", str(out), "--quiet"]) == 2
