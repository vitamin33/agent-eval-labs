"""The pin has to mean the served model, not just an internally consistent one.

September 2026: the config pinned `deepseek-v4-flash`, the API served
`deepseek-flash`, and every record in the run agreed with every other. The
"single resolved model" check passed while the run was not on the pinned model
at all. These tests pin the stronger invariant.
"""

import json
from pathlib import Path

import pytest
from conftest import make_record

import report

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments/verifier-gap/results"
AUG_GEN = RESULTS / "run-live-20260819T190057Z.jsonl"
SEPT_INJ = RESULTS / "run-live-inject-20260918T124004Z.jsonl"


def _records(requested, served, n=4):
    return [
        make_record(record_id=f"T01|baseline|{i}", mode="baseline", provider="deepseek",
                    model_requested=requested, model_resolved=served)
        for i in range(n)
    ]


def test_a_matching_pin_is_not_a_mismatch():
    assert report.model_mismatch(_records("deepseek-v4-flash", "deepseek-v4-flash")) is None


def test_a_served_model_other_than_the_pin_is_reported():
    out = report.model_mismatch(_records("deepseek-v4-flash", "deepseek-flash"))
    assert out == (["deepseek-v4-flash"], ["deepseek-flash"])


def test_mismatch_is_detected_even_when_the_run_is_internally_consistent():
    """Every record agrees with every other, and the run is still off the pin."""
    recs = _records("deepseek-v4-flash", "deepseek-flash", n=50)
    assert len({r["model_resolved"] for r in recs}) == 1
    assert report.model_mismatch(recs) is not None


def test_report_refuses_to_publish_an_off_pin_run(tmp_path, capsys):
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in _records("a-model", "b-model")) + "\n")
    rc = report.main([
        "--results", str(path), "--out-md", str(tmp_path / "R.md"),
        "--assets", str(tmp_path / "assets"), "--no-readme",
    ])
    assert rc == 2
    assert "refusing to publish" in capsys.readouterr().err


def test_the_override_exists_and_is_explicit(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in _records("a-model", "b-model")) + "\n")
    rc = report.main([
        "--results", str(path), "--out-md", str(tmp_path / "R.md"),
        "--assets", str(tmp_path / "assets"), "--no-readme",
        "--allow-model-mismatch",
    ])
    assert rc == 0


def test_mock_runs_are_exempt_because_they_mark_themselves(dry_run_records):
    """The mock suffixes its id on purpose; that is labelling, not a broken pin."""
    assert report.model_mismatch(dry_run_records) is None


@pytest.mark.skipif(not AUG_GEN.exists(), reason="August run not present")
def test_the_published_august_run_is_on_its_pin():
    import metrics
    assert report.model_mismatch(metrics.load_records(AUG_GEN)) is None


@pytest.mark.skipif(not SEPT_INJ.exists(), reason="September run not present")
def test_the_september_run_is_off_its_pin_and_stays_published_as_such():
    import metrics
    out = report.model_mismatch(metrics.load_records(SEPT_INJ))
    assert out == (["deepseek-v4-flash"], ["deepseek-flash"])
