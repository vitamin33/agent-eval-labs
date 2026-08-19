"""Metrics for the verifier-gap experiment.

Every formula here is the one written in RESEARCH.md; that document is the
specification and this module is its implementation. Every rate carries a
Wilson 95% interval. Degenerate denominators return None, never 0.0 — a metric
that could not be computed must not look like a measurement of zero.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

Z95 = 1.959964


# --------------------------------------------------------------------------- #
# rates and intervals
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Rate:
    """A proportion with its Wilson 95% interval."""

    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    @property
    def ci(self) -> tuple[float, float] | None:
        return wilson(self.numerator, self.denominator)

    def to_dict(self) -> dict:
        ci = self.ci
        return {
            "value": self.value,
            "ci_low": ci[0] if ci else None,
            "ci_high": ci[1] if ci else None,
            "n": self.denominator,
            "k": self.numerator,
        }

    def fmt(self, pct: bool = True) -> str:
        if self.value is None:
            return "n/a (n=0)"
        lo, hi = self.ci
        if pct:
            return f"{self.value * 100:.1f}% [{lo * 100:.1f}, {hi * 100:.1f}]"
        return f"{self.value:.3f} [{lo:.3f}, {hi:.3f}]"


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval. Wald is wrong at these n and near 0/1, so it is
    not used anywhere in this experiment."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #


def load_records(path: str | Path) -> list[dict]:
    """Read an append-only .jsonl results file."""
    path = Path(path)
    records = []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{i}: malformed record: {exc}") from exc
    return records


def _mode(records: list[dict], mode: str) -> list[dict]:
    return [r for r in records if r["mode"] == mode]


def _correct(r: dict) -> bool:
    """Ground truth for the answer the mode finally produced."""
    return r["truth_final"] == "correct"


# --------------------------------------------------------------------------- #
# core metrics
# --------------------------------------------------------------------------- #


def pass_at_1(records: list[dict]) -> Rate:
    """(1/N) * sum_i(c_i / R), reported with a CI over the N*R trials.

    Averaging per task first and then over tasks is identical to the pooled
    proportion when every task has the same run count, which the matrix
    guarantees; the pooled form is used for the interval.
    """
    return Rate(sum(1 for r in records if _correct(r)), len(records))


def pass_at_1_by_task(records: list[dict]) -> dict[str, Rate]:
    per: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        per[r["task_id"]].append(r)
    return {tid: Rate(sum(1 for r in rs if _correct(r)), len(rs)) for tid, rs in sorted(per.items())}


def pass_hat_k(records: list[dict], k: int) -> Rate:
    """Fraction of tasks correct on ALL k runs."""
    per = pass_at_1_by_task(records)
    eligible = {tid: rate for tid, rate in per.items() if rate.denominator == k}
    solved = sum(1 for rate in eligible.values() if rate.numerator == k)
    return Rate(solved, len(eligible))


def false_green_rate(records: list[dict]) -> Rate:
    """P(verdict = correct | the answer shown to the verifier was wrong).

    Conditioned on `truth_initial`: the verdict is a judgement about the
    generated answer, not about any later revision.
    """
    shown_wrong = [r for r in _mode(records, "self_verify") if r["truth_initial"] != "correct"]
    approved = [r for r in shown_wrong if r["verdict"] == "correct"]
    return Rate(len(approved), len(shown_wrong))


def false_red_rate(records: list[dict]) -> Rate:
    """P(verdict = wrong | the answer shown to the verifier was correct)."""
    shown_correct = [r for r in _mode(records, "self_verify") if r["truth_initial"] == "correct"]
    rejected = [r for r in shown_correct if r["verdict"] == "wrong"]
    return Rate(len(rejected), len(shown_correct))


def verifier_accuracy(records: list[dict]) -> Rate:
    judged = [r for r in _mode(records, "self_verify") if r["verdict"] is not None]
    agree = [r for r in judged if r["verdict"] == r["truth_initial"]]
    return Rate(len(agree), len(judged))


def hardcode_rate(records: list[dict]) -> Rate:
    """Fraction of graded artifacts that satisfied every visible case and then
    failed a held-out one.

    A validity metric, not a model-quality one: a high rate means the tasks are
    solvable by writing to the stated examples, which would make pass@1 measure
    example-matching rather than the requirement.
    """
    graded = [
        r for r in records
        if r.get("grade_initial", {}).get("outcome") in ("correct", "wrong")
    ]
    hardcoded = [r for r in graded if r.get("grade_initial", {}).get("hardcoded")]
    return Rate(len(hardcoded), len(graded))


def truncation_rate(records: list[dict]) -> Rate:
    """Fraction of records where a call hit the output cap.

    A truncated completion has no usable answer and grades as a non-answer, so
    truncation caused by a low `max_tokens` would be mismeasured as model
    failure. On reasoning models this is a live risk: most of the budget is
    spent on reasoning tokens that never reach the response.
    """
    return Rate(sum(1 for r in records if r.get("truncated")), len(records))


def verdict_parse_failure_rate(records: list[dict]) -> Rate:
    sv = _mode(records, "self_verify")
    return Rate(sum(1 for r in sv if r["verdict"] is None), len(sv))


def total_cost(records: list[dict]) -> float:
    return sum(r["cost_usd"] for r in records)


def total_tokens(records: list[dict]) -> tuple[int, int]:
    return (
        sum(r["tokens"]["input"] for r in records),
        sum(r["tokens"]["output"] for r in records),
    )


def cost_per_solved_task(records: list[dict]) -> float | None:
    solved = sum(1 for r in records if _correct(r))
    if solved == 0:
        return None
    return total_cost(records) / solved


def expected_calibration_error(records: list[dict], n_bins: int = 10) -> tuple[float | None, list[dict]]:
    """ECE over verifier confidence, with the per-bin table it was built from.

    Accuracy in a bin is how often the verdict matched ground truth; confidence
    is the verifier's stated number. Empty bins contribute nothing.
    """
    judged = [
        r
        for r in _mode(records, "self_verify")
        if r["verdict"] is not None and r["confidence"] is not None
    ]
    if not judged:
        return None, []

    bins: list[list[dict]] = [[] for _ in range(n_bins)]
    for r in judged:
        p = min(max(r["confidence"] / 100.0, 0.0), 1.0)
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append(r)

    total = len(judged)
    ece = 0.0
    table = []
    for i, bucket in enumerate(bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not bucket:
            table.append({"bin": f"[{lo:.1f},{hi:.1f})", "n": 0, "accuracy": None, "confidence": None})
            continue
        acc = sum(1 for r in bucket if r["verdict"] == r["truth_initial"]) / len(bucket)
        conf = sum(r["confidence"] for r in bucket) / len(bucket) / 100.0
        ece += (len(bucket) / total) * abs(acc - conf)
        table.append(
            {"bin": f"[{lo:.1f},{hi:.1f})", "n": len(bucket), "accuracy": acc, "confidence": conf}
        )
    return ece, table


def mean_confidence_on_false_greens(records: list[dict]) -> tuple[float | None, int]:
    fg = [
        r
        for r in _mode(records, "self_verify")
        if r["truth_initial"] != "correct"
        and r["verdict"] == "correct"
        and r["confidence"] is not None
    ]
    if not fg:
        return None, 0
    return sum(r["confidence"] for r in fg) / len(fg), len(fg)


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #


def summarize(records: list[dict], k: int = 5) -> dict:
    """Every metric in RESEARCH.md, plus the per-task breakdown."""
    base = _mode(records, "baseline")
    sv = _mode(records, "self_verify")

    p1_base, p1_sv = pass_at_1(base), pass_at_1(sv)
    cost_base, cost_sv = total_cost(base), total_cost(sv)
    ece, ece_table = expected_calibration_error(records)
    mean_conf_fg, n_fg = mean_confidence_on_false_greens(records)

    delta = None
    if p1_base.value is not None and p1_sv.value is not None:
        # Rounded at source: float noise of ~1e-15 sitting on a hypothesis
        # threshold silently flips the verdict (9.999999999999998 < 10 is True
        # while the true value, exactly 10, is not). See REVIEW.md R5.
        delta = round(100 * (p1_sv.value - p1_base.value), 9)

    out = {
        "n_records": len(records),
        "providers": sorted({r["provider"] for r in records}),
        "models_resolved": sorted({r["model_resolved"] for r in records}),
        "k": k,
        "by_mode": {},
        "false_green_rate": false_green_rate(records).to_dict(),
        "false_red_rate": false_red_rate(records).to_dict(),
        "verifier_accuracy": verifier_accuracy(records).to_dict(),
        "verdict_parse_failure_rate": verdict_parse_failure_rate(records).to_dict(),
        "hardcode_rate": hardcode_rate(records).to_dict(),
        "truncation_rate": truncation_rate(records).to_dict(),
        "delta_pass_at_1_pp": delta,
        "cost_multiplier": (cost_sv / cost_base) if cost_base else None,
        "ece": ece,
        "ece_bins": ece_table,
        "mean_confidence_on_false_greens": mean_conf_fg,
        "n_false_greens": n_fg,
        "per_task": {},
    }

    for name, subset in (("baseline", base), ("self_verify", sv)):
        in_tok, out_tok = total_tokens(subset)
        out["by_mode"][name] = {
            "n": len(subset),
            "pass_at_1": pass_at_1(subset).to_dict(),
            "pass_hat_k": pass_hat_k(subset, k).to_dict(),
            "cost_usd": total_cost(subset),
            "cost_per_solved_task": cost_per_solved_task(subset),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cache_hit_tokens": sum(r["tokens"].get("cache_hit", 0) for r in subset),
            "reasoning_tokens": sum(r["tokens"].get("reasoning", 0) for r in subset),
            "mean_wall_clock_s": (
                sum(r["wall_clock_s"] for r in subset) / len(subset) if subset else None
            ),
        }

    # Per-task breakdown is always reported; aggregates never stand alone.
    for tid in sorted({r["task_id"] for r in records}):
        t_base = [r for r in base if r["task_id"] == tid]
        t_sv = [r for r in sv if r["task_id"] == tid]
        fg_denom = [r for r in t_sv if r["truth_initial"] != "correct"]
        fg_num = [r for r in fg_denom if r["verdict"] == "correct"]
        out["per_task"][tid] = {
            "task_name": next((r["task_name"] for r in records if r["task_id"] == tid), tid),
            "task_type": next((r["task_type"] for r in records if r["task_id"] == tid), ""),
            "baseline_pass_at_1": pass_at_1(t_base).to_dict(),
            "self_verify_pass_at_1": pass_at_1(t_sv).to_dict(),
            "false_green": Rate(len(fg_num), len(fg_denom)).to_dict(),
        }
    return out
