"""usage.py — per-call export and cost accounting are derived, checked, and honest."""

import csv
import json
from pathlib import Path

import pytest
from conftest import make_record

import config as config_mod
import metrics
import usage

ROOT = Path(__file__).resolve().parents[1]
LIVE_GEN = ROOT / "experiments/verifier-gap/results/run-live-20260819T190057Z.jsonl"
LIVE_INJ = ROOT / "experiments/verifier-gap/results/run-live-inject-20260820T082818Z.jsonl"

RATES = {"tier": "peak", "input_cache_miss_per_mtok": 0.44,
         "input_cache_hit_per_mtok": 0.014, "output_per_mtok": 1.32}


def _rec(**kw):
    r = make_record(**kw)
    return r


def test_one_row_per_call_with_the_record_context(dry_run_records):
    rows = usage.flatten_calls(dry_run_records, RATES)
    assert len(rows) == sum(len(r["calls"]) for r in dry_run_records)
    by_id = {}
    for row in rows:
        by_id.setdefault(row["record_id"], []).append(row)
    for r in dry_run_records:
        mine = by_id[r["record_id"]]
        assert [m["stage"] for m in mine] == [c["stage"] for c in r["calls"]]
        assert all(m["verdict"] == r["verdict"] and m["truth_initial"] == r["truth_initial"]
                   for m in mine)
        assert all(m["mode"] == r["mode"] and m["run_index"] == r["run_index"] for m in mine)


def test_v2_records_carry_per_call_cost_and_cache_fields(dry_run_records):
    for r in dry_run_records:
        assert r["schema_version"] == 2
        assert r["max_tokens"] > 0
        assert r["pricing"]["tier"] in ("peak", "off_peak")
        assert len(r["config"]["sha256"]) == 64
        for c in r["calls"]:
            assert c["cost_usd"] > 0
            assert c["cache_miss_tokens"] + c["cache_hit_tokens"] == c["input_tokens"]
            assert "cache_write_tokens" in c
        assert set(r["tokens"]) >= {"input", "output", "cache_hit", "cache_miss", "cache_write", "reasoning"}


def test_per_call_costs_sum_to_the_record_cost(dry_run_records):
    rows = usage.flatten_calls(dry_run_records, RATES)
    for r in dry_run_records:
        mine = sum(x["cost_usd"] for x in rows if x["record_id"] == r["record_id"])
        assert abs(mine - r["cost_usd"]) <= usage.COST_TOLERANCE


def test_v1_records_get_cost_and_cache_miss_derived_from_the_rate_table():
    """The August runs predate per-call costs; they are derived and cross-checked."""
    r = make_record()
    r["calls"] = [
        {"stage": "generation", "input_tokens": 1000, "output_tokens": 2000,
         "cache_hit_tokens": 200, "reasoning_tokens": 1500, "latency_s": 1.0,
         "stop_reason": "stop", "truncated": False, "structured": False, "model": "m"},
    ]
    r["cost_usd"] = (800 * 0.44 + 200 * 0.014 + 2000 * 1.32) / 1e6
    rows = usage.flatten_calls([r], RATES)
    assert rows[0]["cache_miss_tokens"] == 800
    assert abs(rows[0]["cost_usd"] - r["cost_usd"]) <= usage.COST_TOLERANCE


def test_a_rate_table_that_disagrees_with_the_run_is_an_error_not_a_number():
    r = make_record()
    r["calls"] = [
        {"stage": "generation", "input_tokens": 1000, "output_tokens": 2000,
         "cache_hit_tokens": 0, "reasoning_tokens": 0, "latency_s": 1.0,
         "stop_reason": "stop", "truncated": False, "structured": False, "model": "m"},
    ]
    r["cost_usd"] = 0.5  # nothing like what RATES would give
    with pytest.raises(ValueError, match="rate table does not match"):
        usage.flatten_calls([r], RATES)


def test_false_green_spend_counts_only_approved_wrong_answers():
    fg = make_record(record_id="T01|self_verify|0", truth_initial="wrong", verdict="correct",
                     cost_usd=0.3)
    ok = make_record(record_id="T01|self_verify|1", truth_initial="correct", verdict="correct",
                     cost_usd=0.2)
    caught = make_record(record_id="T01|self_verify|2", truth_initial="wrong", verdict="wrong",
                         cost_usd=0.1)
    fr = make_record(record_id="T01|self_verify|3", truth_initial="correct", verdict="wrong",
                     cost_usd=0.05)
    for r in (fg, ok, caught, fr):
        r["calls"] = []  # no per-call rows needed for the record-level accounting
    acc = usage.cost_accounting([fg, ok, caught, fr], None)
    sv = acc["by_mode"]["self_verify"]
    assert sv["n_false_green"] == 1 and abs(sv["false_green_cost_usd"] - 0.3) < 1e-12
    assert sv["n_false_red"] == 1 and abs(sv["false_red_cost_usd"] - 0.05) < 1e-12
    assert sv["n_shown_wrong"] == 2 and sv["n_caught"] == 1


def test_baseline_has_no_verifier_so_its_verifier_metrics_are_none_not_zero():
    b = make_record(mode="baseline", record_id="T01|baseline|0")
    b["calls"] = []
    acc = usage.cost_accounting([b], None)
    blk = acc["by_mode"]["baseline"]
    assert blk["n_false_green"] is None and blk["false_green_cost_usd"] is None
    assert blk["verification_cost_usd"] is None
    assert "n/a" in usage.cost_markdown(acc, "generation", "x.jsonl")


def test_extra_cost_per_catch_is_none_when_nothing_was_caught():
    b = make_record(mode="baseline", record_id="T01|baseline|0", cost_usd=0.1)
    s = make_record(mode="self_verify", record_id="T01|self_verify|0", cost_usd=0.2,
                    truth_initial="correct", verdict="correct")
    b["calls"] = s["calls"] = []
    d = usage.cost_accounting([b, s], None)["self_verify_vs_baseline"]
    assert abs(d["extra_cost_usd"] - 0.1) < 1e-12
    assert d["wrong_answers_caught"] == 0
    assert d["extra_cost_per_wrong_answer_caught"] is None
    md = usage.cost_markdown(usage.cost_accounting([b, s], None), "generation", "x.jsonl")
    assert "nothing was caught" in md


def test_csv_round_trips_every_row(tmp_path, dry_run_records):
    rows = usage.flatten_calls(dry_run_records, RATES)
    out = usage.write_csv(rows, tmp_path / "u.csv")
    with out.open() as fh:
        back = list(csv.DictReader(fh))
    assert len(back) == len(rows)
    assert list(back[0].keys()) == usage.CALL_FIELDS
    assert back[0]["record_id"] == rows[0]["record_id"]


@pytest.mark.skipif(not LIVE_GEN.exists(), reason="live results not present")
def test_live_generation_run_cost_accounting_matches_the_raw_records():
    """The published numbers, recomputed from the raw file with the config rates."""
    cfg = config_mod.load()
    records = metrics.load_records(LIVE_GEN)
    acc = usage.cost_accounting(records, cfg.pricing_rates())
    assert acc["n_calls"] == 150
    assert abs(acc["total_cost_usd"] - sum(r["cost_usd"] for r in records)) < 1e-9
    d = acc["self_verify_vs_baseline"]
    # Self-verify's own generations were all correct: nothing reached the
    # verifier wrong, so nothing was caught and the extra cost bought no catch.
    assert d["self_verify_wrong_before_verification"] == 0
    assert d["wrong_answers_caught"] == 0
    assert d["false_greens"] == 0
    assert d["extra_cost_per_wrong_answer_caught"] is None


@pytest.mark.skipif(not LIVE_INJ.exists(), reason="live results not present")
def test_live_injection_run_false_green_spend_is_zero_because_there_were_none():
    cfg = config_mod.load()
    records = metrics.load_records(LIVE_INJ)
    acc = usage.cost_accounting(records, cfg.pricing_rates())
    w = acc["by_mode"]["inject_wrong"]
    assert w["n_false_green"] == 0 and w["false_green_cost_usd"] == 0.0
    c = acc["by_mode"]["inject_correct"]
    assert c["n_false_red"] == 5 and c["false_red_cost_usd"] > 0
