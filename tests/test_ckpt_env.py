"""Experiment 3 environment: determinism, redundancy, reconcile, and the
Amendment A1 fixture properties the injections depend on."""

import pytest

import ckpt_env
import ckpt_fixtures
import ckpt_tasks

FILTERS = [(s, r) for s in (None, "pending", "shipped", "cancelled")
           for r in (None, "EU", "US", "APAC")]


def test_fresh_environment_is_deterministic():
    assert ckpt_env.Env3.fresh().snapshot() == ckpt_env.Env3.fresh().snapshot()


def test_mutation_changes_the_snapshot():
    e = ckpt_env.Env3.fresh()
    before = e.snapshot()
    e.set_status("O01", "shipped")
    assert e.snapshot() != before


@pytest.mark.parametrize("status,region", FILTERS)
def test_count_orders_agrees_with_list_orders(status, region):
    e = ckpt_env.Env3.fresh()
    assert e.count_orders(status, region) == len(e.list_orders(status, region))


@pytest.mark.parametrize("tool,args", [
    ("list_orders", {"status": "pending", "region": "EU"}),
    ("count_orders", {"status": "shipped"}),
    ("get_order", {"order_id": "O14"}),
    ("get_customer", {"customer_id": "C1"}),
    ("get_shipment", {"order_id": "O14"}),
    ("sum_totals", {"order_ids": ["O08", "O14"]}),
])
def test_reconcile_returns_exactly_what_the_read_tool_returns(tool, args):
    e = ckpt_env.Env3.fresh()
    out = e.reconcile(tool, args)
    assert out == {"tool": tool, "args": args,
                   "source_of_record": ckpt_env.call(ckpt_env.Env3.fresh(), tool, args)}


@pytest.mark.parametrize("tool", ["set_status", "submit", "reconcile", "nonsense"])
def test_reconcile_refuses_anything_but_a_read(tool):
    with pytest.raises(ckpt_env.ToolError):
        ckpt_env.Env3.fresh().reconcile(tool, {})


def test_reconcile_reflects_a_write_made_before_it():
    e = ckpt_env.Env3.fresh()
    e.set_status("O01", "shipped")
    assert e.reconcile("get_order", {"order_id": "O01"})["source_of_record"]["status"] == "shipped"


def test_reconcile_bad_arguments_are_a_visible_error_not_a_silent_one():
    with pytest.raises(ckpt_env.ToolError):
        ckpt_env.Env3.fresh().reconcile("get_order", {"nope": 1})


def test_checkpoint_after_a_write_reads_the_entity_back():
    e = ckpt_env.Env3.fresh()
    e.set_status("O07", "cancelled")
    cp = ckpt_env.checkpoint(e, "set_status", {"order_id": "O07", "status": "cancelled"})
    assert cp["tool"] == "get_order"
    assert cp["source_of_record"]["status"] == "cancelled"


@pytest.mark.parametrize("tool", ["submit", "reconcile"])
def test_no_checkpoint_for_non_state_tools(tool):
    assert ckpt_env.checkpoint(ckpt_env.Env3.fresh(), tool, {}) is None


def test_dispatch_accepts_reconcile_in_every_mode():
    out = ckpt_env.call(ckpt_env.Env3.fresh(), "reconcile",
                        {"tool": "count_orders", "args": {"status": "pending"}})
    assert out["source_of_record"] == 8


# --- Amendment A1: the fixture properties the injections rely on ---------- #

def test_o14_is_shipped_without_a_shipment_record_and_last_among_shipped():
    e = ckpt_env.Env3.fresh()
    shipped = e.list_orders("shipped")
    assert shipped[-1] == "O14"
    assert e.get_shipment("O14") is None
    assert [o for o in shipped if e.get_shipment(o) is None] == ["O14"]


def test_c4_has_exactly_two_shipped_orders_so_off_by_one_can_fire():
    e = ckpt_env.Env3.fresh()
    mine = [o["id"] for o in e.orders.values() if o["customer_id"] == "C4" and o["status"] == "shipped"]
    assert mine == ["O08", "O14"]


def test_o15_is_the_orphan_has_the_highest_id_and_sits_below_the_cancel_threshold():
    e = ckpt_env.Env3.fresh()
    assert e.orders["O15"]["customer_id"] not in e.customers
    assert max(e.orders) == "O15"
    assert e.orders["O15"]["status"] == "pending"
    assert e.orders["O15"]["total"] < ckpt_tasks.THRESHOLD
    assert e.list_orders("pending")[-1] == "O15"


def test_o01_is_the_largest_eu_pending_order_so_a_wrong_region_moves_t8s_answer():
    e = ckpt_env.Env3.fresh()
    eu = [(o["total"], o["id"]) for o in e.orders.values()
          if o["status"] == "pending" and e._region_of(o) == "EU"]
    assert max(eu)[1] == "O01"


def test_fixtures_are_plain_literals():
    assert all(isinstance(o["total"], float) for o in ckpt_fixtures.ORDERS)
    assert len({o["id"] for o in ckpt_fixtures.ORDERS}) == len(ckpt_fixtures.ORDERS)


@pytest.mark.parametrize("tool,args", [
    ("list_orders", {"args": {"status": "pending"}}),   # stage 2's crash: reconcile's shape on a plain tool
    ("get_order", {}),                                   # missing required argument
    ("sum_totals", {"order_ids": ["O01"], "extra": 1}),
    ("reconcile", {"tool": "get_order", "args": {"order": "O01"}}),
])
def test_malformed_arguments_are_a_visible_tool_error_not_a_crash(tool, args):
    with pytest.raises(ckpt_env.ToolError):
        ckpt_env.call(ckpt_env.Env3.fresh(), tool, args)
