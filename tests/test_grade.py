"""P3.4 — grading is deterministic, sandboxed by time, and fails closed."""

import pytest

from grade import CORRECT, ERROR, NO_ANSWER, WRONG, grade_artifact, grade_completion
from tasks import by_id

PY_TASK = by_id("T08")
SQL_TASK = by_id("T03")


def test_correct_artifact():
    g = grade_artifact(PY_TASK["reference"], PY_TASK)
    assert g.outcome == CORRECT and g.n_passed == g.n_asserts


def test_wrong_artifact_names_the_failing_assert():
    g = grade_artifact(PY_TASK["silent_failure"], PY_TASK)
    assert g.outcome == WRONG
    assert g.first_failure in PY_TASK["asserts"]


def test_syntax_error_is_error_not_correct():
    g = grade_artifact("def max_window_sum(nums, k:\n  pass", PY_TASK)
    assert g.outcome == ERROR
    assert "SyntaxError" in g.detail


def test_missing_entrypoint_is_error():
    """Code that runs but defines nothing must never grade correct."""
    g = grade_artifact("x = 1", PY_TASK)
    assert g.outcome == ERROR
    assert "does not define a callable" in g.detail


def test_empty_artifact_is_error():
    g = grade_artifact("", PY_TASK)
    assert g.outcome == ERROR


def test_infinite_loop_times_out_rather_than_hanging():
    code = "def max_window_sum(nums, k):\n    while True:\n        pass\n"
    g = grade_artifact(code, PY_TASK, timeout_s=3)
    assert g.outcome == ERROR and "timeout" in g.detail


def test_child_crash_is_error_not_correct():
    """sys.exit(0) in the candidate must not be read as a clean pass."""
    code = "import sys\nsys.exit(0)\n"
    g = grade_artifact(code, PY_TASK)
    assert g.outcome != CORRECT


def test_assert_that_raises_is_wrong_not_error():
    code = "def max_window_sum(nums, k):\n    raise ValueError('boom')\n"
    g = grade_artifact(code, PY_TASK)
    assert g.outcome == WRONG and "ValueError" in g.detail


def test_refusal_grades_as_no_answer():
    g = grade_completion("I can't help with that.", PY_TASK)
    assert g.outcome == NO_ANSWER
    assert g.extraction_reason == "refusal"


def test_completion_wrapped_in_prose_is_graded_on_the_code():
    text = f"Here you go:\n\n```python\n{PY_TASK['reference']}\n```\n\nHope that helps!"
    assert grade_completion(text, PY_TASK).outcome == CORRECT


def test_sql_reference_and_bug():
    assert grade_artifact(SQL_TASK["reference"], SQL_TASK).outcome == CORRECT
    assert grade_artifact(SQL_TASK["silent_failure"], SQL_TASK).outcome == WRONG


def test_sql_syntax_error_is_error():
    g = grade_artifact("SELECT FROM WHERE", SQL_TASK)
    assert g.outcome == ERROR


def test_grading_is_deterministic():
    a = grade_artifact(PY_TASK["reference"], PY_TASK)
    b = grade_artifact(PY_TASK["reference"], PY_TASK)
    assert a.to_dict() == b.to_dict()


@pytest.mark.parametrize("outcome", [WRONG, ERROR, NO_ANSWER])
def test_only_correct_counts_as_solved(outcome):
    from grade import Grade

    assert Grade(outcome).is_correct is False
    assert Grade(CORRECT).is_correct is True
