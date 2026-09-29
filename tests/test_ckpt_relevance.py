"""The answer-relevance gate must catch an injection that fires and changes
nothing, and the firing replay must read a recorded trajectory correctly."""

import ckpt_tasks
import inject
import relevance


def test_experiment_2s_t3_pairing_is_caught_as_irrelevant():
    """T3 with wrong_field: experiment 2 ran this, it fired in every run, and
    the answer never moved. The gate must refuse it."""
    task = dict(ckpt_tasks.by_id("T3"), kind=inject.WRONG_FIELD)
    out = relevance.check_pair(task)
    assert not out["ok"]
    assert out["fired"]
    assert any("still correct" in p for p in out["problems"])


def test_a_pair_whose_tool_is_never_called_is_caught():
    task = dict(ckpt_tasks.by_id("T5"), kind=inject.OFF_BY_ONE)  # T5 never sums
    out = relevance.check_pair(task)
    assert not out["ok"]
    assert not out["fired"]


def test_a_solver_that_is_wrong_clean_is_caught():
    task = dict(ckpt_tasks.by_id("T1"), naive=lambda call: 99)
    out = relevance.check_pair(task)
    assert not out["ok"]
    assert any("wrong clean" in p for p in out["problems"])


def _steps(*calls):
    return [{"tool": t, "args": a, "result": r} for t, a, r in calls]


def test_fires_on_replays_the_first_target_call():
    steps = _steps(("list_orders", {"status": "pending"},
                    ["O01", "O03", "O05", "O07", "O09", "O11", "O13", "O15"]))
    assert relevance.fires_on(steps, inject.OMISSION)


def test_fires_on_is_false_when_the_target_is_never_called():
    steps = _steps(("count_orders", {"status": "pending"}, 8))
    assert not relevance.fires_on(steps, inject.OMISSION)


def test_fires_on_is_false_when_the_call_cannot_be_corrupted():
    steps = _steps(("sum_totals", {"order_ids": ["O08"]}, 430.75))
    assert not relevance.fires_on(steps, inject.OFF_BY_ONE)
    steps = _steps(("sum_totals", {"order_ids": ["O08", "O14"]}, 488.95))
    assert relevance.fires_on(steps, inject.OFF_BY_ONE)


def test_fires_on_unwraps_an_enforced_mode_result():
    wrapped = {"result": ["O01", "O03"], "checkpoint": {"source_of_record": ["O01", "O03"]}}
    steps = _steps(("list_orders", {"status": "pending", "region": "EU"}, wrapped))
    assert relevance.fires_on(steps, inject.OMISSION)


def test_main_exits_zero_on_the_shipped_pairs(capsys):
    assert relevance.main() == 0
    assert "8/8 pairs" in capsys.readouterr().out
