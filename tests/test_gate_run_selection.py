"""G4 judges the publishable run, and can never hide the ones it skipped.

Before September 2026 the gate simply took the newest results file. That is
wrong in both directions: a newer run served by a different model would be
judged as if it were the result, and — once the gate learned to reject it —
an older good run could be quietly re-promoted with nothing saying why.
"""

import json

import pytest
from conftest import make_record

import gates


def _write(path, requested, served, n=4, provider="deepseek"):
    recs = [
        make_record(record_id=f"T01|baseline|{i}", mode="baseline", provider=provider,
                    model_requested=requested, model_resolved=served)
        for i in range(n)
    ]
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return path


def test_a_run_on_its_pin_is_not_off_pin(tmp_path):
    p = _write(tmp_path / "a.jsonl", "m", "m")
    assert gates.served_off_pin(gates.read_records(p)) is False


def test_a_renamed_model_is_off_pin(tmp_path):
    p = _write(tmp_path / "a.jsonl", "deepseek-v4-flash", "deepseek-flash")
    assert gates.served_off_pin(gates.read_records(p)) is True


def test_mock_records_do_not_count_as_off_pin(tmp_path):
    p = _write(tmp_path / "a.jsonl", "m", "m-mock", provider="mock")
    assert gates.served_off_pin(gates.read_records(p)) is False


def test_split_puts_the_newest_on_pin_run_last(tmp_path):
    good_old = _write(tmp_path / "run-live-1.jsonl", "m", "m")
    bad_new = _write(tmp_path / "run-live-3.jsonl", "m", "other")
    good_new = _write(tmp_path / "run-live-2.jsonl", "m", "m")
    on, off = gates.split_by_pin([good_old, good_new, bad_new])
    assert on == [good_old, good_new]
    assert on[-1] == good_new
    assert off == [bad_new]


def test_an_unreadable_file_is_treated_as_unpublishable(tmp_path):
    broken = tmp_path / "run-live-x.jsonl"
    broken.write_text("not json\n")
    on, off = gates.split_by_pin([broken])
    assert on == [] and off == [broken]


@pytest.mark.skipif(not gates.live_result_files(), reason="no live runs present")
def test_the_gate_names_every_off_pin_run_it_skipped():
    """The skipped runs appear in the gate's own output, by filename."""
    _on, off = gates.split_by_pin(gates.live_result_files())
    names = [c.name for c in gates.gate_g4()]
    for f in off:
        assert any(f.name in n for n in names), f"{f.name} was skipped without being named"


@pytest.mark.skipif(not gates.live_result_files(), reason="no live runs present")
def test_the_gate_fails_when_no_run_is_on_the_pin(monkeypatch):
    monkeypatch.setattr(gates, "split_by_pin", lambda files: ([], list(files)))
    failed = [c for c in gates.gate_g4() if not c.ok]
    assert any("on the pinned model exists" in c.name for c in failed)
