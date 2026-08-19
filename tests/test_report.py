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
