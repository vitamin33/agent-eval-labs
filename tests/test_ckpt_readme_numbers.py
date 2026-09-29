"""Every number in the README's experiment 3 prose is recomputed from the raw
records. If a rerun changes a number, this fails until the prose matches."""

import json
import re
from pathlib import Path

import pytest

import ckpt_metrics as cm

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
RESULTS_DIR = ROOT / "experiments/agent-checkpoint/results"
STAGE2 = RESULTS_DIR / "ckpt-stage2-20260929T145911Z.jsonl"
STAGE4 = RESULTS_DIR / "ckpt-stage4-deepseek-wrapped-20260929T184151Z.jsonl"

pytestmark = pytest.mark.skipif(not STAGE2.exists(), reason="live results absent")


@pytest.fixture(scope="module")
def data():
    recs = cm.load(STAGE2)
    text = README.read_text()
    section = text[text.index("## Experiment 3"):text.index("## Repository layout")]
    return {"recs": recs, "s": cm.summarize(recs), "md": section}


def _pct_ci(rate: dict) -> str:
    return f"**{rate['value']*100:.1f}%** [{rate['ci_low']*100:.1f}%, {rate['ci_high']*100:.1f}%] ({rate['k']} of {rate['n']})"


@pytest.mark.parametrize("mode", ["inject", "inject_tool", "inject_enforced"])
def test_silent_failure_rows_match(data, mode):
    b = data["s"]["by_mode"][mode]
    assert _pct_ci(b["silent_failure_rate"]) in data["md"], mode
    p = b["outcome_pass_rate_fired"]
    assert f"| {p['k']} of {p['n']} |" in data["md"], mode
    mult = 1.0 if mode == "inject" else b["cost_multiplier"]
    assert f"${b['mean_cost_usd']:.5f} ({mult:.2f}x)" in data["md"], mode


def test_stage_2_size_and_cost(data):
    assert len(data["recs"]) == 160
    assert f"${data['s']['total_cost_usd']:.2f}" in data["md"]
    fired = cm.fired(data["recs"], "inject")
    assert len(fired) == 40 and "40 fired injections per arm" in data["md"]


def test_usage_and_remaining_failures(data):
    use = data["s"]["reconcile_usage_rate"]
    assert f"in {use['k']} of {use['n']} trajectories" in data["md"]
    sf = data["s"]["by_mode"]["inject_tool"]["silent_failure_rate"]
    assert f"{sf['k']} of {sf['n']}: it reconciled" in data["md"]
    tasks = {r["task_id"] for r in data["recs"] if r["mode"] == "inject_tool" and r["silent_failure"]}
    assert tasks == {"T4", "T8"}
    assert all(r["injection_kind"] == "wrong_field" for r in data["recs"]
               if r["mode"] == "inject_tool" and r["silent_failure"])


def test_baseline_claimed_success_every_time(data):
    fg = data["s"]["by_mode"]["inject"]["false_green_rate"]
    assert fg["k"] == fg["n"] == 22
    assert "22 of 22" in data["md"]


def test_enforced_removed_every_failure(data):
    b = data["s"]["by_mode"]["inject_enforced"]
    assert b["silent_failure_rate"]["k"] == 0 and b["outcome_pass_rate_fired"]["k"] == 40
    assert "removed every silent failure in 40 injected" in data["md"]


def test_verdicts_are_the_ones_stated(data):
    import ckpt_hypotheses as ch
    verdicts = {r.id: r.verdict for r in ch.evaluate(data["recs"], "95")}
    assert verdicts == {"H1": "SUPPORTED", "H2": "FALSIFIED", "H3": "FALSIFIED",
                        "H4": "SUPPORTED", "H5": "SUPPORTED"}
    assert "H1, H4 and H5 supported, H2 and H3 falsified" in data["md"]


def test_whole_experiment_spend_includes_aborted_starts(data):
    files = sorted(RESULTS_DIR.glob("*.jsonl"))
    assert any(f.name.startswith("aborted-") for f in files)
    total = sum(json.loads(l).get("cost_usd", 0.0) for f in files
                for l in f.read_text().splitlines() if l.strip())
    assert f"starts kept on disk: ${total:.2f}." in data["md"]


def test_every_raw_exp3_file_is_named_somewhere():
    named = (ROOT / "experiments/agent-checkpoint/CALIBRATION.md").read_text()
    for f in RESULTS_DIR.glob("*.jsonl"):
        assert f.name in named, f"{f.name} exists on disk but CALIBRATION.md does not name it"


def test_results_md_is_from_the_published_file():
    md = (ROOT / "experiments/agent-checkpoint/RESULTS.md").read_text()
    assert STAGE2.name in md and "**95%**" in md


@pytest.mark.skipif(not STAGE4.exists(), reason="stage 4 absent")
@pytest.mark.parametrize("mode", ["inject", "inject_wrapped", "inject_enforced"])
def test_wrapper_follow_up_rows_match(mode):
    recs = cm.load(STAGE4)
    assert len(recs) == 120
    s = cm.summarize(recs)
    text = README.read_text()
    md = text[text.index("**And without the sentence?**"):text.index("Five hypotheses, fixed before data")]
    b = s["by_mode"][mode]
    assert _pct_ci(b["silent_failure_rate"]) in md, mode
    p = b["outcome_pass_rate_fired"]
    assert f"| {p['k']} of {p['n']} |" in md, mode
    mult = 1.0 if mode == "inject" else b["cost_multiplier"]
    assert f"${b['mean_cost_usd']:.5f} ({mult:.2f}x)" in md, mode
    if mode == "inject_wrapped":
        assert {r["task_id"] for r in recs if r["mode"] == mode and r["silent_failure"]} == {"T7"}
        assert f"{b['mean_steps']} steps against {s['by_mode']['inject_enforced']['mean_steps']}" in md


@pytest.mark.skipif(not STAGE4.exists(), reason="stage 4 absent")
def test_h8_verdict_is_the_one_stated():
    import ckpt_hypotheses as ch
    by = {r.id: r for r in ch.evaluate_replication(cm.load(STAGE4), "95")}
    assert by["H8"].verdict == "SUPPORTED"
    assert "H8 (the wrapper without its sentence stays under 25%) supported" in README.read_text()
