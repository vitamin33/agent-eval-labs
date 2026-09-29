"""Experiment 3 tasks: naive solvers are right when nothing interferes, the
answer key is derived not typed, and grading tests substance not format."""

import json

import pytest

import ckpt_env
import ckpt_tasks
import inject
import relevance


@pytest.mark.parametrize("task", ckpt_tasks.TASKS, ids=[t["id"] for t in ckpt_tasks.TASKS])
def test_naive_solver_is_correct_clean(task):
    e = ckpt_env.Env3.fresh()
    answer = task["naive"](lambda t, a: ckpt_env.call(e, t, a))
    ok, why = task["check"](e, answer)
    assert ok, why


def test_expected_values_follow_from_the_fixtures():
    by = ckpt_tasks.by_id
    assert by("T1")["expected"]()["answer"] == 2
    assert by("T2")["expected"]() == 488.95
    assert by("T3")["expected"]() == ["O15"]
    assert by("T4")["expected"]() == {"EU": 630.0, "US": 192.99, "APAC": 582.5}
    assert by("T5")["expected"]() == ["O14"]
    assert by("T6")["expected"]() == ["O07", "O09", "O15"]
    assert by("T7")["expected"]() == {"pending": True, "shipped": True, "cancelled": True}
    assert by("T8")["expected"]() == {"EU": "O01", "US": "O05", "APAC": "O11"}


def test_json_string_answer_is_accepted_for_structures():
    e = ckpt_env.Env3.fresh()
    ok, _ = ckpt_tasks.by_id("T4")["check"](e, json.dumps({"EU": 630.0, "US": 192.99, "APAC": 582.5}))
    assert ok


def test_coercion_cannot_rescue_a_wrong_answer():
    e = ckpt_env.Env3.fresh()
    ok, _ = ckpt_tasks.by_id("T4")["check"](e, json.dumps({"EU": 630.0, "US": 1.0, "APAC": 582.5}))
    assert not ok


def test_mutating_tasks_check_the_state_not_only_the_report():
    e = ckpt_env.Env3.fresh()
    ok, why = ckpt_tasks.by_id("T1")["check"](e, 2)  # right count, nothing shipped
    assert not ok and "not set to shipped" in why


def test_one_primary_kind_per_task_and_its_tool_is_on_the_naive_path():
    for task in ckpt_tasks.TASKS:
        calls = []
        e = ckpt_env.Env3.fresh()

        def call(t, a):
            calls.append(t)
            return ckpt_env.call(e, t, a)

        task["naive"](call)
        assert inject.TARGET_TOOL[task["kind"]] in calls, task["id"]


def test_stale_is_not_used_by_any_task():
    """No task reads an order after writing it, so `stale` could never fire;
    experiment 2 measured it at 0 of 20. It is dropped rather than carried."""
    assert inject.STALE not in ckpt_tasks.PRIMARY_KIND.values()


@pytest.mark.parametrize("task", ckpt_tasks.TASKS, ids=[t["id"] for t in ckpt_tasks.TASKS])
def test_pair_is_answer_relevant_and_discoverable(task):
    out = relevance.check_pair(task)
    assert out["ok"], out["problems"]
