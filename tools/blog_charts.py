#!/usr/bin/env python3
"""Charts for the serbyn.io write-ups, generated from the raw records.

Dark surface to match the site. Same rule as every other report here: nothing
is drawn from memory, every number comes from a results file, and re-running
this regenerates the images byte-for-byte from the same data.

    python tools/blog_charts.py --out /path/to/serbyn-pro/public/blog
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "experiments" / "verifier-gap", ROOT / "experiments" / "agent-verifier-gap",
          ROOT / "experiments" / "agent-checkpoint"):
    sys.path.insert(0, str(p))

import ckpt_metrics as cm  # noqa: E402
import metrics  # noqa: E402
import traj_metrics as tm  # noqa: E402
from metrics import wilson  # noqa: E402

# Dark palette: validated categorical slots re-stepped for a dark surface.
SURFACE = "#0b0f19"
INK = "#e6e6e3"
INK_MUTED = "#9a9a94"
GRID = "#262a35"
C_ONE = "#3987e5"    # blue, slot 1 dark step
C_TWO = "#d95926"    # orange, slot 2 dark step
C_WARN = "#e66767"

EXP1_GEN = ROOT / "experiments/verifier-gap/results/run-live-20260819T190057Z.jsonl"
EXP1_INJ = ROOT / "experiments/verifier-gap/results/run-live-inject-20260820T082818Z.jsonl"
EXP2_S2 = ROOT / "experiments/agent-verifier-gap/results/traj-stage2-20260901T171546Z.jsonl"
C_THREE = "#3fb27f"  # green, slot 3 dark step


def exp3_published() -> Path:
    """The newest complete stage-2 file of experiment 3 (160 records), else
    the newest complete stage-1 file. Aborted partials are never chosen."""
    d = ROOT / "experiments/agent-checkpoint/results"
    for stage, n in ((2, 160), (1, 64)):
        for f in sorted(d.glob(f"ckpt-stage{stage}-*.jsonl"), reverse=True):
            if sum(1 for line in f.read_text().splitlines() if line.strip()) == n:
                return f
    raise FileNotFoundError("no complete experiment 3 stage file")

ORIG_RECHECK = {
    "omission": {"count_orders", "list_orders"},
    "stale": {"get_order", "get_shipment"},
    "off_by_one": {"get_order", "sum_totals"},
    "wrong_field": {"get_customer", "list_orders", "count_orders"},
}


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def err(k, n):
    lo, hi = wilson(k, n)
    p = k / n
    # clamp: at k == n the upper bound is 1.0 up to float epsilon
    return [[max(0.0, 100 * (p - lo))], [max(0.0, 100 * (hi - p))]]


def bar_with_ci(ax, x, k, n, color, label=None, width=0.34):
    val = 100 * k / n
    ax.bar(x, val, width, color=color, zorder=3, label=label)
    e = err(k, n)
    ax.errorbar(x, val, yerr=e, fmt="none", ecolor=INK, elinewidth=1.3, capsize=4, capthick=1.3, zorder=4)
    ax.text(x, val + e[1][0] + 2.5, f"{val:.0f}%", ha="center", va="bottom", fontsize=10, color=INK, zorder=5)
    ax.text(x, -7, f"{k} / {n}", ha="center", va="top", fontsize=8, color=INK_MUTED)


def save(fig, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE, dpi=200, bbox_inches="tight", metadata={"Software": "agent-eval-labs"})
    plt.close(fig)
    print(f"  -> {out}")


# --------------------------------------------------------------------------- #
# A1 — the contrast: same model, single answer vs trajectory
# --------------------------------------------------------------------------- #

def chart_contrast(out: Path):
    inj1 = metrics.load_records(EXP1_INJ)
    fg1 = metrics.false_green_rate(inj1)
    wrong1 = [r for r in inj1 if r["truth_initial"] != "correct"]
    caught1 = sum(1 for r in wrong1 if r["verdict"] == "wrong")

    t2 = tm.load(EXP2_S2)
    fg2 = tm.trajectory_false_green_rate(t2)
    det2 = tm.detection_rate(t2)

    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    style(ax)
    w = 0.34
    # group 0: false-green rate ; group 1: caught the planted fault
    bar_with_ci(ax, 0 - w / 2 - 0.01, fg1.numerator, fg1.denominator, C_ONE, "single answer")
    bar_with_ci(ax, 0 + w / 2 + 0.01, fg2.numerator, fg2.denominator, C_TWO, "trajectory")
    bar_with_ci(ax, 1 - w / 2 - 0.01, caught1, len(wrong1), C_ONE)
    bar_with_ci(ax, 1 + w / 2 + 0.01, det2.numerator, det2.denominator, C_TWO)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["false-green rate", "caught the planted fault"], fontsize=10, color=INK)
    ax.set_ylim(-14, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("rate, %", fontsize=9, color=INK_MUTED)
    ax.set_title("deepseek-v4-flash, same week", fontsize=12, color=INK, loc="left", pad=14)
    ax.text(0, 1.015, "error bars: Wilson 95% CI · single answer n=50 wrong shown · trajectory n=70 injected",
            transform=ax.transAxes, fontsize=8, color=INK_MUTED)
    leg = ax.legend(frameon=False, fontsize=9, loc="upper center", ncols=2, bbox_to_anchor=(0.5, -0.17))
    for t in leg.get_texts():
        t.set_color(INK)
    save(fig, out / "verifier-gap-contrast.png")


# --------------------------------------------------------------------------- #
# A2 — contamination depth distribution
# --------------------------------------------------------------------------- #

def chart_contamination(out: Path):
    t2 = tm.load(EXP2_S2)
    d = tm.contamination_depths(t2)
    c = tm.contamination_summary(t2)
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    style(ax)
    ax.grid(axis="x", visible=False)
    xs = sorted(set(d))
    counts = [d.count(x) for x in xs]
    ax.bar(xs, counts, width=0.8, color=C_TWO, zorder=3)
    ax.axvline(c["median"], color=INK, linewidth=1.2, linestyle=(0, (4, 3)), zorder=4)
    ax.text(c["median"] + 0.3, max(counts) * 0.95, f"median {c['median']:.0f}", color=INK, fontsize=9, va="top")
    ax.set_xlabel("tool-call steps taken on the corrupted value before re-checking it (or submitting)",
                  fontsize=9, color=INK_MUTED)
    ax.set_ylabel("trajectories", fontsize=9, color=INK_MUTED)
    ax.set_xticks(range(0, c["max"] + 2, 2))
    ax.set_yticks(range(0, max(counts) + 5, 5))
    ax.set_title("Contamination depth", fontsize=12, color=INK, loc="left", pad=14)
    ax.text(0, 1.02, f"n={c['n']} injected trajectories · range {c['min']}–{c['max']}",
            transform=ax.transAxes, fontsize=8, color=INK_MUTED)
    save(fig, out / "contamination-depth.png")


# --------------------------------------------------------------------------- #
# B1 — detection under two definitions, same data
# --------------------------------------------------------------------------- #

def chart_definition(out: Path):
    t2 = tm.load(EXP2_S2)
    inj = tm.injected(t2)
    old = sum(
        1 for x in inj
        if any(s["idx"] > x["injection"]["fired_at_step"] and s["tool"] in ORIG_RECHECK[x["injection_kind"]]
               for s in x["steps"])
    )
    new = sum(1 for x in inj if x["detected"])
    n = len(inj)
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    style(ax)
    bar_with_ci(ax, 0, old, n, C_WARN, width=0.5)
    bar_with_ci(ax, 1, new, n, C_ONE, width=0.5)
    ax.axhline(50, color=INK_MUTED, linewidth=1, linestyle=(0, (3, 3)), zorder=2)
    ax.text(1.32, 51.5, "H2 threshold: < 50%", color=INK_MUTED, fontsize=8, ha="right")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(['"called the tool again"', '"re-examined the same subject"'], fontsize=9.5, color=INK)
    ax.set_ylim(-14, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("detection rate, %", fontsize=9, color=INK_MUTED)
    ax.set_title("Same 70 trajectories, two definitions of detection", fontsize=12, color=INK, loc="left", pad=14)
    ax.text(0, 1.02, "the first counts ordinary progress through a customer list as suspicion",
            transform=ax.transAxes, fontsize=8, color=INK_MUTED)
    save(fig, out / "detection-two-definitions.png")


# --------------------------------------------------------------------------- #
# B2 — the −26pp trap: pooled vs manipulated position
# --------------------------------------------------------------------------- #

def chart_position_trap(out: Path):
    t2 = tm.load(EXP2_S2)
    pooled = tm.detection_by_position(t2)
    manip = tm.detection_by_position(t2, manipulated_only=True)
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 4.0), sharey=True)
    for ax, data, title in (
        (axes[0], pooled, "pooled across all tasks"),
        (axes[1], manip, "only tasks where late ≠ early  (" + ", ".join(manip.get("tasks", [])) + ")"),
    ):
        style(ax)
        for i, pos in enumerate(("early", "late")):
            k, n = data[pos]["k"], data[pos]["n"]
            if n:
                bar_with_ci(ax, i, k, n, C_ONE if pos == "early" else C_TWO, width=0.5)
            else:
                ax.text(i, 6, "n = 0\nnever fired", ha="center", va="bottom", fontsize=9, color=C_WARN, style="italic")
                ax.text(i, -7, "0 / 0", ha="center", va="top", fontsize=8, color=INK_MUTED)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["early", "late"], fontsize=10, color=INK)
        ax.set_ylim(-14, 75)
        ax.set_yticks([0, 20, 40, 60])
        ax.set_title(title, fontsize=10, color=INK, loc="left", pad=10)
    axes[0].set_ylabel("detection rate, %", fontsize=9, color=INK_MUTED)
    fig.suptitle("The −26pp that was not a position effect", fontsize=12, color=INK, x=0.02, ha="left", y=1.02)
    save(fig, out / "position-trap.png")


# --------------------------------------------------------------------------- #
# A5 — experiment 3: silent failures and cost by mode
# --------------------------------------------------------------------------- #

def chart_checkpoint(out: Path):
    path = exp3_published()
    recs = cm.load(path)
    modes = [("inject", "no checkpoint", C_WARN), ("inject_tool", "reconcile tool,\nvoluntary", C_TWO),
             ("inject_enforced", "checkpoint,\nenforced", C_THREE)]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    style(ax)
    for i, (m, label, color) in enumerate(modes):
        r = cm.silent_failure_rate(recs, m)
        bar_with_ci(ax, i, r.numerator, r.denominator, color, width=0.55)
    ax.set_xticks(range(3))
    ax.set_xticklabels([l for _, l, _ in modes], fontsize=9, color=INK)
    ax.set_ylim(-14, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("silent failures per fired injection, %", fontsize=9, color=INK_MUTED)
    ax.set_title("Finished wrong and said done", fontsize=11, color=INK, loc="left", pad=12)

    ax = axes[1]
    style(ax)
    base = cm.mean_cost(recs, "inject")
    for i, (m, label, color) in enumerate(modes):
        mult = cm.mean_cost(recs, m) / base
        ax.bar(i, mult, 0.55, color=color, zorder=3)
        ax.text(i, mult + 0.04, f"{mult:.2f}x", ha="center", va="bottom", fontsize=10, color=INK)
    ax.axhline(1.0, color=INK_MUTED, linewidth=0.8, linestyle="--", zorder=2)
    ax.set_xticks(range(3))
    ax.set_xticklabels([l for _, l, _ in modes], fontsize=9, color=INK)
    ax.set_ylim(0, max(2.6, 1.15 * max(cm.mean_cost(recs, m) / base for m, _, _ in modes)))
    ax.set_ylabel("cost per trajectory, relative to no checkpoint", fontsize=9, color=INK_MUTED)
    ax.set_title("What it cost", fontsize=11, color=INK, loc="left", pad=12)
    n = cm.silent_failure_rate(recs, "inject").denominator
    fig.text(0.02, 0.965, f"deepseek-flash · {path.name} · error bars: Wilson 95% CI · n={n} fired injections per arm",
             fontsize=8, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save(fig, out / "checkpoint-silent-failures.png")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    chart_contrast(out)
    chart_contamination(out)
    chart_definition(out)
    chart_position_trap(out)
    chart_checkpoint(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
