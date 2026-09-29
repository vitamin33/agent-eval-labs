"""Experiment 3 hypotheses: thresholds held against RESEARCH.md, and the
stopping rule applied as written."""

import re
from pathlib import Path

import pytest

import ckpt_hypotheses as ch

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = (ROOT / "experiments/agent-checkpoint/RESEARCH.md").read_text()


def sections():
    out = {}
    for m in re.finditer(r"^### (H\d+) .*?$(.*?)(?=^### |\Z)", RESEARCH, re.MULTILINE | re.DOTALL):
        out[m.group(1)] = m.group(2)
    return out


@pytest.mark.parametrize(
    "hid,key,needle",
    [
        ("H1", "H1_silent_failure_max_enforced", "25%"),
        ("H2", "H2_usage_max_tool", "50%"),
        ("H3", "H3_silent_failure_min_tool", "35%"),
        ("H4", "H4_cost_multiplier_max_enforced", "1.5x"),
        ("H5", "H5_outcome_pass_min_enforced", "70%"),
    ],
)
def test_code_thresholds_match_research_md(hid, key, needle):
    """A threshold must not be quietly moved after the data is in."""
    body = sections()[hid]
    lines = re.findall(r"\*\*Threshold:\*\*(.+)", body)
    assert lines, f"{hid} has no threshold line"
    assert any(needle in line for line in lines), (
        f"{hid}: code uses {ch.THRESHOLDS[key]} but RESEARCH.md's threshold line "
        f"does not mention {needle}")
    number = float(needle.rstrip("%x"))
    coded = ch.THRESHOLDS[key] * (100 if needle.endswith("%") else 1)
    assert coded == pytest.approx(number)


def test_h4_interim_band_is_the_one_research_md_names():
    assert "[1.2, 1.8]" in RESEARCH
    assert (ch.THRESHOLDS["H4_interim_band_low"], ch.THRESHOLDS["H4_interim_band_high"]) == (1.2, 1.8)


def test_every_research_hypothesis_is_evaluated():
    assert {r.id for r in ch.evaluate([])} == set(sections())


def test_research_md_has_no_results_section_and_labels_predictions():
    assert not re.search(r"^## Results", RESEARCH, re.MULTILINE)
    for hid, body in sections().items():
        assert "**Prediction:**" in body, hid
        assert "**Falsified if:**" in body, hid


def rec(mode, ok, claims=True, fired=True, cost=0.01, used=False, run=0):
    return {"task_id": "T1", "mode": mode, "run_index": run,
            "injection": {"applicable": fired} if mode != "clean" else None,
            "outcome_correct": ok, "claims_success": claims,
            "silent_failure": bool(mode != "clean" and fired and not ok and claims),
            "detected": False, "contamination_depth": None, "reconcile_used": used,
            "reconcile_on_subject": False, "cost_usd": cost, "n_steps": 4,
            "hit_step_cap": False, "truncated": False, "steps": [], "tokens": {}}


def _by_id(results):
    return {r.id: r for r in results}


def test_h1_supported_only_when_the_whole_interval_is_below_25():
    zero = [rec("inject_enforced", ok=True, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(zero, "99"))["H1"].verdict == ch.SUPPORTED
    # 3/40 = 7.5%: point estimate below, 99% interval straddles -> undetermined
    some = [rec("inject_enforced", ok=(i >= 3), run=i) for i in range(40)]
    assert _by_id(ch.evaluate(some, "99"))["H1"].verdict == ch.UNDETERMINED
    all_wrong = [rec("inject_enforced", ok=False, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(all_wrong, "99"))["H1"].verdict == ch.FALSIFIED


def test_h1_is_undetermined_with_no_data():
    assert _by_id(ch.evaluate([], "99"))["H1"].verdict == ch.UNDETERMINED


def test_h2_falsified_when_the_agent_reconciles_every_time():
    recs = [rec("inject_tool", ok=True, used=True, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(recs, "99"))["H2"].verdict == ch.FALSIFIED
    recs = [rec("inject_tool", ok=True, used=False, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(recs, "99"))["H2"].verdict == ch.SUPPORTED


def test_h3_is_the_lower_bound_direction():
    recs = [rec("inject_tool", ok=False, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(recs, "99"))["H3"].verdict == ch.SUPPORTED
    recs = [rec("inject_tool", ok=True, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(recs, "99"))["H3"].verdict == ch.FALSIFIED


def _cost_records(mult):
    base = [rec("inject", ok=False, cost=0.010, run=i) for i in range(4)]
    enf = [rec("inject_enforced", ok=True, cost=0.010 * mult, run=i) for i in range(4)]
    return base + enf


def test_h4_inside_the_band_waits_for_stage_2_and_is_decided_there():
    r99 = _by_id(ch.evaluate(_cost_records(1.4), "99"))["H4"]
    assert r99.verdict == ch.UNDETERMINED and not r99.decided
    r95 = _by_id(ch.evaluate(_cost_records(1.4), "95"))["H4"]
    assert r95.verdict == ch.SUPPORTED and r95.decided
    assert _by_id(ch.evaluate(_cost_records(1.6), "95"))["H4"].verdict == ch.FALSIFIED


def test_h4_outside_the_band_is_decided_at_the_interim_look():
    assert _by_id(ch.evaluate(_cost_records(1.05), "99"))["H4"].verdict == ch.SUPPORTED
    assert _by_id(ch.evaluate(_cost_records(2.0), "99"))["H4"].verdict == ch.FALSIFIED


def test_h4_is_decided_exactly_at_the_threshold_by_arithmetic_not_float_noise():
    r = _by_id(ch.evaluate(_cost_records(1.5), "95"))["H4"]
    assert r.verdict == ch.FALSIFIED  # "< 1.5" is not satisfied on the boundary


def test_h5_supported_when_the_checkpoint_restores_the_outcome():
    recs = [rec("inject_enforced", ok=True, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(recs, "99"))["H5"].verdict == ch.SUPPORTED
    recs = [rec("inject_enforced", ok=False, run=i) for i in range(40)]
    assert _by_id(ch.evaluate(recs, "99"))["H5"].verdict == ch.FALSIFIED


def test_markdown_names_the_level_and_the_undecided():
    md = ch.to_markdown(ch.evaluate([], "99"), "99")
    assert "99%" in md and "UNDETERMINED" in md and "stopping rule" in md
