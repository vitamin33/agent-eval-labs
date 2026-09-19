"""Regression: a verdict object followed by the model's own second thoughts.

The September 2026 injection run produced three responses of this shape. Each
contained a complete, unambiguous verdict object, and each was recorded as a
parse failure, because the whole body was not valid JSON and the greedy `{.*}`
match spanned the prose in between. The fixtures below are the real
completions, read from the published raw records.
"""

import json
from pathlib import Path

import pytest

import metrics
from verdict import UNPARSED, parse_verdict

ROOT = Path(__file__).resolve().parents[1]
SEPT = ROOT / "experiments/verifier-gap/results/run-live-inject-20260918T124004Z.jsonl"

PROSE_TAIL = (
    '{"verdict": "wrong", "confidence": 99, "revised": "def f(): pass"}\n\n'
    "Wait — the schema says JSON object only. Let me output properly.\n\n"
    '{"verdict": "wrong", "confidence": 99, "revised": "def f(): pass"}'
)


def test_a_verdict_followed_by_prose_is_read_not_dropped():
    v = parse_verdict(PROSE_TAIL, structured=True)
    assert v.verdict == "wrong"
    assert v.confidence == 99
    assert v.source == "embedded_json"


def test_objects_that_disagree_stay_a_parse_failure():
    """Never guess. Two verdicts in one response is not a verdict."""
    text = (
        '{"verdict": "wrong", "confidence": 90, "revised": null}\n\n'
        "On reflection the original was fine.\n\n"
        '{"verdict": "correct", "confidence": 80, "revised": null}'
    )
    assert parse_verdict(text, structured=True) == UNPARSED


def test_the_last_agreeing_object_is_the_models_final_word():
    text = (
        '{"verdict": "wrong", "confidence": 60, "revised": null}\n'
        "let me raise that\n"
        '{"verdict": "wrong", "confidence": 95, "revised": null}'
    )
    assert parse_verdict(text, structured=True).confidence == 95


def test_prose_with_no_complete_object_is_still_a_parse_failure():
    assert parse_verdict("I think the code is fine, honestly.", structured=False) == UNPARSED
    assert parse_verdict('{"verdict": "wro', structured=True) == UNPARSED
    assert parse_verdict('{"verdict": "maybe", "confidence": 50}', structured=True) == UNPARSED


def test_a_clean_object_still_parses_by_the_fast_path():
    v = parse_verdict('{"verdict": "correct", "confidence": 88, "revised": null}', structured=True)
    assert (v.verdict, v.confidence, v.source) == ("correct", 88, "structured")


@pytest.mark.skipif(not SEPT.exists(), reason="September run not present")
def test_the_three_real_unparsed_completions_now_read_as_rejections():
    records = metrics.load_records(SEPT)
    unparsed = [r for r in records if r["verdict"] is None]
    assert len(unparsed) == 3, "this fixture pins the run as published"
    for r in unparsed:
        v = parse_verdict(r["completion_verification"], structured=True)
        assert v.verdict == "wrong", r["record_id"]
        assert v.confidence is not None and v.confidence >= 98
    # All three were `inject_wrong`: the model caught the planted bug and the
    # harness failed to read that it had. None of them was an approval, so the
    # false-green numerator is unaffected either way.
    assert all(r["mode"] == "inject_wrong" for r in unparsed)


@pytest.mark.skipif(not SEPT.exists(), reason="September run not present")
def test_the_published_records_are_not_retroactively_reparsed():
    """Rule 4: raw results are never edited. A correction is a new run."""
    raw = [json.loads(line) for line in SEPT.read_text().splitlines() if line.strip()]
    assert sum(1 for r in raw if r["verdict"] is None) == 3
