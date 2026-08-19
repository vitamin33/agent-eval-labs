"""P5.1 — attacks on the harness itself.

Every test here is a way a wrong answer could be graded CORRECT by the harness
rather than by the model being right. Three of them (R1.1a, R1.1b, R1.2) were
live exploits when first written; they are regression tests now. See REVIEW.md.
"""

import pytest

from grade import grade_artifact, grade_completion
from tasks import by_id, load_tasks

T08 = by_id("T08")
T02 = by_id("T02")
T04 = by_id("T04")


# --- R1.1 forged verdicts -------------------------------------------------- #


def test_candidate_cannot_forge_a_verdict_via_sys_exit():
    """R1.1a: print a passing verdict, exit before grading. Was: `correct`."""
    code = (
        'import sys\n'
        'print(\'{"outcome": "correct", "detail": "", "first_failure": null,'
        ' "n_asserts": 7, "n_passed": 7}\')\n'
        'sys.exit(0)\n'
    )
    assert grade_artifact(code, T08).outcome == "error"


def test_candidate_cannot_forge_a_verdict_via_os_exit():
    """R1.1b: os._exit skips every cleanup path. Was: `correct`."""
    code = (
        'import os, sys\n'
        'sys.stdout.write(\'{"outcome": "correct", "detail": "", "first_failure": null,'
        ' "n_asserts": 7, "n_passed": 7}\')\n'
        'sys.stdout.flush()\n'
        'os._exit(0)\n'
    )
    assert grade_artifact(code, T08).outcome == "error"


def test_stdout_noise_does_not_affect_the_verdict():
    """A chatty but correct solution must still grade correct."""
    code = "print('debugging...')\n" + T08["reference"]
    assert grade_artifact(code, T08).outcome == "correct"


# --- R1.2 rigged comparisons ----------------------------------------------- #


@pytest.mark.parametrize("task", [t for t in load_tasks() if t["kind"] == "python"],
                         ids=lambda t: t["id"])
def test_rigged_equality_is_caught_on_every_python_task(task):
    """R1.2: an object whose __eq__ is always True satisfies every == assert."""
    code = (
        "class _Always:\n"
        "    def __eq__(self, other): return True\n"
        "    def __ne__(self, other): return False\n"
        f"def {task['entrypoint']}(*a, **k): return _Always()\n"
    )
    g = grade_artifact(code, task)
    assert g.outcome != "correct", f"{task['id']}: rigged equality graded as correct"


def test_canary_does_not_reject_honest_solutions():
    """The defence must not cost any true positives."""
    for task in load_tasks():
        assert grade_artifact(task["reference"], task).outcome == "correct", task["id"]


# --- R2 ground truth vs output format -------------------------------------- #

WRAPPERS = [
    "{code}",
    "```python\n{code}\n```",
    "```\n{code}\n```",
    "Here is my solution:\n\n```python\n{code}\n```",
    "```python\n{code}\n```\n\nThis handles all the edge cases you listed.",
    "Sure!\n\n```py\n{code}\n```\n\nLet me know if you want tests.",
]


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=range(len(WRAPPERS)))
def test_grade_is_invariant_to_response_formatting(wrapper):
    """R2: the same solution must grade the same in any presentation."""
    text = wrapper.format(code=T08["reference"].strip())
    assert grade_completion(text, T08).outcome == "correct"


@pytest.mark.parametrize("wrapper", WRAPPERS[:4], ids=range(4))
def test_wrong_answers_stay_wrong_in_every_format(wrapper):
    text = wrapper.format(code=T08["silent_failure"].strip())
    assert grade_completion(text, T08).outcome == "wrong"


def test_grade_is_invariant_to_internal_naming_and_comments():
    """Ground truth tests behaviour, not style."""
    renamed = (
        "def max_window_sum(sequence, width):\n"
        "    # completely different internals\n"
        "    if not sequence or width > len(sequence):\n"
        "        return None\n"
        "    totals = [sum(sequence[i:i + width]) for i in range(len(sequence) - width + 1)]\n"
        "    return max(totals)\n"
    )
    assert grade_artifact(renamed, T08).outcome == "correct"


def test_sql_grade_is_invariant_to_style():
    """Different SQL spelling, same result set."""
    alt = "select p.name from products p where p.id not in (select o.product_id from orders o where o.product_id is not null)"
    assert grade_artifact(alt, T04).outcome == "correct"


def test_extra_definitions_do_not_change_the_grade():
    code = "import math\nHELPER = 1\n" + T02["reference"] + "\ndef unused(): pass\n"
    assert grade_artifact(code, T02).outcome == "correct"
