"""The modes differ ONLY by the declared intervention.

`inject_tool` = `inject` + one tool definition; `inject_enforced` = `inject`
+ one system-prompt block. Anything else would confound every comparison in
the experiment with wording rather than with the checkpoint.
"""

import json

import ckpt_prompts
import ckpt_tasks
import prompts_agent

MODES = ("clean", "inject", "inject_tool", "inject_enforced")


def test_base_system_prompt_is_experiment_2s_not_a_copy():
    assert ckpt_prompts.BASE_SYSTEM is prompts_agent.BASE_SYSTEM


def test_three_modes_share_one_system_prompt():
    assert (ckpt_prompts.system_prompt("clean") == ckpt_prompts.system_prompt("inject")
            == ckpt_prompts.system_prompt("inject_tool") == ckpt_prompts.BASE_SYSTEM)


def test_enforced_prompt_residue_is_exactly_the_checkpoint_block():
    base = ckpt_prompts.system_prompt("inject")
    enforced = ckpt_prompts.system_prompt("inject_enforced")
    assert enforced.startswith(base)
    assert enforced[len(base):] == ckpt_prompts.CHECKPOINT_BLOCK


def test_tool_mode_residue_is_exactly_the_reconcile_tool():
    base = ckpt_prompts.tool_schemas("inject")
    tool = ckpt_prompts.tool_schemas("inject_tool")
    assert len(tool) == len(base) + 1
    assert [t for t in tool if t["function"]["name"] != "reconcile"] == base
    assert [t for t in tool if t["function"]["name"] == "reconcile"] == [ckpt_prompts.RECONCILE_TOOL]
    assert tool[-1]["function"]["name"] == "submit"


def test_enforced_and_clean_tool_lists_equal_the_baseline():
    base = ckpt_prompts.tool_schemas("inject")
    assert ckpt_prompts.tool_schemas("inject_enforced") == base
    assert ckpt_prompts.tool_schemas("clean") == base


def test_task_prompts_do_not_depend_on_mode():
    for task in ckpt_tasks.TASKS:
        assert ckpt_prompts.task_prompt(task) == ckpt_prompts.task_prompt(task)
        assert task["goal"] in ckpt_prompts.task_prompt(task)


def test_nothing_in_the_intervention_names_the_sabotage():
    """A block or a description that mentions what was corrupted would turn
    detection into reading comprehension."""
    text = (ckpt_prompts.CHECKPOINT_BLOCK + json.dumps(ckpt_prompts.RECONCILE_TOOL)).lower()
    for word in ("omission", "off_by_one", "off-by-one", "wrong_field", "corrupt", "inject",
                 "sabotag", "poison", "dropped", "stale"):
        assert word not in text, word


def test_every_mode_is_accepted_and_nothing_else():
    for m in MODES:
        ckpt_prompts.system_prompt(m)
        ckpt_prompts.tool_schemas(m)
