"""P3.3 — answer extraction, including the shapes that could fake a result.

Every case here is a way the harness could silently produce a wrong grade:
a refusal read as code, a fragment read as a solution, or an empty string
executed as a no-op that happens to define nothing.
"""

import pytest

from extract import extract_python, extract_sql

ENTRY = "solve"
GOOD = "def solve(x):\n    return x + 1\n"


def test_fenced_python():
    e = extract_python(f"```python\n{GOOD}```", ENTRY)
    assert e.found and "def solve" in e.code


def test_fence_without_language():
    e = extract_python(f"```\n{GOOD}```", ENTRY)
    assert e.found and "def solve" in e.code


def test_prose_before_and_after_the_fence():
    text = f"Sure! Here it is:\n\n```python\n{GOOD}```\n\nLet me know if you need tests."
    e = extract_python(text, ENTRY)
    assert e.found
    assert "Sure!" not in e.code and "Let me know" not in e.code


def test_multiple_fences_takes_the_last_defining_one():
    """A 'before/after' answer must be graded on the after."""
    before = "def solve(x):\n    return x  # buggy\n"
    text = f"The bug:\n```python\n{before}```\nFixed:\n```python\n{GOOD}```"
    e = extract_python(text, ENTRY)
    assert "x + 1" in e.code and "# buggy" not in e.code


def test_unterminated_fence_still_yields_the_body():
    """max_tokens truncation is common; a truncated answer is still an answer."""
    e = extract_python(f"```python\n{GOOD}", ENTRY)
    assert e.found and "def solve" in e.code


def test_unfenced_code():
    e = extract_python(GOOD, ENTRY)
    assert e.found and e.reason.startswith("unfenced")


def test_refusal_returns_none_not_empty_string():
    """The critical case: `None` grades as no_answer; `''` would exec cleanly."""
    e = extract_python("I can't help with that request.", ENTRY)
    assert e.code is None
    assert e.reason == "refusal"


@pytest.mark.parametrize("text", ["", "   \n\n ", "Sure, happy to help!"])
def test_no_code_returns_none(text):
    assert extract_python(text, ENTRY).code is None


def test_fenced_prose_without_the_entrypoint_is_flagged():
    """Returned so the grader errors on a missing entrypoint, with a reason."""
    e = extract_python("```python\nprint('hello')\n```", ENTRY)
    assert e.found
    assert "no `def solve`" in e.reason


def test_sql_fenced():
    e = extract_sql("```sql\nSELECT 1;\n```")
    assert e.found and e.code.startswith("SELECT")


def test_sql_unfenced_strips_prose_on_both_sides():
    e = extract_sql("You can use this query:\nSELECT name FROM t;\nThat covers it.")
    assert e.code == "SELECT name FROM t;"


def test_sql_with_cte():
    assert extract_sql("```sql\nWITH x AS (SELECT 1) SELECT * FROM x;\n```").found


def test_sql_refusal():
    e = extract_sql("I'm unable to write that query.")
    assert e.code is None and e.reason == "refusal"
