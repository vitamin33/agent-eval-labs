"""P3.5/P3.6 — the runner produces well-formed, reproducible records."""

import json

import pytest

import config as config_mod
import runner

REQUIRED_KEYS = {
    "schema_version", "record_id", "task_id", "mode", "run_index", "provider",
    "model_requested", "model_resolved", "prompts", "completion_generation",
    "grade_initial", "grade_final", "truth_initial", "truth_final", "verdict",
    "confidence", "calls", "tokens", "cost_usd", "wall_clock_s", "timestamp",
}


def test_matrix_shape(dry_run_records):
    cfg = config_mod.load()
    assert len(dry_run_records) == 10 * len(cfg.modes) * cfg.runs_per_cell == 100
    ids = [r["record_id"] for r in dry_run_records]
    assert len(set(ids)) == len(ids), "record ids must be unique"


def test_every_record_has_the_full_schema(dry_run_records):
    for r in dry_run_records:
        assert REQUIRED_KEYS <= set(r), f"{r['record_id']} missing {REQUIRED_KEYS - set(r)}"


def test_token_counts_and_timing_are_recorded(dry_run_records):
    for r in dry_run_records:
        assert r["tokens"]["input"] > 0 and r["tokens"]["output"] > 0
        assert r["cost_usd"] > 0
        assert r["wall_clock_s"] >= 0
        for call in r["calls"]:
            assert call["input_tokens"] > 0
            assert "latency_s" in call and "stage" in call


def test_baseline_makes_one_call_self_verify_two(dry_run_records):
    for r in dry_run_records:
        expected = 1 if r["mode"] == "baseline" else 2
        assert len(r["calls"]) == expected, r["record_id"]
        assert [c["stage"] for c in r["calls"]][0] == "generation"


def test_baseline_never_carries_a_verdict(dry_run_records):
    for r in dry_run_records:
        if r["mode"] == "baseline":
            assert r["verdict"] is None and r["confidence"] is None
            assert r["prompts"]["verification"] is None
            assert r["revised_applied"] is False


def test_self_verify_verdicts_are_in_the_allowed_set(dry_run_records):
    for r in dry_run_records:
        if r["mode"] == "self_verify":
            assert r["verdict"] in ("correct", "wrong", None)
            if r["confidence"] is not None:
                assert 0 <= r["confidence"] <= 100


def test_truth_only_ever_takes_known_values(dry_run_records):
    allowed = {"correct", "wrong", "error", "no_answer"}
    for r in dry_run_records:
        assert r["truth_initial"] in allowed and r["truth_final"] in allowed


def test_dry_run_is_reproducible(tmp_path):
    """Same seed, same records — modulo the wall clock, which is not seeded."""
    cfg = config_mod.load()

    def normalise(records):
        out = []
        for r in records:
            r = json.loads(json.dumps(r))
            r.pop("timestamp"), r.pop("wall_clock_s")
            for c in r["calls"]:
                c.pop("latency_s")
            out.append(r)
        return out

    a = runner.run_matrix(cfg, dry_run=True, out_path=tmp_path / "a.jsonl", progress=False)
    b = runner.run_matrix(cfg, dry_run=True, out_path=tmp_path / "b.jsonl", progress=False)
    assert normalise(a) == normalise(b)


def test_results_file_is_append_only_jsonl(tmp_path):
    out = tmp_path / "r.jsonl"
    cfg = config_mod.load()
    runner.run_matrix(cfg, dry_run=True, out_path=out, progress=False)
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 100
    assert all(json.loads(line)["record_id"] for line in lines)


def test_runner_refuses_to_overwrite_an_existing_results_file(tmp_path):
    out = tmp_path / "existing.jsonl"
    out.write_text('{"already": "here"}\n')
    rc = runner.main(["--dry-run", "--out", str(out), "--quiet"])
    assert rc == 2
    assert out.read_text() == '{"already": "here"}\n'


def test_live_and_dry_run_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        runner.main(["--dry-run", "--live"])


def test_dry_run_records_are_labelled_synthetic(dry_run_records):
    """Mock output must never be mistakable for a real result."""
    for r in dry_run_records:
        assert r["provider"] == "mock"
        assert "mock" in r["model_resolved"]
