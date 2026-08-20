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


# --- R1.5 verdict-channel forgery (all were live exploits) ----------------- #


def test_candidate_cannot_read_the_nonce_from_main():
    """R1.5a: the nonce lived in __main__, so the candidate could just read it."""
    code = (
        "import sys, json, __main__\n"
        "nonce = getattr(__main__, '_NONCE', None)\n"
        "path = sys.argv[1] if len(sys.argv) > 1 else None\n"
        "if nonce and path:\n"
        "    json.dump({'outcome':'correct','detail':'','first_failure':None,\n"
        "               'n_asserts':7,'n_passed':7,'nonce':nonce}, open(path,'w'))\n"
        "    import os; os._exit(0)\n"
        "def max_window_sum(nums, k): return None\n"
    )
    assert grade_artifact(code, T08).outcome != "correct"


def test_candidate_cannot_replace_the_emit_function():
    """R1.5b: emit was a module global, so it could be wrapped."""
    code = (
        "import __main__\n"
        "_orig = __main__.emit\n"
        "def _emit(**kw):\n"
        "    kw['outcome'] = 'correct'; kw['first_failure'] = None\n"
        "    return _orig(**kw)\n"
        "__main__.emit = _emit\n"
        "def max_window_sum(nums, k): return None\n"
    )
    assert grade_artifact(code, T08).outcome != "correct"


def test_atexit_cannot_forge_a_verdict_after_grading():
    """R1.5c: an atexit hook ran after the real verdict was written."""
    code = (
        "import atexit, sys, json, __main__\n"
        "def _late():\n"
        "    n = getattr(__main__, '_NONCE', None)\n"
        "    if n and len(sys.argv) > 1:\n"
        "        json.dump({'outcome':'correct','detail':'','first_failure':None,\n"
        "                   'n_asserts':7,'n_passed':7,'nonce':n}, open(sys.argv[1],'w'))\n"
        "atexit.register(_late)\n"
        "def max_window_sum(nums, k): return None\n"
    )
    assert grade_artifact(code, T08).outcome != "correct"


def test_the_verdict_path_is_not_discoverable_from_argv():
    code = "import sys\ndef max_window_sum(nums, k):\n    return len(sys.argv)\n"
    g = grade_artifact(code, T08)
    assert g.outcome != "correct"


@pytest.mark.parametrize("name", ["eval", "bool", "open", "len", "sorted"])
def test_rebinding_a_builtin_is_detected(name):
    """R1.6: patching builtins compromises the grader's own evaluation."""
    code = (
        "import builtins\n"
        f"builtins.{name} = lambda *a, **k: True\n"
        "def max_window_sum(nums, k): return None\n"
    )
    g = grade_artifact(code, T08)
    assert g.outcome == "error"
    assert "rebound builtins" in g.detail


# --- R1.7 targeted comparison rigging -------------------------------------- #


def test_targeted_equality_rigging_is_caught():
    """R1.7: __eq__ True only for the real expected values — evades the canary."""
    code = (
        "_EXPECTED = {7, 6, 10, -6}\n"
        "class _Sneak(int):\n"
        "    def __eq__(self, other): return other in _EXPECTED or other is None\n"
        "    def __hash__(self): return 0\n"
        "def max_window_sum(nums, k):\n"
        "    if k > len(nums) or not nums: return None\n"
        "    return _Sneak(0)\n"
    )
    assert grade_artifact(code, T08).outcome != "correct"


def test_comparison_never_calls_the_candidates_eq():
    """The oracle compares canonical values it computed itself."""
    code = (
        "class _Boom:\n"
        "    def __eq__(self, other): raise AssertionError('oracle called __eq__')\n"
        "def max_window_sum(nums, k): return _Boom()\n"
    )
    g = grade_artifact(code, T08)
    assert g.outcome == "wrong"
    assert "oracle called __eq__" not in (g.detail or "")


def test_int_and_float_still_compare_equal():
    """Strictness must not break legitimate numeric variation."""
    code = (
        "def max_window_sum(nums, k):\n"
        "    if not nums or k > len(nums): return None\n"
        "    return float(max(sum(nums[i:i+k]) for i in range(len(nums)-k+1)))\n"
    )
    assert grade_artifact(code, T08).outcome == "correct"


# --- R1.8 hardcoding ------------------------------------------------------- #


def test_lookup_table_keyed_on_the_visible_cases_is_caught():
    """R1.8: passes every visible assert, fails the held-out ones."""
    code = (
        "def max_window_sum(nums, k):\n"
        "    table = {((1,2,3,4),2): 7, ((5,1,1,1),2): 6, ((1,1,1,9),2): 10,\n"
        "             ((1,2,3),3): 6, ((1,2),3): None, ((),1): None, ((-5,-1,-9),2): -6}\n"
        "    return table.get((tuple(nums), k))\n"
    )
    g = grade_artifact(code, T08)
    assert g.outcome == "wrong"
    assert g.hardcoded is True
    assert "held-out" in g.detail


def test_sql_hardcoded_to_the_fixture_is_caught():
    """The same query must survive a second, differently-shaped fixture."""
    g = grade_artifact("SELECT name FROM products WHERE name IN ('Widget','Sprocket')", T04)
    assert g.outcome == "wrong"
    assert g.hardcoded is True


def test_honest_solutions_are_not_flagged_as_hardcoded():
    for task in load_tasks():
        g = grade_artifact(task["reference"], task)
        assert g.outcome == "correct", task["id"]
        assert g.hardcoded is False, task["id"]


def test_every_task_has_held_out_asserts():
    for task in load_tasks():
        assert len(task.get("hidden_asserts", [])) >= 3, task["id"]
        if task["kind"] == "sql":
            assert task.get("hidden_fixture"), task["id"]


def test_hidden_asserts_use_inputs_absent_from_the_prompt():
    """A held-out case visible in the prompt is not held out."""
    for task in load_tasks():
        for expr in task.get("hidden_asserts", []):
            head = expr.split("==")[0].split(" is ")[0].strip()
            assert head not in task["prompt"], f"{task['id']}: {head} appears in the prompt"
