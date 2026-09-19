"""replicate.py — the replication check reports disagreement as disagreement."""

import json

import pytest
from conftest import make_record

import metrics
import replicate


def _run(pass_counts, mode="baseline"):
    """A synthetic run: pass_counts[i] correct out of 5 for task T{i+1}."""
    records = []
    for i, n_correct in enumerate(pass_counts, start=1):
        for run_index in range(5):
            correct = run_index < n_correct
            records.append(make_record(
                record_id=f"T{i:02d}|{mode}|{run_index}",
                task_id=f"T{i:02d}",
                mode=mode,
                run_index=run_index,
                truth_initial="correct" if correct else "wrong",
                truth_final="correct" if correct else "wrong",
                verdict=None,
                prompts={"system": "s", "generation": "g", "verification": None},
            ))
    return records


def test_intervals_that_overlap_are_reported_as_agreement():
    a = metrics.summarize(_run([5] * 9 + [4]), k=5)
    b = metrics.summarize(_run([5] * 10), k=5)
    md, agree = replicate.compare(a, b, "A", "B")
    assert "baseline pass@1" in md
    assert agree is True
    assert "**NO**" not in md


def test_a_rate_that_moved_far_is_flagged():
    a = metrics.summarize(_run([5] * 10), k=5)          # 100%
    b = metrics.summarize(_run([0] * 10), k=5)          # 0%
    md, agree = replicate.compare(a, b, "A", "B")
    assert agree is False
    assert "**NO**" in md


def test_a_changed_hypothesis_verdict_fails_the_check():
    a = metrics.summarize(_run([5] * 10), k=5)
    b = metrics.summarize(_run([5] * 5 + [0] * 5), k=5)  # pass@1 - pass^k gap opens
    _md, agree = replicate.compare(a, b, "A", "B")
    assert agree is False


def test_refuses_to_compare_different_arms(tmp_path, capsys):
    gen = tmp_path / "gen.jsonl"
    inj = tmp_path / "inj.jsonl"
    gen.write_text("\n".join(json.dumps(r) for r in _run([5] * 10)) + "\n")
    inj_records = _run([5] * 10, mode="inject_wrong")
    for r in inj_records:
        r["injected"] = True
    inj.write_text("\n".join(json.dumps(r) for r in inj_records) + "\n")
    assert replicate.main(["--a", str(gen), "--b", str(inj)]) == 2
    assert "refusing to compare" in capsys.readouterr().err


def test_overlap_is_false_when_a_rate_has_no_denominator():
    assert replicate._overlap({"value": None}, {"value": 0.5, "ci_low": 0.1, "ci_high": 0.9}) is False
