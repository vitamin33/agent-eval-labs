"""Every number in the README's hand-written summary is recomputed from raw data.

The generated block is protected by report.py and gate G4. The plain-language
summary above it is prose and could drift, so this test recomputes each figure
it quotes from the live results files and asserts the exact string is present.
If a rerun changes a number, this fails until the prose is updated to match.
"""

from pathlib import Path

import pytest

import config as config_mod
import metrics
import usage

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
GEN = ROOT / "experiments/verifier-gap/results/run-live-20260819T190057Z.jsonl"
INJ = ROOT / "experiments/verifier-gap/results/run-live-inject-20260820T082818Z.jsonl"

pytestmark = pytest.mark.skipif(not (GEN.exists() and INJ.exists()), reason="live results absent")


@pytest.fixture(scope="module")
def data():
    cfg = config_mod.load()
    gen = metrics.load_records(GEN)
    inj = metrics.load_records(INJ)
    return {
        "gen": metrics.summarize(gen, k=5),
        "inj": metrics.summarize(inj, k=5),
        "gen_cost": usage.cost_accounting(gen, cfg.pricing_rates()),
        "inj_cost": usage.cost_accounting(inj, cfg.pricing_rates()),
        "md": README.read_text(),
    }


def _pct_ci(rate: dict) -> str:
    return f"[{rate['ci_low']*100:.1f}%, {rate['ci_high']*100:.1f}%]"


def test_false_green_and_false_red_lines(data):
    fg, fr = data["inj"]["false_green_rate"], data["inj"]["false_red_rate"]
    assert f"{fg['k']} of {fg['n']} = {fg['value']*100:.0f}%" in data["md"]
    assert _pct_ci(fg) in data["md"]
    assert f"{fr['k']} of {fr['n']} = {fr['value']*100:.0f}%" in data["md"]
    assert _pct_ci(fr) in data["md"]


def test_pass_rates(data):
    b = data["gen"]["by_mode"]["baseline"]
    s = data["gen"]["by_mode"]["self_verify"]
    assert f"{b['pass_at_1']['k']} of {b['pass_at_1']['n']} = {b['pass_at_1']['value']*100:.0f}%" in data["md"]
    assert _pct_ci(b["pass_at_1"]) in data["md"]
    assert f"{s['pass_at_1']['k']} of {s['pass_at_1']['n']} = {s['pass_at_1']['value']*100:.0f}%" in data["md"]
    hk = b["pass_hat_k"]
    assert f"{hk['k']} of {hk['n']} tasks = {hk['value']*100:.0f}%" in data["md"]
    assert _pct_ci(hk) in data["md"]


def test_cost_lines(data):
    d = data["gen_cost"]["self_verify_vs_baseline"]
    assert f"+${d['extra_cost_usd']:.3f} per 50 tasks, {d['multiplier']:.2f}x" in data["md"]
    assert f"{(d['multiplier']-1)*100:.0f}% cost increase" in data["md"]
    assert d["wrong_answers_caught"] == 0
    b = data["gen_cost"]["by_mode"]["baseline"]
    s = data["gen_cost"]["by_mode"]["self_verify"]
    assert f"${b['cost_per_correct']:.4f} without the self-check" in data["md"]
    assert f"${s['cost_per_correct']:.4f} with it" in data["md"]


def test_false_red_share_of_the_control_arm(data):
    c = data["inj_cost"]["by_mode"]["inject_correct"]
    share = c["false_red_cost_usd"] / c["cost_usd"]
    assert f"consumed {share*100:.0f}% of what the whole control arm cost" in data["md"]
    words = {5: "five"}
    assert f"Those {words.get(c['n_false_red'], c['n_false_red'])} false" in data["md"]


def test_the_sample_size_claim_matches_the_interval(data):
    fg = data["inj"]["false_green_rate"]
    assert fg["k"] == 0 and fg["n"] == 50
    assert f"(0 of 50 puts the 95% upper bound at {fg['ci_high']*100:.1f}%" in data["md"]


def test_replication_status_is_stated():
    md = README.read_text()
    assert "renamed under us" in md
    assert "deepseek-flash" in md
    assert "make reproduce-live" in md


def test_every_raw_run_on_disk_is_named_in_the_readme():
    """A run that exists cannot be absent from the writeup."""
    md = README.read_text()
    runs = sorted((ROOT / "experiments/verifier-gap/results").glob("run-live-*.jsonl"))
    assert runs, "no live runs on disk"
    missing = [f.name for f in runs if f.name not in md]
    assert not missing, f"raw runs present on disk but not named in the README: {missing}"


def test_total_spend_and_record_count_across_every_live_run():
    """The 'whole study' figure quoted in the README is a sum over every raw
    file in both experiments, recomputed here."""
    import json
    files = sorted((ROOT / "experiments").glob("*/results/*.jsonl"))
    rows = [json.loads(l) for f in files for l in f.read_text().splitlines() if l.strip()]
    total = sum(r.get("cost_usd", 0.0) for r in rows)
    assert f"{len(rows)} records for ${total:.2f} in model usage" in README.read_text()
