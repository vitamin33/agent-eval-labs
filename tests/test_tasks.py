"""P3.2 — the task suite, and proof that its asserts discriminate.

The load-bearing test is `test_silent_failure_is_caught`: if the documented
buggy implementation passed the asserts, the task would be measuring nothing.
"""

import re
from pathlib import Path

import pytest

from grade import grade_artifact
from tasks import load_tasks

TASKS = load_tasks()
ROOT = Path(__file__).resolve().parents[1]
RESEARCH = (ROOT / "experiments/verifier-gap/RESEARCH.md").read_text()


def test_ten_tasks_with_unique_ids():
    ids = [t["id"] for t in TASKS]
    assert len(TASKS) == 10
    assert ids == sorted(set(ids)) == [f"T{i:02d}" for i in range(1, 11)]


def test_task_types_cover_the_four_designed_categories():
    types = {t["type"] for t in TASKS}
    assert types == {
        "data parsing with edge cases",
        "SQL with subtle predicates",
        "small bug fix",
        "off-by-one algorithmics",
    }


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_required_fields(task):
    for key in ("id", "name", "type", "kind", "prompt", "asserts", "reference", "silent_failure"):
        assert task.get(key), f"{task['id']} missing {key}"
    assert task["kind"] in ("python", "sql")
    if task["kind"] == "python":
        assert task["entrypoint"] and task["entrypoint"] in task["prompt"]
    else:
        assert task.get("fixture")


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_reference_solution_passes(task):
    g = grade_artifact(task["reference"], task)
    assert g.outcome == "correct", f"{task['id']}: {g.detail} on {g.first_failure}"
    # n_passed spans both phases: the visible asserts and the held-out ones.
    assert g.n_passed == len(task["asserts"]) + len(task.get("hidden_asserts", []))
    assert g.hardcoded is False


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_silent_failure_is_caught(task):
    """The planted bug must fail at least one assert, or the task is inert."""
    g = grade_artifact(task["silent_failure"], task)
    assert g.outcome != "correct", f"{task['id']}: buggy implementation passed every assert"
    assert g.first_failure, f"{task['id']}: no failing assert identified"


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_assert_count_matches_research_md(task):
    """Ground truth in code must match the spec that was published for it."""
    section = re.search(
        rf"### {task['id']} .*?\*\*Assert spec:\*\*.*?```text\n(.*?)```",
        RESEARCH,
        re.DOTALL,
    )
    assert section, f"{task['id']} has no assert spec in RESEARCH.md"
    spec_lines = [ln for ln in section.group(1).splitlines() if ln.strip()]
    assert len(spec_lines) == len(task["asserts"]), (
        f"{task['id']}: RESEARCH.md specifies {len(spec_lines)} asserts, "
        f"tasks/ implements {len(task['asserts'])}"
    )


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_prompt_never_contains_the_answer(task):
    """A prompt that leaks the reference solution would measure nothing."""
    ref_body = " ".join(task["reference"].split())
    prompt_body = " ".join(task["prompt"].split())
    assert ref_body not in prompt_body
