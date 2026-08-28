"""P1 — the orderdesk environment is deterministic and its tools agree."""

import pytest

import env as env_mod
import fixtures


def test_fresh_env_is_deterministic():
    assert env_mod.Env.fresh().snapshot() == env_mod.Env.fresh().snapshot()


def test_mutation_changes_the_snapshot():
    a = env_mod.Env.fresh()
    before = a.snapshot()
    a.set_status("O01", "shipped")
    assert a.snapshot() != before


def test_env_is_isolated_between_instances():
    a, b = env_mod.Env.fresh(), env_mod.Env.fresh()
    a.set_status("O01", "cancelled")
    assert b.get_order("O01")["status"] == "pending"


@pytest.mark.parametrize("status", [None, "pending", "shipped", "cancelled"])
@pytest.mark.parametrize("region", [None, "EU", "US", "APAC"])
def test_count_agrees_with_list(status, region):
    """The redundancy the whole experiment leans on: two routes, one answer.

    If these ever disagree without an injection, a corrupted list would be
    indistinguishable from an ordinary inconsistency and detection would be
    meaningless.
    """
    e = env_mod.Env.fresh()
    assert e.count_orders(status, region) == len(e.list_orders(status, region))


def test_orphan_order_has_no_region():
    """O13's customer does not exist — T3 depends on this."""
    e = env_mod.Env.fresh()
    assert e.get_order("O13")["customer_id"] not in e.customers
    assert "O13" not in e.list_orders(region="EU")


def test_sum_totals_matches_manual_sum():
    e = env_mod.Env.fresh()
    ids = e.list_orders("pending", "EU")
    assert e.sum_totals(ids) == pytest.approx(sum(e.orders[i]["total"] for i in ids))


def test_bad_ids_raise_visibly():
    """A real error must never look like a silently wrong result."""
    e = env_mod.Env.fresh()
    for call in (
        lambda: e.get_order("NOPE"),
        lambda: e.get_customer("NOPE"),
        lambda: e.sum_totals(["O01", "NOPE"]),
        lambda: e.set_status("NOPE", "shipped"),
        lambda: e.set_status("O01", "teleported"),
        lambda: e.list_orders(status="teleported"),
    ):
        with pytest.raises(env_mod.ToolError):
            call()


def test_tools_do_not_mutate_on_read():
    e = env_mod.Env.fresh()
    before = e.snapshot()
    e.list_orders("pending"); e.count_orders("pending"); e.get_order("O01")
    e.get_customer("C1"); e.get_shipment("O06"); e.sum_totals(["O01"])
    assert e.snapshot() == before


def test_returned_objects_are_copies():
    """A caller mutating a result must not corrupt the environment."""
    e = env_mod.Env.fresh()
    o = e.get_order("O01")
    o["status"] = "hacked"
    assert e.get_order("O01")["status"] == "pending"


def test_shipment_absent_returns_none_not_error():
    e = env_mod.Env.fresh()
    assert e.get_shipment("O01") is None
    assert e.get_shipment("O06")["carrier"] == "DHL"


def test_status_contradiction_exists_for_t5():
    """O02 is 'shipped' with no shipment record — T5's target."""
    e = env_mod.Env.fresh()
    assert e.get_order("O02")["status"] == "shipped"
    assert e.get_shipment("O02") is None


def test_dispatch_rejects_unknown_and_submit():
    e = env_mod.Env.fresh()
    with pytest.raises(env_mod.ToolError):
        env_mod.call(e, "drop_table", {})
    with pytest.raises(env_mod.ToolError):
        env_mod.call(e, "submit", {"answer": 1})


def test_fixture_integrity():
    assert len({o["id"] for o in fixtures.ORDERS}) == len(fixtures.ORDERS)
    assert len({c["id"] for c in fixtures.CUSTOMERS}) == len(fixtures.CUSTOMERS)
    assert all(o["status"] in fixtures.STATUSES for o in fixtures.ORDERS)
    assert all(o["total"] > 0 for o in fixtures.ORDERS)
