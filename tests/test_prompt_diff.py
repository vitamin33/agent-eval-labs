"""P3.9 — the two modes differ ONLY by the verification block.

If the modes' generation prompts differ in any other way, every comparison in
this experiment is confounded: a Δpass@1 could come from better wording rather
than from self-verification. This test reconstructs one mode's request from the
other's and asserts the residue is exactly VERIFICATION_BLOCK.
"""

import difflib

import prompts
from tasks import load_tasks

TASKS = load_tasks()


def _baseline_messages(task):
    return prompts.generation_messages(task)


def _self_verify_messages(task, answer="ANSWER"):
    return prompts.verification_messages(task, answer)


def test_generation_prompt_is_byte_identical_across_modes():
    for task in TASKS:
        base = _baseline_messages(task)
        sv = _self_verify_messages(task)
        assert base == sv[: len(base)], f"{task['id']}: generation turn differs between modes"


def test_system_prompt_is_shared():
    """One SYSTEM constant, used by both modes — nothing to diverge."""
    assert prompts.SYSTEM
    assert "verif" not in prompts.SYSTEM.lower()


def test_self_verify_adds_exactly_two_turns():
    for task in TASKS:
        base = _baseline_messages(task)
        sv = _self_verify_messages(task)
        assert len(sv) == len(base) + 2
        assert sv[-2]["role"] == "assistant"
        assert sv[-1] == {"role": "user", "content": prompts.VERIFICATION_BLOCK}


def test_baseline_is_recoverable_by_deleting_the_verification_block():
    """Strip the assistant echo and the verification turn -> baseline, exactly."""
    for task in TASKS:
        sv = _self_verify_messages(task)
        reconstructed = sv[:-2]
        assert reconstructed == _baseline_messages(task)


def test_textual_diff_contains_only_the_verification_block():
    """Line-level check: every line self-verify adds comes from the block."""
    task = TASKS[0]
    base_text = "\n".join(m["content"] for m in _baseline_messages(task))
    sv_text = "\n".join(m["content"] for m in _self_verify_messages(task, answer="ANSWER"))

    added = [
        line[2:]
        for line in difflib.ndiff(base_text.splitlines(), sv_text.splitlines())
        if line.startswith("+ ")
    ]
    allowed = set(prompts.VERIFICATION_BLOCK.splitlines()) | {"ANSWER"}
    unexpected = [line for line in added if line not in allowed]
    assert not unexpected, f"self-verify adds lines outside the verification block: {unexpected}"

    removed = [
        line for line in difflib.ndiff(base_text.splitlines(), sv_text.splitlines())
        if line.startswith("- ")
    ]
    assert not removed, f"self-verify removes content from the baseline prompt: {removed}"


def test_verification_block_asks_for_the_structured_verdict():
    block = prompts.VERIFICATION_BLOCK
    for token in ('"verdict"', '"confidence"', '"revised"', "correct", "wrong"):
        assert token in block


def test_recorded_prompts_match_across_modes(dry_run_records):
    """The same check, against what was actually written to the results file."""
    by_key = {}
    for r in dry_run_records:
        by_key.setdefault(r["task_id"], {})[r["mode"]] = r

    for task_id, modes in by_key.items():
        base, sv = modes["baseline"], modes["self_verify"]
        assert base["prompts"]["generation"] == sv["prompts"]["generation"], task_id
        assert base["prompts"]["system"] == sv["prompts"]["system"], task_id
        assert base["prompts"]["verification"] is None, task_id
        assert sv["prompts"]["verification"] == prompts.VERIFICATION_BLOCK, task_id
