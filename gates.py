#!/usr/bin/env python3
"""Phase gates for agent-eval-labs.

Every phase of an experiment ends with a gate. A gate is a named collection of
checks; it passes only when every check passes. `gates.py` exits 0 on pass and 1
on failure, so it is usable directly in CI and as a hard stop between phases.

Usage:
    python gates.py --list
    python gates.py --gate G0
    python gates.py --all
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent
EXP = ROOT / "experiments" / "verifier-gap"

# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #


@dataclass
class Check:
    """One assertion inside a gate."""

    name: str
    ok: bool
    detail: str = ""


CheckFn = Callable[[], Iterable[Check]]
REGISTRY: dict[str, tuple[str, CheckFn]] = {}


def gate(gate_id: str, title: str) -> Callable[[CheckFn], CheckFn]:
    """Register a gate function under `gate_id`."""

    def decorate(fn: CheckFn) -> CheckFn:
        if gate_id in REGISTRY:
            raise RuntimeError(f"duplicate gate id: {gate_id}")
        REGISTRY[gate_id] = (title, fn)
        return fn

    return decorate


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def interpreter() -> str:
    """Interpreter used for subprocess checks: the repo venv when it exists."""
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )


def count_collected(stdout: str) -> int:
    """Count tests in `pytest --collect-only -q` output.

    pytest <9 prints one `path::test` line per test; pytest >=9 prints one
    `path: <count>` line per file. Handle both so the gate is version-stable.
    """
    per_file = re.findall(r"^\S+\.py: (\d+)$", stdout, re.MULTILINE)
    if per_file:
        return sum(int(n) for n in per_file)
    return sum(1 for line in stdout.splitlines() if "::" in line)


def exists(rel: str, kind: str = "any") -> Check:
    """Check that a repo-relative path exists (kind: file | dir | any)."""
    p = ROOT / rel
    if not p.exists():
        return Check(f"exists: {rel}", False, "missing")
    if kind == "file" and not p.is_file():
        return Check(f"exists: {rel}", False, "not a file")
    if kind == "dir" and not p.is_dir():
        return Check(f"exists: {rel}", False, "not a directory")
    return Check(f"exists: {rel}", True)


# --------------------------------------------------------------------------- #
# G0 — scaffold
# --------------------------------------------------------------------------- #


@gate("G0", "Scaffold: git repo, structure, pytest collects")
def gate_g0() -> list[Check]:
    checks: list[Check] = []

    # 1. git repository exists
    proc = run(["git", "rev-parse", "--is-inside-work-tree"])
    checks.append(
        Check(
            "git repository initialised",
            proc.returncode == 0 and proc.stdout.strip() == "true",
            proc.stderr.strip() or proc.stdout.strip(),
        )
    )

    # 2. structure present
    checks.append(exists("pyproject.toml", "file"))
    checks.append(exists(".gitignore", "file"))
    checks.append(exists("gates.py", "file"))
    checks.append(exists("Makefile", "file"))
    checks.append(exists("experiments/verifier-gap", "dir"))
    checks.append(exists("experiments/verifier-gap/tasks", "dir"))
    checks.append(exists("experiments/verifier-gap/results", "dir"))
    checks.append(exists("tests", "dir"))

    # 3. pytest collects at least one test
    proc = run([interpreter(), "-m", "pytest", "--collect-only", "-q"])
    collected = proc.returncode == 0 and "error" not in proc.stdout.lower()
    n_tests = count_collected(proc.stdout)
    checks.append(
        Check(
            "pytest collects cleanly",
            collected,
            (proc.stdout + proc.stderr).strip()[-400:] if not collected else "",
        )
    )
    checks.append(
        Check(f"pytest collected {n_tests} test(s)", n_tests > 0, "no tests found")
    )

    return checks


# --------------------------------------------------------------------------- #
# G1 — RESEARCH.md is machine-checkable
# --------------------------------------------------------------------------- #

RESEARCH_MD = EXP / "RESEARCH.md"
N_TASKS = 10


def split_sections(md: str, level: int) -> dict[str, str]:
    """Split markdown into {heading_text: body} for headings at `level`."""
    pat = re.compile(rf"^{'#' * level} +(.+?)\s*$", re.MULTILINE)
    out: dict[str, str] = {}
    marks = list(pat.finditer(md))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(md)
        out[m.group(1).strip()] = md[m.end() : end]
    return out


def section_body(md: str, title_prefix: str, level: int = 2) -> str:
    """Body of the level-N section whose title starts with `title_prefix`."""
    for title, body in split_sections(md, level).items():
        if title.lower().startswith(title_prefix.lower()):
            return body
    return ""


@gate("G1", "RESEARCH.md: hypotheses have numbers, metrics have formulas, tasks have asserts")
def gate_g1() -> list[Check]:
    checks: list[Check] = []
    checks.append(exists("experiments/verifier-gap/RESEARCH.md", "file"))
    if not RESEARCH_MD.exists():
        return checks
    md = RESEARCH_MD.read_text()

    # --- hypotheses ------------------------------------------------------- #
    hyp_body = section_body(md, "Hypotheses")
    hyps = {k: v for k, v in split_sections(hyp_body, 3).items() if re.match(r"^H\d+\b", k)}
    checks.append(
        Check(f"hypotheses found: {len(hyps)}", len(hyps) >= 3, "need at least 3 (H1, H2, H3)")
    )
    for name, body in sorted(hyps.items()):
        hid = name.split()[0]
        # a threshold line carrying at least one number
        thr = re.search(r"^\s*-\s*\*\*Threshold:\*\*(.+)$", body, re.MULTILINE)
        has_num = bool(thr and re.search(r"-?\d+(\.\d+)?", thr.group(1)))
        checks.append(
            Check(
                f"{hid}: numeric threshold",
                has_num,
                "missing '- **Threshold:**' line with a number",
            )
        )
        # an explicit falsification condition
        fal = re.search(r"^\s*-\s*\*\*Falsified if:\*\*(.+)$", body, re.MULTILINE)
        checks.append(
            Check(f"{hid}: falsification condition", bool(fal), "missing '- **Falsified if:**'")
        )
        # names the metric that decides it
        met = re.search(r"^\s*-\s*\*\*Metric:\*\*(.+)$", body, re.MULTILINE)
        checks.append(Check(f"{hid}: names a metric", bool(met), "missing '- **Metric:**'"))

    # --- metrics ---------------------------------------------------------- #
    met_body = section_body(md, "Metric definitions")
    metrics = split_sections(met_body, 3)
    checks.append(
        Check(f"metrics found: {len(metrics)}", len(metrics) >= 5, "need at least 5 metrics")
    )
    required = {
        "pass_at_1",
        "pass_hat_k",
        "false_green_rate",
        "cost_per_solved_task",
        "ece",
    }
    missing = sorted(m for m in required if not any(m in k for k in metrics))
    checks.append(
        Check("required metrics defined", not missing, f"missing: {', '.join(missing)}")
    )
    for name, body in metrics.items():
        has_formula = bool(re.search(r"\*\*Formula:\*\*", body))
        checks.append(
            Check(f"metric '{name}': has formula", has_formula, "missing '- **Formula:**' line")
        )

    # every hypothesis must reference a metric that is actually defined
    metric_names = {re.sub(r"[^a-z0-9_]", "", k.lower()) for k in metrics}
    for name, body in sorted(hyps.items()):
        hid = name.split()[0]
        met = re.search(r"^\s*-\s*\*\*Metric:\*\*(.+)$", body, re.MULTILINE)
        referenced = re.findall(r"`([a-z0-9_]+)`", met.group(1)) if met else []
        ok = bool(referenced) and all(
            any(r in m or m in r for m in metric_names) for r in referenced
        )
        checks.append(
            Check(
                f"{hid}: metric is defined in Metric definitions",
                ok,
                f"referenced {referenced} but defined metrics are {sorted(metric_names)}",
            )
        )

    # --- tasks ------------------------------------------------------------ #
    task_body = section_body(md, "Task design")
    tasks = {k: v for k, v in split_sections(task_body, 3).items() if re.match(r"^T\d{2}\b", k)}
    ids = [k.split()[0] for k in tasks]
    checks.append(Check(f"tasks found: {len(tasks)}", len(tasks) == N_TASKS, f"expected {N_TASKS}"))
    checks.append(Check("task ids unique", len(set(ids)) == len(ids), f"ids: {ids}"))
    checks.append(
        Check(
            "task ids are T01..T10",
            sorted(ids) == [f"T{i:02d}" for i in range(1, N_TASKS + 1)],
            f"got {sorted(ids)}",
        )
    )
    for name, body in sorted(tasks.items()):
        tid = name.split()[0]
        checks.append(
            Check(
                f"{tid}: silent-failure mode",
                bool(re.search(r"\*\*Silent-failure mode:\*\*", body)),
                "missing '- **Silent-failure mode:**'",
            )
        )
        spec = re.search(r"\*\*Assert spec:\*\*.*?```text\n(.*?)```", body, re.DOTALL)
        n_asserts = (
            len([ln for ln in spec.group(1).splitlines() if ln.strip()]) if spec else 0
        )
        checks.append(
            Check(
                f"{tid}: assert spec with >=3 cases (got {n_asserts})",
                n_asserts >= 3,
                "missing '- **Assert spec:**' followed by a ```text block",
            )
        )
        checks.append(
            Check(
                f"{tid}: declares a task type",
                bool(re.search(r"\*\*Type:\*\*", body)),
                "missing '- **Type:**'",
            )
        )

    # --- no LLM judges anywhere in the design ----------------------------- #
    banned = re.findall(r"(?i)\bllm[- ]as[- ]a?[- ]?judge\b|\bmodel[- ]graded\b", md)
    checks.append(
        Check("no LLM-judge ground truth in design", not banned, f"found: {banned}")
    )

    return checks


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def _color(s: str, c: str) -> str:
    return s if not sys.stdout.isatty() else f"{c}{s}{RESET}"


def run_gate(gate_id: str) -> bool:
    if gate_id not in REGISTRY:
        print(f"unknown gate: {gate_id}. known: {', '.join(sorted(REGISTRY))}")
        return False
    title, fn = REGISTRY[gate_id]
    print(f"\n=== {gate_id}: {title} ===")
    checks = list(fn())
    for c in checks:
        mark = _color("PASS", GREEN) if c.ok else _color("FAIL", RED)
        print(f"  [{mark}] {c.name}")
        if c.detail and not c.ok:
            for line in c.detail.splitlines():
                print(f"         {_color(line, DIM)}")
    passed = all(c.ok for c in checks) and len(checks) > 0
    n_ok = sum(1 for c in checks if c.ok)
    verdict = _color("GATE PASSED", GREEN) if passed else _color("GATE FAILED", RED)
    print(f"  -> {verdict} ({n_ok}/{len(checks)} checks)")
    return passed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gate", help="gate id to run, e.g. G0")
    ap.add_argument("--all", action="store_true", help="run every registered gate")
    ap.add_argument("--list", action="store_true", help="list registered gates")
    args = ap.parse_args(argv)

    if args.list:
        for gid in sorted(REGISTRY):
            print(f"{gid}\t{REGISTRY[gid][0]}")
        return 0

    if args.all:
        results = {gid: run_gate(gid) for gid in sorted(REGISTRY)}
        print("\n=== summary ===")
        for gid, ok in results.items():
            print(f"  {gid}: {'PASS' if ok else 'FAIL'}")
        return 0 if all(results.values()) else 1

    if args.gate:
        return 0 if run_gate(args.gate.upper()) else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
