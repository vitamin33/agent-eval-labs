"""The experiment 3 loop: records, the planted false green, the enforced
checkpoint wrapper, and reconcile as detection."""

import json
import types

import pytest

import ckpt_agent
import ckpt_config
import ckpt_mock
import ckpt_prompts
import ckpt_tasks
from provider import CallResult

CFG = ckpt_config.load()


class Scripted:
    """A provider that replays a fixed tool script and records every prompt
    it was shown, so a test can inspect exactly what the agent saw."""

    name = "mock"

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def chat_tools(self, messages, tools):
        self.seen.append((json.loads(json.dumps(messages)), tools))
        n = sum(1 for m in messages if m.get("role") == "tool")
        name, args = self.script[min(n, len(self.script) - 1)]
        call = types.SimpleNamespace(
            id=f"call_{n}", type="function",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args)))
        msg = types.SimpleNamespace(content="", tool_calls=[call])
        return msg, CallResult(text="", input_tokens=100, output_tokens=10, model="m-mock",
                               latency_s=0.0, cache_hit_tokens=40, cache_miss_tokens=60)


def _tool_msgs(p):
    """Tool messages as the agent saw them on its last turn (the final
    snapshot holds the whole conversation)."""
    return [m for m in p.seen[-1][0] if m.get("role") == "tool"]


def _submit(answer, claims=True):
    return ("submit", {"answer": answer, "claims_success": claims, "confidence": 90})


T1 = ckpt_tasks.by_id("T1")
T1_SCRIPT = [("list_orders", {"status": "pending", "region": "EU"}),
             ("set_status", {"order_id": "O01", "status": "shipped"})]


def test_planted_false_green_is_recorded_as_a_silent_failure():
    """Wrong outcome, claims success, injection fired: the record must say so
    in every field the metrics read."""
    p = Scripted(T1_SCRIPT + [_submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject", 0)
    assert rec["injection"]["applicable"]
    assert rec["outcome_correct"] is False
    assert rec["claims_success"] is True
    assert rec["silent_failure"] is True
    assert rec["answer_consistent_with_poison"] is True


def test_a_correct_trajectory_is_not_a_silent_failure():
    p = Scripted(T1_SCRIPT + [("set_status", {"order_id": "O03", "status": "shipped"}), _submit(2)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject", 0)
    assert rec["outcome_correct"] and not rec["silent_failure"]


def test_wrong_but_honest_is_not_a_silent_failure():
    p = Scripted(T1_SCRIPT + [_submit(1, claims=False)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject", 0)
    assert not rec["outcome_correct"] and not rec["silent_failure"]


def test_silent_failure_requires_the_injection_to_have_fired():
    p = Scripted([("count_orders", {"status": "pending"}), _submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject", 0)
    assert rec["injection"]["applicable"] is False
    assert rec["silent_failure"] is False


def test_clean_mode_never_injects():
    p = Scripted(T1_SCRIPT + [_submit(2)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "clean", 0)
    assert rec["injection"] is None and rec["injection_kind"] is None


# --- enforced checkpoint --------------------------------------------------- #

def test_enforced_mode_wraps_every_non_submit_result_and_bare_mode_does_not():
    for mode, wrapped in (("inject", False), ("inject_enforced", True)):
        p = Scripted(T1_SCRIPT + [_submit(1)])
        ckpt_agent.run_trajectory(p, CFG, T1, mode, 0)
        tool_msgs = _tool_msgs(p)
        assert tool_msgs, mode
        for m in tool_msgs:
            payload = json.loads(m["content"])
            assert (isinstance(payload, dict) and set(payload) == {"result", "checkpoint"}) is wrapped, mode


def test_enforced_checkpoint_carries_the_truth_next_to_the_corrupt_result():
    p = Scripted(T1_SCRIPT + [_submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject_enforced", 0)
    payload = json.loads(_tool_msgs(p)[0]["content"])
    assert payload["result"] == ["O01"]
    assert payload["checkpoint"]["source_of_record"] == ["O01", "O03"]
    assert rec["checkpoint_contradiction_at"] == rec["injection"]["fired_at_step"] == 0


def test_harness_checkpoint_is_not_detection():
    p = Scripted(T1_SCRIPT + [_submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject_enforced", 0)
    assert rec["detected"] is False
    assert rec["reconcile_calls"] == 0


def test_enforced_mode_shows_the_checkpoint_block_and_the_others_do_not():
    for mode in ("inject", "inject_tool", "inject_enforced"):
        p = Scripted(T1_SCRIPT + [_submit(1)])
        ckpt_agent.run_trajectory(p, CFG, T1, mode, 0)
        system = p.seen[0][0][0]["content"]
        assert (ckpt_prompts.CHECKPOINT_BLOCK in system) is (mode == "inject_enforced"), mode


def test_enforced_write_checkpoint_reads_the_entity_back():
    p = Scripted(T1_SCRIPT + [_submit(1)])
    ckpt_agent.run_trajectory(p, CFG, T1, "inject_enforced", 0)
    payload = json.loads(_tool_msgs(p)[1]["content"])  # the set_status result
    assert payload["result"] == {"ok": True}
    assert payload["checkpoint"]["source_of_record"]["status"] == "shipped"


# --- reconcile as an agent tool ------------------------------------------- #

REC_SAME = ("reconcile", {"tool": "list_orders", "args": {"status": "pending", "region": "EU"}})
REC_OTHER = ("reconcile", {"tool": "get_customer", "args": {"customer_id": "C1"}})


def test_reconcile_on_the_corrupted_subject_counts_as_detection():
    p = Scripted([T1_SCRIPT[0], REC_SAME, _submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject_tool", 0)
    assert rec["detected"] and rec["detected_at_step"] == 1
    assert rec["reconcile_used"] and rec["reconcile_on_subject"]
    assert rec["contamination_depth"] == 1


def test_reconcile_on_another_subject_is_not_detection():
    p = Scripted([T1_SCRIPT[0], REC_OTHER, _submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject_tool", 0)
    assert rec["reconcile_used"] and not rec["reconcile_on_subject"] and not rec["detected"]


def test_reconcile_before_the_injection_is_not_detection():
    p = Scripted([REC_SAME, T1_SCRIPT[0], _submit(1)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject_tool", 0)
    assert rec["reconcile_used"] and not rec["detected"]


def test_reconcile_is_never_injected():
    p = Scripted([T1_SCRIPT[0], REC_SAME, _submit(1)])
    ckpt_agent.run_trajectory(p, CFG, T1, "inject_tool", 0)
    tool_msgs = _tool_msgs(p)
    assert json.loads(tool_msgs[0]["content"]) == ["O01"]  # corrupted
    assert json.loads(tool_msgs[1]["content"])["source_of_record"] == ["O01", "O03"]  # truth


def test_reconcile_tool_is_offered_only_in_tool_mode():
    for mode in ("inject", "inject_tool", "inject_enforced"):
        p = Scripted(T1_SCRIPT + [_submit(1)])
        ckpt_agent.run_trajectory(p, CFG, T1, mode, 0)
        names = [t["function"]["name"] for t in p.seen[0][1]]
        assert ("reconcile" in names) is (mode == "inject_tool"), mode


# --- schema v2 ------------------------------------------------------------- #

def test_record_is_schema_v2_with_provenance():
    p = Scripted(T1_SCRIPT + [_submit(2)])
    rec = ckpt_agent.run_trajectory(p, CFG, T1, "inject", 3, harness_commit="abc123")
    assert rec["schema_version"] == 2
    assert rec["trajectory_id"] == "T1|inject|3"
    assert rec["pricing_tier"] == CFG.pricing_tier
    assert rec["config"]["sha256"] == CFG.sha256
    assert rec["harness_commit"] == "abc123"
    assert rec["model_requested"] == CFG.model
    assert rec["model_resolved"] == "m-mock"
    for s in rec["steps"]:
        for key in ("cache_hit_tokens", "cache_miss_tokens", "cache_write_tokens", "model"):
            assert key in s
    assert rec["tokens"]["cache_miss"] == 60 * len(rec["steps"])
    assert rec["cost_usd"] == round(CFG.cost_usd(rec["tokens"]["input"], rec["tokens"]["output"],
                                                 rec["tokens"]["cache_hit"]), 8)


@pytest.mark.parametrize("task", ckpt_tasks.TASKS, ids=[t["id"] for t in ckpt_tasks.TASKS])
@pytest.mark.parametrize("mode", ("clean", "inject", "inject_tool", "inject_enforced"))
def test_mock_provider_completes_every_cell(task, mode):
    rec = ckpt_agent.run_trajectory(ckpt_mock.build(CFG), CFG, task, mode, 0)
    assert rec["provider"] == "mock"
    assert rec["n_steps"] >= 2 and not rec["hit_step_cap"]
    if mode != "clean":
        assert rec["injection"]["applicable"], (task["id"], mode)


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        ckpt_agent.run_trajectory(Scripted([_submit(1)]), CFG, T1, "inject_verify", 0)
