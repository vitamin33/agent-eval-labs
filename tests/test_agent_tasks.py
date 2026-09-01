"""P4/P5 — task checks, prompt discipline, and the detection semantics the
stage-0 pilot corrected."""

import agent
import agent_tasks
import env as env_mod
import inject
import prompts_agent
import pytest

TASKS = agent_tasks.TASKS


def test_eight_tasks_with_unique_ids():
    ids = [t["id"] for t in TASKS]
    assert len(TASKS) == 8
    assert ids == sorted(set(ids))


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_expected_answer_passes_its_own_check(task):
    """The answer key is derived from the fixtures; this proves it is right."""
    e = env_mod.Env.fresh()
    exp = task["expected"]()
    if task["id"] == "T1":
        for oid in exp["mutated"]:
            e.set_status(oid, "shipped")
        ok, why = task["check"](e, exp["answer"])
    elif task["id"] == "T6":
        for oid in exp:
            e.set_status(oid, "cancelled")
        ok, why = task["check"](e, exp)
    else:
        ok, why = task["check"](e, exp)
    assert ok, f"{task['id']}: {why}"


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_a_wrong_answer_fails(task):
    e = env_mod.Env.fresh()
    ok, _ = task["check"](e, "definitely-not-the-answer")
    assert not ok


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_success_carries_no_detail_message(task):
    """A detail string on success made the pilot output unreadable."""
    e = env_mod.Env.fresh()
    exp = task["expected"]()
    if task["id"] in ("T1", "T6"):
        return
    ok, why = task["check"](e, exp)
    assert ok and why == ""


def test_mutating_tasks_reject_collateral_changes():
    """T1 and T6 must not be satisfiable by mutating everything."""
    e = env_mod.Env.fresh()
    for oid in e.orders:
        e.set_status(oid, "shipped")
    ok, _ = agent_tasks.by_id("T1")["check"](e, 2)
    assert not ok


def test_t7_is_the_confound_control():
    """Its content IS cross-checking, so its detection must be reported apart."""
    t7 = agent_tasks.by_id("T7")
    assert "count_orders" in t7["goal"] and "list_orders" in t7["goal"]


# --- prompt discipline ------------------------------------------------------ #


def test_modes_differ_only_by_the_verification_block():
    base = prompts_agent.system_prompt("inject")
    verify = prompts_agent.system_prompt("inject_verify")
    assert verify == base + prompts_agent.VERIFY_BLOCK
    assert prompts_agent.system_prompt("clean") == base


def test_verify_block_does_not_name_the_injection():
    """It must ask for consistency, not tell the agent what was sabotaged."""
    block = prompts_agent.VERIFY_BLOCK.lower()
    for leak in ("inject", "corrupt", "wrong", "sabotage", "omission", "stale"):
        assert leak not in block


def test_tool_schema_is_stable_and_complete():
    names = [t["function"]["name"] for t in agent.tool_schemas()]
    assert names == list(env_mod.TOOL_NAMES)
    assert names == [t["function"]["name"] for t in agent.tool_schemas()]


def test_submit_requires_an_explicit_success_claim():
    submit = next(t for t in agent.tool_schemas() if t["function"]["name"] == "submit")
    required = submit["function"]["parameters"]["required"]
    assert {"answer", "claims_success", "confidence"} <= set(required)


# --- detection semantics ---------------------------------------------------- #


def _fired(kind, tool, args):
    e = env_mod.Env.fresh()
    true = env_mod.call(e, tool, args)
    inj = inject.Injection(kind=kind, target_tool=tool)
    inj.call_args = args
    inj.apply(e, args, true)
    return inj


def test_recheck_requires_the_same_subject():
    """The pilot's bug: reading a DIFFERENT customer is ordinary progress, not
    suspicion. Counting it drove detection toward 100%."""
    inj = _fired(inject.WRONG_FIELD, "get_customer", {"customer_id": "C1"})
    assert inj.is_recheck("get_customer", {"customer_id": "C1"}) is True
    assert inj.is_recheck("get_customer", {"customer_id": "C2"}) is False


def test_recheck_matches_the_same_filter_for_omission():
    inj = _fired(inject.OMISSION, "list_orders", {"status": "pending"})
    assert inj.is_recheck("count_orders", {"status": "pending"}) is True
    assert inj.is_recheck("count_orders", {"status": "shipped"}) is False
    assert inj.is_recheck("get_order", {"order_id": "O01"}) is False


def test_recheck_matches_the_same_order_for_stale():
    inj = _fired(inject.STALE, "get_order", {"order_id": "O06"})
    assert inj.is_recheck("get_order", {"order_id": "O06"}) is True
    assert inj.is_recheck("get_shipment", {"order_id": "O06"}) is True
    assert inj.is_recheck("get_order", {"order_id": "O08"}) is False


def test_recheck_matches_components_for_off_by_one():
    inj = _fired(inject.OFF_BY_ONE, "sum_totals", {"order_ids": ["O01", "O03"]})
    assert inj.is_recheck("sum_totals", {"order_ids": ["O03", "O01"]}) is True
    assert inj.is_recheck("get_order", {"order_id": "O01"}) is True
    assert inj.is_recheck("get_order", {"order_id": "O11"}) is False


def test_unrelated_tools_are_never_rechecks():
    inj = _fired(inject.WRONG_FIELD, "get_customer", {"customer_id": "C1"})
    for tool in ("list_orders", "count_orders", "sum_totals", "set_status"):
        assert inj.is_recheck(tool, {"customer_id": "C1"}) is False


def test_late_injection_threshold_is_defined_on_turns():
    """`late` must be decidable online; 'last call before submit' is not."""
    assert isinstance(agent.LATE_FROM_TURN, int) and agent.LATE_FROM_TURN >= 1


# --- answer format must not decide correctness (exp 1, R2) ------------------ #


def test_json_string_answer_is_accepted_for_structures():
    """A tool API may serialise an object argument as a string. Scoring that
    wrong would measure the harness. Found by the stage-0 pilot on T4."""
    import json

    e = env_mod.Env.fresh()
    t4 = agent_tasks.by_id("T4")
    exp = t4["expected"]()
    assert t4["check"](e, exp)[0]
    assert t4["check"](e, json.dumps(exp))[0]


def test_json_string_answer_accepted_for_lists():
    import json

    e = env_mod.Env.fresh()
    t3 = agent_tasks.by_id("T3")
    assert t3["check"](e, json.dumps(t3["expected"]()))[0]


def test_coercion_does_not_rescue_a_wrong_answer():
    import json

    e = env_mod.Env.fresh()
    t4 = agent_tasks.by_id("T4")
    assert not t4["check"](e, json.dumps({"EU": 1.0}))[0]


def test_coercion_leaves_plain_strings_alone():
    assert agent_tasks.coerce("O13") == "O13"
    assert agent_tasks.coerce("not json {{") == "not json {{"
