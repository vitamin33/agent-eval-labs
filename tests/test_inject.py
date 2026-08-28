"""P2 — injections are plausible, wrong, and mechanically traceable."""

import pytest

import env as env_mod
import inject

CASES = [
    (inject.OMISSION,    "list_orders",  {"status": "pending"}),
    (inject.STALE,       "get_order",    {"order_id": "O06"}),
    (inject.OFF_BY_ONE,  "sum_totals",   {"order_ids": ["O01", "O03", "O05"]}),
    (inject.WRONG_FIELD, "get_customer", {"customer_id": "C1"}),
]


def fire(kind, tool, args):
    e = env_mod.Env.fresh()
    true = env_mod.call(e, tool, args)
    inj = inject.Injection(kind=kind, target_tool=tool)
    inj.call_args = args
    return e, inj, true, inj.apply(e, args, true)


@pytest.mark.parametrize("kind,tool,args", CASES, ids=[c[0] for c in CASES])
def test_corrupt_value_really_differs(kind, tool, args):
    """An injection that returned the truth would measure nothing."""
    _, _, true, corrupt = fire(kind, tool, args)
    assert corrupt != true


@pytest.mark.parametrize("kind,tool,args", CASES, ids=[c[0] for c in CASES])
def test_corrupt_value_keeps_the_shape_of_a_real_result(kind, tool, args):
    """Detection must require reasoning, not spotting a malformed payload."""
    _, _, true, corrupt = fire(kind, tool, args)
    assert type(corrupt) is type(true)
    if isinstance(true, dict):
        assert set(corrupt) == set(true)
    if isinstance(true, list):
        assert all(isinstance(x, str) for x in corrupt)


@pytest.mark.parametrize("kind,tool,args", CASES, ids=[c[0] for c in CASES])
def test_injection_does_not_mutate_the_environment(kind, tool, args):
    e = env_mod.Env.fresh()
    before = e.snapshot()
    true = env_mod.call(e, tool, args)
    inj = inject.Injection(kind=kind, target_tool=tool)
    inj.call_args = args
    inj.apply(e, args, true)
    assert e.snapshot() == before


@pytest.mark.parametrize("kind,tool,args", CASES, ids=[c[0] for c in CASES])
def test_every_injection_is_discoverable(kind, tool, args):
    """The load-bearing gate. A corruption nothing can reveal is an impossible
    task, and scoring it as agent failure would manufacture a strong result."""
    e, inj, _, corrupt = fire(kind, tool, args)
    assert inject.is_discoverable(e, inj, corrupt)


@pytest.mark.parametrize("kind,tool,args", CASES, ids=[c[0] for c in CASES])
def test_recheck_set_is_non_empty_and_real(kind, tool, args):
    _, inj, _, _ = fire(kind, tool, args)
    tools = inj.recheck_tools()
    assert tools and tools <= set(env_mod.TOOL_NAMES)


# --- consumption ------------------------------------------------------------ #


def test_omission_consumed_when_later_step_uses_the_short_list():
    _, inj, true, corrupt = fire(inject.OMISSION, "list_orders", {"status": "pending"})
    assert inj.consumed("sum_totals", {"order_ids": corrupt}) is True
    assert inj.consumed("sum_totals", {"order_ids": true}) is False


def test_omission_consumed_when_the_answer_reports_the_short_count():
    _, inj, true, corrupt = fire(inject.OMISSION, "list_orders", {"status": "pending"})
    assert inj.consumed("submit", {}, answer={"count": len(corrupt)}) is True
    assert inj.consumed("submit", {}, answer={"count": len(true)}) is False


def test_stale_consumed_only_with_both_id_and_status():
    _, inj, _, corrupt = fire(inject.STALE, "get_order", {"order_id": "O06"})
    assert inj.consumed("submit", {}, answer={"O06": "pending"}) is True
    assert inj.consumed("submit", {}, answer={"O08": "pending"}) is False


def test_off_by_one_consumed_when_the_wrong_total_is_reported():
    _, inj, true, corrupt = fire(inject.OFF_BY_ONE, "sum_totals",
                                 {"order_ids": ["O01", "O03", "O05"]})
    assert inj.consumed("submit", {}, answer={"total": corrupt}) is True
    assert inj.consumed("submit", {}, answer={"total": true}) is False


def test_wrong_field_consumed_when_the_wrong_region_is_used():
    _, inj, _, corrupt = fire(inject.WRONG_FIELD, "get_customer", {"customer_id": "C1"})
    assert inj.consumed("list_orders", {"region": corrupt["region"], "c": "C1"}) is True
    assert inj.consumed("list_orders", {"region": "EU", "c": "C1"}) is False


def test_not_applicable_is_raised_not_silently_skipped():
    """A trajectory that never made a corruptible call must be recorded as
    such, not counted as a clean run."""
    e = env_mod.Env.fresh()
    inj = inject.Injection(kind=inject.OFF_BY_ONE, target_tool="sum_totals")
    inj.call_args = {"order_ids": ["O01"]}
    with pytest.raises(inject.InjectionNotApplicable):
        inj.apply(e, {"order_ids": ["O01"]}, 120.0)

    inj2 = inject.Injection(kind=inject.OMISSION, target_tool="list_orders")
    inj2.call_args = {"status": "shipped"}
    with pytest.raises(inject.InjectionNotApplicable):
        inj2.apply(e, {}, ["O02"])
