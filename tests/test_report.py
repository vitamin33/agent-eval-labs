"""P3.8 — reports are generated, reproducible, and honest about their source."""

import json
from pathlib import Path

import metrics
import report

ROOT = Path(__file__).resolve().parents[1]


def test_generates_table_and_both_charts(tmp_path, dry_run_records):
    results = tmp_path / "run.jsonl"
    results.write_text("\n".join(json.dumps(r, sort_keys=True) for r in dry_run_records) + "\n")
    rc = report.main(
        [
            "--results", str(results),
            "--out-md", str(tmp_path / "RESULTS.md"),
            "--assets", str(tmp_path / "assets"),
            "--no-readme",
        ]
    )
    assert rc == 0
    assert (tmp_path / "RESULTS.md").exists()
    for name in ("fig1_rates_by_mode.png", "fig2_calibration.png"):
        png = tmp_path / "assets" / name
        assert png.exists() and png.stat().st_size > 5_000
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_table_carries_intervals_not_just_point_estimates(dry_run_records):
    summary = metrics.summarize(dry_run_records, k=5)
    md = report.results_markdown(summary, "run.jsonl")
    assert md.count("[") > 5, "rates must be printed with their CIs"
    assert "Wilson 95%" in md


def test_synthetic_data_is_labelled_as_such(dry_run_records):
    md = report.results_markdown(metrics.summarize(dry_run_records, k=5), "run.jsonl")
    assert "SYNTHETIC DATA" in md


def test_per_task_breakdown_is_always_present(dry_run_records):
    md = report.results_markdown(metrics.summarize(dry_run_records, k=5), "run.jsonl")
    assert "Per-task breakdown" in md
    for tid in [f"T{i:02d}" for i in range(1, 11)]:
        assert tid in md


def test_report_is_deterministic(dry_run_records):
    summary = metrics.summarize(dry_run_records, k=5)
    assert report.results_markdown(summary, "x.jsonl") == report.results_markdown(summary, "x.jsonl")


def test_readme_injection_replaces_only_the_marked_block(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        f"# Title\n\nintro\n\n{report.README_BEGIN}\nOLD\n{report.README_END}\n\nfooter\n"
    )
    assert report.inject_readme("NEW TABLE", readme) is True
    text = readme.read_text()
    assert "NEW TABLE" in text and "OLD" not in text
    assert text.startswith("# Title") and text.rstrip().endswith("footer")


def test_readme_injection_is_a_noop_without_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# no markers here\n")
    assert report.inject_readme("NEW", readme) is False
    assert readme.read_text() == "# no markers here\n"


def test_chart_handles_a_run_with_no_parsed_verdicts(tmp_path):
    from conftest import make_record

    records = [make_record(mode="baseline", verdict=None) for _ in range(2)]
    summary = metrics.summarize(records, k=1)
    out = report.chart_calibration(summary, tmp_path / "cal.png")
    assert out.exists()


def test_only_mock_output_is_labelled_synthetic():
    """Adding a provider must not relabel real results as synthetic."""
    assert report.is_synthetic({"providers": ["mock"]}) is True
    assert report.is_synthetic({"providers": ["deepseek"]}) is False
    assert report.is_synthetic({"providers": ["anthropic"]}) is False
    assert report.is_synthetic({"providers": ["deepseek", "mock"]}) is True
    assert report.is_synthetic({}) is False


def test_live_results_carry_no_synthetic_banner():
    from conftest import make_record

    records = [make_record(provider="deepseek", mode="baseline", verdict=None)]
    md = report.results_markdown(metrics.summarize(records, k=1), "run-live.jsonl")
    assert "SYNTHETIC DATA" not in md


# --- two-arm reporting ------------------------------------------------------ #


def _summ(**over):
    from conftest import make_record

    s = metrics.summarize([make_record(mode="baseline", verdict=None)], k=1)
    s.update(over)
    return s


def test_combined_summary_takes_verification_from_the_injection_arm():
    """H1/H3/H5 come from the arm that has wrong answers; H2/H4 from generation."""
    gen = _summ(n_records=100)
    gen["false_green_rate"] = {"value": None, "ci_low": None, "ci_high": None, "n": 0, "k": 0}
    inj = _summ(n_records=100)
    inj["false_green_rate"] = {"value": 0.3, "ci_low": 0.2, "ci_high": 0.4, "n": 50, "k": 15}
    inj["n_false_greens"] = 15
    merged = report.combined_summary(gen, inj)
    assert merged["false_green_rate"]["value"] == 0.3
    assert merged["n_false_greens"] == 15
    assert merged["n_records"] == 200
    assert merged["arm"] == "combined"


def test_combined_summary_passes_through_a_single_arm():
    gen = _summ(n_records=100)
    assert report.combined_summary(gen, None) is gen
    inj = _summ(n_records=42)
    assert report.combined_summary(None, inj) is inj


def test_injection_markdown_reports_the_controlled_denominator():
    inj = _summ(n_records=100)
    inj["false_green_rate"] = {"value": 0.0, "ci_low": 0.0, "ci_high": 0.07, "n": 50, "k": 0}
    inj["false_red_rate"] = {"value": 0.02, "ci_low": 0.0, "ci_high": 0.1, "n": 50, "k": 1}
    md = report.injection_markdown(inj, "run-live-inject.jsonl")
    assert "50 wrong answers shown" in md
    assert "false-green rate" in md
    assert "run-live-inject.jsonl" in md
