#!/usr/bin/env python3
"""Generate the results table and both charts from raw results.

Reports are generated, never hand-written. Everything this script emits is
derived from an append-only .jsonl results file; editing the output by hand
means the next run silently reverts it, and gate G4 recomputes one metric
independently to catch a report that has drifted from its data.

    python experiments/verifier-gap/report.py --results results/run-live-*.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import metrics  # noqa: E402

ASSETS = ROOT / "docs" / "assets"

# Validated categorical pair (dataviz palette slots 1 and 2).
C_BASELINE = "#2a78d6"
C_SELFVERIFY = "#eb6834"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
SURFACE = "#fcfcfb"
GRID = "#e3e2de"
WARN = "#e34948"

MODE_LABEL = {"baseline": "baseline", "self_verify": "self-verify"}


def _style(ax) -> None:
    """Recessive axes and grid; the data carries the ink."""
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _synthetic_banner(ax, summary: dict) -> None:
    """Stamp mocked output so a chart cannot be screenshotted out of context."""
    if summary.get("providers") == ["anthropic"]:
        return
    ax.text(
        0.5,
        0.5,
        "SYNTHETIC\nmocked dry run",
        transform=ax.transAxes,
        fontsize=26,
        color=WARN,
        alpha=0.16,
        ha="center",
        va="center",
        rotation=24,
        zorder=6,
        fontweight="bold",
    )

def _asym_err(rate: dict) -> tuple[float, float]:
    """Wilson interval as (lower_len, upper_len) for matplotlib yerr."""
    if rate["value"] is None:
        return (0.0, 0.0)
    return (
        max(0.0, rate["value"] - rate["ci_low"]),
        max(0.0, rate["ci_high"] - rate["value"]),
    )


# --------------------------------------------------------------------------- #
# chart (a): pass@1 vs pass^k vs false-green, by mode
# --------------------------------------------------------------------------- #


def chart_rates(summary: dict, out: Path) -> Path:
    k = summary["k"]
    groups = ["pass@1", f"pass^{k}", "false-green"]
    base = summary["by_mode"]["baseline"]
    sv = summary["by_mode"]["self_verify"]

    series = {
        "baseline": [base["pass_at_1"], base["pass_hat_k"], None],
        "self_verify": [sv["pass_at_1"], sv["pass_hat_k"], summary["false_green_rate"]],
    }

    fig, ax = plt.subplots(figsize=(7.6, 4.4), dpi=200)
    _style(ax)
    width, xs = 0.34, range(len(groups))

    for i, (mode, rates) in enumerate(series.items()):
        color = C_BASELINE if mode == "baseline" else C_SELFVERIFY
        offset = (i - 0.5) * (width + 0.02)  # 2px-equivalent gap between fills
        for j, rate in enumerate(rates):
            if rate is None or rate["value"] is None:
                continue
            val = rate["value"] * 100
            lo, hi = _asym_err(rate)
            ax.bar(
                j + offset,
                val,
                width,
                color=color,
                zorder=3,
                label=MODE_LABEL[mode] if j == 0 else None,
            )
            ax.errorbar(
                j + offset,
                val,
                yerr=[[lo * 100], [hi * 100]],
                fmt="none",
                ecolor=INK,
                elinewidth=1.4,
                capsize=4,
                capthick=1.4,
                zorder=4,
            )
            # Direct label: relief for the contrast rule, and it saves a lookup.
            ax.text(
                j + offset,
                val + hi * 100 + 2.4,
                f"{val:.0f}%",
                ha="center",
                va="bottom",
                fontsize=9,
                color=INK,
                zorder=5,
            )

    # Baseline has no verifier, so false-green is undefined — not zero.
    ax.text(
        2 - 0.5 * (width + 0.02),
        3,
        "n/a\nno verifier",
        ha="center",
        va="bottom",
        fontsize=8,
        color=INK_MUTED,
        style="italic",
        zorder=5,
    )

    ax.set_xticks(list(xs))
    ax.set_xticklabels(groups, fontsize=10, color=INK)
    ax.set_ylabel("rate (%)", fontsize=9, color=INK_MUTED)
    ax.set_ylim(0, 108)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_title(
        "Accuracy, reliability, and the false-green rate",
        fontsize=12,
        color=INK,
        loc="left",
        pad=14,
    )
    ax.text(
        0,
        1.015,
        f"error bars: Wilson 95% CI  ·  n={summary['n_records']} records  ·  k={k}",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK_MUTED,
    )
    _synthetic_banner(ax, summary)
    leg = ax.legend(frameon=False, fontsize=9, loc="upper right", ncols=2)
    for text in leg.get_texts():
        text.set_color(INK)

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE, metadata={"Software": "agent-eval-labs"})
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# chart (b): verifier calibration
# --------------------------------------------------------------------------- #


def chart_calibration(summary: dict, out: Path) -> Path:
    bins = [b for b in summary["ece_bins"] if b["n"] > 0]
    fig, ax = plt.subplots(figsize=(5.6, 5.2), dpi=200)
    _style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)

    ax.plot([0, 1], [0, 1], color=INK_MUTED, linewidth=1.2, linestyle=(0, (4, 3)), zorder=2)
    ax.text(0.62, 0.585, "perfect calibration", fontsize=8.5, color=INK_MUTED, rotation=39)

    if bins:
        xs = [b["confidence"] for b in bins]
        ys = [b["accuracy"] for b in bins]
        ns = [b["n"] for b in bins]
        ax.plot(xs, ys, color=C_SELFVERIFY, linewidth=1.6, zorder=3)
        ax.scatter(
            xs,
            ys,
            s=[max(64, 26 * n**0.7) for n in ns],
            color=C_SELFVERIFY,
            edgecolor=SURFACE,
            linewidth=2,
            zorder=4,
        )
        for x, y, n in zip(xs, ys, ns):
            # Points near the ceiling have no room above; label them to the side.
            side = y > 0.92
            ax.annotate(
                f"n={n}",
                (x, y),
                textcoords="offset points",
                xytext=(15, -4) if side else (0, -17),
                ha="left" if side else "center",
                fontsize=8,
                color=INK_MUTED,
            )
    else:
        ax.text(0.5, 0.5, "no parsed verdicts", ha="center", color=INK_MUTED)

    ece = summary["ece"]
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("stated confidence", fontsize=9, color=INK_MUTED)
    ax.set_ylabel("observed verdict accuracy", fontsize=9, color=INK_MUTED)
    ax.set_title("Verifier calibration", fontsize=12, color=INK, loc="left", pad=14)
    ax.text(
        0,
        1.015,
        (f"ECE = {ece:.3f}" if ece is not None else "ECE = n/a")
        + "  ·  marker area \u221d bin count",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK_MUTED,
    )
    # The note belongs in the region it describes: below the diagonal.
    ax.text(
        0.98,
        0.05,
        "below the line:\nconfidence exceeds accuracy",
        fontsize=8.5,
        color=INK_MUTED,
        ha="right",
        va="bottom",
    )

    _synthetic_banner(ax, summary)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE, metadata={"Software": "agent-eval-labs"})
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #


def _r(d: dict, pct: bool = True) -> str:
    if d is None or d.get("value") is None:
        return "n/a"
    if pct:
        return f"{d['value']*100:.1f}% [{d['ci_low']*100:.1f}, {d['ci_high']*100:.1f}]"
    return f"{d['value']:.3f} [{d['ci_low']:.3f}, {d['ci_high']:.3f}]"


def results_markdown(summary: dict, source: str) -> str:
    k = summary["k"]
    base, sv = summary["by_mode"]["baseline"], summary["by_mode"]["self_verify"]
    synthetic = summary["providers"] != ["anthropic"]

    lines: list[str] = []
    if synthetic:
        lines += [
            "> **SYNTHETIC DATA.** These numbers come from the mocked dry run "
            f"(provider: {', '.join(summary['providers'])}). They exercise the "
            "pipeline and mean nothing about model behaviour.",
            "",
        ]

    lines += [
        f"Model `{', '.join(summary['models_resolved'])}` · "
        f"{summary['n_records']} records · k={k} · "
        f"brackets are Wilson 95% confidence intervals.",
        "",
        "| Metric | baseline | self-verify |",
        "|---|---|---|",
        f"| pass@1 | {_r(base['pass_at_1'])} | {_r(sv['pass_at_1'])} |",
        f"| pass^{k} | {_r(base['pass_hat_k'])} | {_r(sv['pass_hat_k'])} |",
        f"| cost (USD) | ${base['cost_usd']:.4f} | ${sv['cost_usd']:.4f} |",
        f"| cost per solved task | "
        f"{'$%.5f' % base['cost_per_solved_task'] if base['cost_per_solved_task'] else 'n/a'} | "
        f"{'$%.5f' % sv['cost_per_solved_task'] if sv['cost_per_solved_task'] else 'n/a'} |",
        f"| tokens in / out | {base['input_tokens']:,} / {base['output_tokens']:,} | "
        f"{sv['input_tokens']:,} / {sv['output_tokens']:,} |",
        "",
        "### Verifier behaviour",
        "",
        "| Metric | value |",
        "|---|---|",
        f"| **false-green rate** | **{_r(summary['false_green_rate'])}** |",
        f"| false-red rate | {_r(summary['false_red_rate'])} |",
        f"| verifier accuracy | {_r(summary['verifier_accuracy'])} |",
        f"| expected calibration error | "
        f"{'%.3f' % summary['ece'] if summary['ece'] is not None else 'n/a'} |",
        f"| mean confidence on false greens | "
        f"{'%.1f' % summary['mean_confidence_on_false_greens'] if summary['mean_confidence_on_false_greens'] is not None else 'n/a'}"
        f" (n={summary['n_false_greens']}) |",
        f"| Δpass@1 (self-verify − baseline) | "
        f"{'%+.1f pp' % summary['delta_pass_at_1_pp'] if summary['delta_pass_at_1_pp'] is not None else 'n/a'} |",
        f"| cost multiplier | "
        f"{'%.2fx' % summary['cost_multiplier'] if summary['cost_multiplier'] else 'n/a'} |",
        f"| verdict parse failure rate | {_r(summary['verdict_parse_failure_rate'])} |",
        "",
        "### Per-task breakdown",
        "",
        "Aggregates hide per-task variance, so the breakdown is always reported "
        "beside them.",
        "",
        "| Task | Type | baseline pass@1 | self-verify pass@1 | false greens |",
        "|---|---|---|---|---|",
    ]
    for tid, t in summary["per_task"].items():
        fg = t["false_green"]
        fg_txt = "n/a" if fg["value"] is None else f"{fg['k']}/{fg['n']}"
        lines.append(
            f"| {tid} {t['task_name']} | {t['task_type']} | "
            f"{t['baseline_pass_at_1']['k']}/{t['baseline_pass_at_1']['n']} | "
            f"{t['self_verify_pass_at_1']['k']}/{t['self_verify_pass_at_1']['n']} | {fg_txt} |"
        )
    lines += ["", f"<sub>Generated by `report.py` from `{source}`. Do not edit by hand.</sub>", ""]
    return "\n".join(lines)


README_BEGIN = "<!-- BEGIN GENERATED RESULTS -->"
README_END = "<!-- END GENERATED RESULTS -->"


def inject_readme(markdown: str, readme: Path) -> bool:
    if not readme.exists():
        return False
    text = readme.read_text()
    if README_BEGIN not in text or README_END not in text:
        return False
    head, rest = text.split(README_BEGIN, 1)
    _, tail = rest.split(README_END, 1)
    readme.write_text(f"{head}{README_BEGIN}\n\n{markdown}\n{README_END}{tail}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", required=True, help="path to a results .jsonl")
    ap.add_argument("--out-md", default=str(HERE / "RESULTS.md"))
    ap.add_argument("--assets", default=str(ASSETS))
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    ap.add_argument("--no-readme", action="store_true")
    args = ap.parse_args(argv)

    records = metrics.load_records(args.results)
    if not records:
        print(f"no records in {args.results}", file=sys.stderr)
        return 1
    k = max(r["run_index"] for r in records) + 1
    summary = metrics.summarize(records, k=k)

    assets = Path(args.assets)
    source = Path(args.results).name
    fig1 = chart_rates(summary, assets / "fig1_rates_by_mode.png")
    fig2 = chart_calibration(summary, assets / "fig2_calibration.png")

    md = results_markdown(summary, source)
    Path(args.out_md).write_text(md)
    summary_path = Path(args.results).with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))

    if not args.no_readme:
        injected = inject_readme(md, Path(args.readme))
        print(f"README injected: {injected}")

    print(f"table   -> {args.out_md}")
    print(f"summary -> {summary_path}")
    print(f"chart a -> {fig1}")
    print(f"chart b -> {fig2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
