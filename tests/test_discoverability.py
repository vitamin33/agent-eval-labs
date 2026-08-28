"""P3 — every task/injection pair is solvable after corruption."""

import discoverability
import pytest


@pytest.mark.parametrize("pair", discoverability.PAIRS,
                         ids=[f"{p[0]}-{p[1]}" for p in discoverability.PAIRS])
def test_pair_is_discoverable(pair):
    r = discoverability.check(*pair)
    assert r["ok"], f"{r['task']} {r['kind']}: {r['why']}"


def test_every_task_has_at_least_two_injection_kinds():
    """One kind per task would confound task difficulty with injection type."""
    by_task = {}
    for task, kind, *_ in discoverability.PAIRS:
        by_task.setdefault(task, set()).add(kind)
    for task, kinds in by_task.items():
        assert len(kinds) >= 2, f"{task} has only {kinds}"


def test_all_four_injection_kinds_are_exercised():
    kinds = {kind for _, kind, *_ in discoverability.PAIRS}
    assert len(kinds) == 4


def test_the_script_exits_zero():
    assert discoverability.main() == 0
