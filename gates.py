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
import json
import re
import shlex
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
# G2 — PLAN.md: every task has a runnable verification command
# --------------------------------------------------------------------------- #

PLAN_MD = EXP / "PLAN.md"

# Commands the gate is willing to execute itself. Anything else is checked for
# shape only.
ALLOWED_RUNNERS = {".venv/bin/python", "python", "python3", "make", "pytest"}

# Never executed by the gate: these cost money or mutate published results.
NEVER_EXECUTE = ("--live", "run-live", "reproduce-live")


def parse_plan_tasks(md: str) -> dict[str, dict]:
    """Extract {task_id: {deliverable, acceptance, command}} from PLAN.md."""
    body = section_body(md, "Tasks")
    out: dict[str, dict] = {}
    for title, sec in split_sections(body, 3).items():
        tid = title.split()[0]
        if not re.match(r"^P\d+\.\d+$", tid):
            continue
        cmd = re.search(r"\*\*Verify:\*\*\s*\n+```bash\n(.*?)```", sec, re.DOTALL)
        out[tid] = {
            "title": title,
            "deliverable": bool(re.search(r"\*\*Deliverable:\*\*", sec)),
            "acceptance": bool(re.search(r"\*\*Acceptance:\*\*", sec)),
            "command": cmd.group(1).strip() if cmd else None,
            "paths": re.findall(r"`([^`]+\.(?:py|yaml|md|json))`", sec),
        }
    return out


def command_targets(cmd: str) -> list[str]:
    """Repo-relative file arguments a command references."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return []
    return [p for p in parts[1:] if "/" in p and not p.startswith("-") and not p.startswith("/")]


@gate("G2", "PLAN.md: every task has a runnable verification command")
def gate_g2() -> list[Check]:
    checks: list[Check] = []
    checks.append(exists("experiments/verifier-gap/PLAN.md", "file"))
    if not PLAN_MD.exists():
        return checks
    md = PLAN_MD.read_text()

    # --- experiment matrix arithmetic ------------------------------------- #
    matrix = section_body(md, "Experiment matrix")
    nums = [int(n) for n in re.findall(r"\|\s*\*{0,2}(\d+)\*{0,2}\s*\|", matrix)]
    checks.append(
        Check(
            "matrix declares tasks/modes/runs/records",
            len(nums) >= 4,
            f"parsed numbers: {nums}",
        )
    )
    if len(nums) >= 4:
        tasks_n, modes_n, runs_n, records_n = nums[0], nums[1], nums[2], nums[3]
        checks.append(
            Check(
                f"matrix arithmetic {tasks_n}x{modes_n}x{runs_n}={records_n}",
                tasks_n * modes_n * runs_n == records_n,
                f"{tasks_n}*{modes_n}*{runs_n} = {tasks_n * modes_n * runs_n}, declared {records_n}",
            )
        )
        checks.append(
            Check(
                "matrix task count matches RESEARCH.md",
                tasks_n == N_TASKS,
                f"plan says {tasks_n}, research defines {N_TASKS}",
            )
        )

    # --- per-task structure ----------------------------------------------- #
    tasks = parse_plan_tasks(md)
    checks.append(Check(f"plan tasks found: {len(tasks)}", len(tasks) >= 5, "expected >= 5"))

    executed = 0
    for tid, t in sorted(tasks.items()):
        checks.append(Check(f"{tid}: has deliverable", t["deliverable"], "missing '- **Deliverable:**'"))
        checks.append(Check(f"{tid}: has acceptance criteria", t["acceptance"], "missing '- **Acceptance:**'"))

        cmd = t["command"]
        if not cmd:
            checks.append(Check(f"{tid}: has verification command", False, "missing ```bash block after '- **Verify:**'"))
            continue

        # one command, parseable, and driven by a known runner
        single = "\n" not in cmd.strip()
        try:
            parts = shlex.split(cmd)
            parseable = bool(parts)
        except ValueError as exc:
            parts, parseable = [], False
            checks.append(Check(f"{tid}: command parses", False, str(exc)))
        checks.append(Check(f"{tid}: exactly one command", single, f"got: {cmd!r}"))
        checks.append(
            Check(
                f"{tid}: known runner ({parts[0] if parts else '?'})",
                parseable and parts[0] in ALLOWED_RUNNERS,
                f"first token must be one of {sorted(ALLOWED_RUNNERS)}",
            )
        )

        # execute it when it is offline and its targets already exist
        targets = command_targets(cmd)
        unsafe = any(tok in cmd for tok in NEVER_EXECUTE)
        missing = [t_ for t_ in targets if not (ROOT / t_).exists()]
        # A `gates.py --gate GN` command is pending until GN is registered:
        # the file exists from Phase 0, but the gate itself lands with its phase.
        gate_ref = re.search(r"--gate\s+(G\d+)", cmd)
        if gate_ref and gate_ref.group(1) not in REGISTRY:
            missing.append(f"gate {gate_ref.group(1)} not yet registered")
        if unsafe:
            checks.append(Check(f"{tid}: not auto-executed (live command)", True, ""))
        elif missing:
            checks.append(
                Check(f"{tid}: command runnable once implemented", True, f"pending: {missing}")
            )
        else:
            proc = run(parts, timeout=600)
            executed += 1
            checks.append(
                Check(
                    f"{tid}: verification command passes",
                    proc.returncode == 0,
                    (proc.stdout + proc.stderr).strip()[-600:],
                )
            )

    checks.append(
        Check(
            f"executed {executed} of {len(tasks)} verification commands",
            True,
            "",
        )
    )
    return checks


# --------------------------------------------------------------------------- #
# G3 — implementation: tests green, dry run valid, false green caught,
#      prompts differ only by the verification block
# --------------------------------------------------------------------------- #

REQUIRED_RECORD_KEYS = {
    "schema_version", "record_id", "task_id", "mode", "run_index", "provider",
    "model_requested", "model_resolved", "prompts", "completion_generation",
    "grade_initial", "grade_final", "truth_initial", "truth_final", "verdict",
    "confidence", "calls", "tokens", "cost_usd", "wall_clock_s", "timestamp",
}


def _exp_python() -> list[str]:
    """Interpreter invocation with experiments/verifier-gap importable."""
    return [interpreter()]


def _run_py(code: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run a snippet with the experiment directory on sys.path."""
    preamble = (
        "import sys; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s')\n" % (str(EXP), str(ROOT))
    )
    return subprocess.run(
        [interpreter(), "-c", preamble + code],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout,
    )


@gate("G3", "Implementation: pytest green, valid dry run, false green detected, prompt diff")
def gate_g3() -> list[Check]:
    checks: list[Check] = []

    # --- deliverables ----------------------------------------------------- #
    for rel in (
        "experiments/verifier-gap/config.yaml",
        "experiments/verifier-gap/config.py",
        "experiments/verifier-gap/runner.py",
        "experiments/verifier-gap/metrics.py",
        "experiments/verifier-gap/report.py",
        "experiments/verifier-gap/extract.py",
        "experiments/verifier-gap/grade.py",
        "experiments/verifier-gap/prompts.py",
        "experiments/verifier-gap/verdict.py",
        "experiments/verifier-gap/provider.py",
        "tests/test_false_green.py",
        "tests/test_prompt_diff.py",
    ):
        checks.append(exists(rel, "file"))

    n_task_modules = len(list((EXP / "tasks").glob("t*.py")))
    checks.append(
        Check(f"task modules present: {n_task_modules}", n_task_modules == N_TASKS, f"expected {N_TASKS}")
    )

    # --- the whole suite must be green ------------------------------------ #
    proc = run([interpreter(), "-m", "pytest", "-q"])
    tail = (proc.stdout + proc.stderr).strip()
    checks.append(Check("pytest suite green", proc.returncode == 0, tail[-800:]))

    # --- the two critical tests, named explicitly ------------------------- #
    for label, target in (
        ("synthetic false green is counted", "tests/test_false_green.py"),
        ("prompts differ only by verification block", "tests/test_prompt_diff.py"),
    ):
        proc = run([interpreter(), "-m", "pytest", target, "-q"])
        checks.append(
            Check(label, proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-500:])
        )

    # --- no LLM anywhere in grading --------------------------------------- #
    grading_sources = ["grade.py", "_grade_child.py", "metrics.py"] + [
        f"tasks/{p.name}" for p in sorted((EXP / "tasks").glob("*.py"))
    ]
    leaks = []
    for rel in grading_sources:
        text = (EXP / rel).read_text()
        if re.search(r"\banthropic\b|\bclient\.messages\b", text):
            leaks.append(rel)
    checks.append(
        Check(
            "ground truth never calls a model",
            not leaks,
            f"model access found in grading path: {leaks}",
        )
    )

    # --- dry run produces schema-valid JSON with token counts ------------- #
    tmp = ROOT / ".gate-dry.jsonl"
    if tmp.exists():
        tmp.unlink()
    proc = run(
        [interpreter(), str(EXP / "runner.py"), "--dry-run", "--out", str(tmp), "--quiet"],
        timeout=900,
    )
    ok = proc.returncode == 0 and tmp.exists()
    checks.append(Check("dry run completes", ok, (proc.stdout + proc.stderr)[-500:]))

    if ok:
        records = [json.loads(line) for line in tmp.read_text().splitlines() if line.strip()]
        checks.append(Check(f"dry run wrote {len(records)} records", len(records) == 100, "expected 100"))
        bad_schema = [r["record_id"] for r in records if not REQUIRED_RECORD_KEYS <= set(r)]
        checks.append(Check("every record is schema-valid", not bad_schema, f"bad: {bad_schema[:5]}"))
        no_tokens = [
            r["record_id"]
            for r in records
            if not (r["tokens"]["input"] > 0 and r["tokens"]["output"] > 0)
        ]
        checks.append(Check("every record has token counts", not no_tokens, f"missing: {no_tokens[:5]}"))
        no_timing = [r["record_id"] for r in records if "wall_clock_s" not in r]
        checks.append(Check("every record has wall-clock timing", not no_timing, f"missing: {no_timing[:5]}"))
        checks.append(
            Check(
                "dry-run records are labelled synthetic",
                all(r["provider"] == "mock" for r in records),
                "a mock record is not labelled provider=mock",
            )
        )
        # metrics must consume the dry run without special-casing
        proc = _run_py(
            "import metrics, json;"
            f"r=metrics.load_records(r'{tmp}');"
            "s=metrics.summarize(r,k=5);"
            "print(json.dumps({'n':s['n_records'],'fg':s['false_green_rate']['n']}))"
        )
        checks.append(
            Check("metrics.summarize consumes the dry run", proc.returncode == 0, proc.stderr[-400:])
        )
        tmp.unlink()

    # --- an injected false green is counted, checked here too ------------- #
    proc = _run_py(
        "import metrics;"
        "rec={'mode':'self_verify','truth_initial':'wrong','verdict':'correct','confidence':99};"
        "r=metrics.false_green_rate([rec]);"
        "assert r.numerator==1 and r.value==1.0, r;"
        "print('counted')"
    )
    checks.append(
        Check(
            "gate-level false-green injection is counted",
            proc.returncode == 0 and "counted" in proc.stdout,
            (proc.stdout + proc.stderr)[-400:],
        )
    )

    # --- prompt diff, checked independently of the test suite ------------- #
    proc = _run_py(
        "import prompts;"
        "from tasks import load_tasks;"
        "t=load_tasks()[0];"
        "base=prompts.generation_messages(t);"
        "sv=prompts.verification_messages(t,'A');"
        "assert sv[:len(base)]==base, 'generation turn differs';"
        "assert sv[-1]['content']==prompts.VERIFICATION_BLOCK, 'unexpected trailing turn';"
        "assert sv[:-2]==base, 'baseline not recoverable';"
        "print('identical')"
    )
    checks.append(
        Check(
            "generation prompt identical across modes",
            proc.returncode == 0 and "identical" in proc.stdout,
            (proc.stdout + proc.stderr)[-400:],
        )
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
