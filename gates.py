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
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import yaml

ROOT = Path(__file__).resolve().parent
# Set while a gate is executing, so a gate cannot be re-entered from inside the
# pytest run it launched.
GATE_ENV = "AELABS_IN_GATE"
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
# Gates that cannot pass without a real API run. They are never silently
# skipped: --offline names them in its output and `--all` still runs them.
REQUIRES_LIVE: set[str] = set()


def gate(gate_id: str, title: str, requires_live: bool = False) -> Callable[[CheckFn], CheckFn]:
    """Register a gate function under `gate_id`."""

    def decorate(fn: CheckFn) -> CheckFn:
        if gate_id in REGISTRY:
            raise RuntimeError(f"duplicate gate id: {gate_id}")
        REGISTRY[gate_id] = (title, fn)
        if requires_live:
            REQUIRES_LIVE.add(gate_id)
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
        # A short note may sit between the label and the fence.
        cmd = re.search(r"\*\*Verify:\*\*.*?```bash\n(.*?)```", sec, re.DOTALL)
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
        # A `gates.py --gate GN` command belongs to phase N, not to this gate.
        # G2's job is that the plan is well-formed and its commands run; whether
        # phase 4 has happened is G4's verdict to give, not G2's.
        gate_ref = re.search(r"--gate\s+(G\d+)", cmd)
        delegated = None
        if gate_ref:
            target_gate = gate_ref.group(1)
            if target_gate not in REGISTRY:
                missing.append(f"gate {target_gate} not yet registered")
            elif int(target_gate[1:]) > 2:
                delegated = target_gate
        if delegated:
            checks.append(
                Check(f"{tid}: verification delegated to {delegated}", True, "")
            )
        elif unsafe:
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
    # The record must carry a verification prompt: that is how metrics decides a
    # record was verified, and the fixture has to match what the runner writes.
    proc = _run_py(
        "import metrics;"
        "rec={'mode':'self_verify','truth_initial':'wrong','verdict':'correct',"
        "'confidence':99,'prompts':{'verification':'v'}};"
        "r=metrics.false_green_rate([rec]);"
        "assert r.numerator==1 and r.value==1.0, r;"
        "inj={'mode':'inject_wrong','truth_initial':'wrong','verdict':'correct',"
        "'confidence':99,'prompts':{'verification':'v'}};"
        "r2=metrics.false_green_rate([inj]);"
        "assert r2.numerator==1, r2;"
        "print('counted')"
    )
    checks.append(
        Check(
            "gate-level false-green injection is counted in both arms",
            proc.returncode == 0 and "counted" in proc.stdout,
            (proc.stdout + proc.stderr)[-400:],
        )
    )

    # --- the attack probe must find no way to forge a pass ---------------- #
    probe = ROOT / "tools" / "attack_probe.py"
    if probe.exists():
        proc = run([interpreter(), str(probe)])
        breaches = [
            ln for ln in proc.stdout.splitlines() if "BREACH" in ln
        ]
        checks.append(
            Check(
                "attack probe finds no forged-pass vector",
                proc.returncode == 0 and not breaches,
                "\n".join(breaches) or (proc.stdout + proc.stderr)[-400:],
            )
        )
    else:
        checks.append(Check("attack probe present", False, "tools/attack_probe.py missing"))

    # --- held-out asserts exist for every task ---------------------------- #
    proc = _run_py(
        "from tasks import load_tasks;"
        "bad=[t['id'] for t in load_tasks() if len(t.get('hidden_asserts',[]))<3];"
        "print('MISSING:'+','.join(bad) if bad else 'ok')"
    )
    checks.append(
        Check(
            "every task has held-out asserts",
            proc.returncode == 0 and "ok" in proc.stdout,
            (proc.stdout + proc.stderr)[-300:],
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
# G4 — run and calibration
# --------------------------------------------------------------------------- #

RESULTS_DIR = EXP / "results"


def live_result_files() -> list[Path]:
    """Generation-arm results from live runs, newest last."""
    return sorted(
        f for f in RESULTS_DIR.glob("run-live-*.jsonl") if "-inject-" not in f.name
    )


def inject_result_files() -> list[Path]:
    """Injection-arm results from live runs, newest last."""
    return sorted(RESULTS_DIR.glob("run-live-inject-*.jsonl"))


def read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def recompute_false_green_rate(records: list[dict]) -> tuple[int, int]:
    """Independent reimplementation of the headline metric.

    Deliberately does NOT import metrics.py: the point of this check is to
    catch a report that no longer matches its raw data, which a shared
    implementation could not detect.
    """
    denom = [
        r for r in records
        if (r.get("prompts") or {}).get("verification")
        and r.get("truth_initial") != "correct"
    ]
    num = [r for r in denom if r.get("verdict") == "correct"]
    return len(num), len(denom)


def recompute_pass_at_1(records: list[dict], mode: str) -> tuple[int, int]:
    subset = [r for r in records if r.get("mode") == mode]
    return sum(1 for r in subset if r.get("truth_final") == "correct"), len(subset)


@gate(
    "G4",
    "Run: 100 live records with tokens, baseline pass@1 in range, report matches raw data",
    requires_live=True,
)
def gate_g4() -> list[Check]:
    checks: list[Check] = []
    cfg_path = EXP / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
    cal = cfg.get("calibration", {})
    lo = float(cal.get("baseline_pass_at_1_min", 0.50))
    hi = float(cal.get("baseline_pass_at_1_max", 0.70))
    max_parse_fail = float(cfg.get("thresholds", {}).get("max_verdict_parse_failure_rate", 0.02))

    files = live_result_files()
    checks.append(
        Check(
            f"live results file present ({len(files)} found)",
            bool(files),
            "no experiments/verifier-gap/results/run-live-*.jsonl — Phase 4 has not run",
        )
    )
    if not files:
        return checks

    path = files[-1]
    records = read_records(path)
    checks.append(Check(f"{path.name}: 100 records", len(records) == 100, f"got {len(records)}"))

    # --- provenance -------------------------------------------------------- #
    expected_provider = cfg.get("provider", "anthropic")
    providers = sorted({r.get("provider") for r in records})
    checks.append(
        Check(
            f"records come from the configured live provider ({expected_provider})",
            providers == [expected_provider],
            f"providers present: {providers} (mock output is not a result)",
        )
    )
    models = sorted({r.get("model_resolved") for r in records})
    checks.append(
        Check(
            f"single resolved model ({models[0] if models else '?'})",
            len(models) == 1,
            f"run spans multiple models: {models}",
        )
    )

    # --- token accounting -------------------------------------------------- #
    missing_tokens = [
        r["record_id"] for r in records
        if not (r.get("tokens", {}).get("input", 0) > 0 and r.get("tokens", {}).get("output", 0) > 0)
    ]
    checks.append(
        Check("every record has non-zero token counts", not missing_tokens, f"{missing_tokens[:5]}")
    )
    missing_timing = [r["record_id"] for r in records if r.get("wall_clock_s") is None]
    checks.append(Check("every record has wall-clock timing", not missing_timing, f"{missing_timing[:5]}"))

    expected_calls = {"baseline": 1, "self_verify": 2}
    bad_calls = [
        r["record_id"] for r in records
        if len(r.get("calls", [])) != expected_calls.get(r.get("mode"), -1)
    ]
    checks.append(Check("call counts match the mode", not bad_calls, f"{bad_calls[:5]}"))

    # --- calibration ------------------------------------------------------- #
    # The 50-70% window exists for ONE reason, stated in RESEARCH.md: above it
    # there are too few wrong answers to compute a false-green rate over. The
    # injection arm supplies wrong answers by construction, so it satisfies that
    # purpose directly. Either route is accepted, and the check says which one
    # applied — a run that missed the window must never read as if it hit it.
    k, n = recompute_pass_at_1(records, "baseline")
    p1 = k / n if n else None
    in_window = p1 is not None and lo <= p1 <= hi

    inject_files = inject_result_files()
    inject_records = read_records(inject_files[-1]) if inject_files else []
    n_wrong_shown = len(
        [r for r in inject_records if r.get("truth_initial") != "correct"]
    )
    min_wrong = 40

    if in_window:
        detail = ""
        label = f"calibration: baseline pass@1 = {p1:.1%} in [{lo:.0%}, {hi:.0%}]"
        ok = True
    elif n_wrong_shown >= min_wrong:
        label = (
            f"calibration: baseline pass@1 = {p1:.1%} is OUTSIDE [{lo:.0%}, {hi:.0%}]; "
            f"satisfied instead by the injection arm's {n_wrong_shown} controlled wrong "
            f"answers (RESEARCH.md Amendment A5)"
        )
        ok = True
        detail = ""
    else:
        label = f"calibration: baseline pass@1 = {p1:.1%}" if p1 is not None else "calibration"
        ok = False
        detail = (
            f"outside [{lo:.0%}, {hi:.0%}] and the injection arm shows only "
            f"{n_wrong_shown} wrong answers (need >= {min_wrong}). Adjust task "
            f"difficulty or run the injection arm, and record it in CALIBRATION.md."
        )
    checks.append(Check(label, ok, detail))
    checks.append(exists("experiments/verifier-gap/CALIBRATION.md", "file"))

    # --- harness health ---------------------------------------------------- #
    sv = [r for r in records if r.get("mode") == "self_verify"]
    unparsed = [r for r in sv if r.get("verdict") is None]
    rate = len(unparsed) / len(sv) if sv else 1.0
    checks.append(
        Check(
            f"verdict parse failure rate {rate:.1%} <= {max_parse_fail:.0%}",
            rate <= max_parse_fail,
            f"{len(unparsed)} of {len(sv)} verification responses could not be parsed",
        )
    )

    truncated = [r["record_id"] for r in records if r.get("truncated")]
    trunc_rate = len(truncated) / len(records) if records else 1.0
    max_trunc = float(cfg.get("thresholds", {}).get("max_truncation_rate", 0.02))
    checks.append(
        Check(
            f"truncation rate {trunc_rate:.1%} <= {max_trunc:.0%}",
            trunc_rate <= max_trunc,
            f"{len(truncated)} records hit the output cap: {truncated[:5]} — raise "
            f"max_tokens; a truncated answer is not a model failure",
        )
    )

    # --- injection arm ----------------------------------------------------- #
    checks.append(
        Check(
            f"injection arm present ({len(inject_files)} file(s))",
            bool(inject_files),
            "no run-live-inject-*.jsonl — H1/H3/H5 cannot be decided without it",
        )
    )
    if inject_records:
        checks.append(
            Check(
                f"injection arm: {len(inject_records)} records",
                len(inject_records) == 100,
                f"expected 100, got {len(inject_records)}",
            )
        )
        n_correct_shown = len(inject_records) - n_wrong_shown
        checks.append(
            Check(
                f"injection denominator: {n_wrong_shown} wrong / {n_correct_shown} correct",
                n_wrong_shown >= min_wrong and n_correct_shown >= min_wrong,
                "both conditions need enough records to bound a rate",
            )
        )
        # The injected artifacts' ground truth is asserted, never assumed.
        mislabelled = [
            r["record_id"] for r in inject_records
            if r.get("injected_source") == "silent_failure" and r.get("truth_initial") == "correct"
        ]
        checks.append(
            Check(
                "every injected silent-failure artifact really is wrong",
                not mislabelled,
                f"these graded CORRECT despite being the planted bug: {mislabelled[:5]}",
            )
        )
        inj_unparsed = [r for r in inject_records if r.get("verdict") is None]
        inj_rate = len(inj_unparsed) / len(inject_records)
        checks.append(
            Check(
                f"injection arm verdict parse failure {inj_rate:.1%} <= {max_parse_fail:.0%}",
                inj_rate <= max_parse_fail,
                f"{len(inj_unparsed)} unparseable verdicts",
            )
        )

    # --- report exists and matches the raw data ---------------------------- #
    checks.append(exists("experiments/verifier-gap/RESULTS.md", "file"))
    checks.append(exists("docs/assets/fig1_rates_by_mode.png", "file"))
    checks.append(exists("docs/assets/fig2_calibration.png", "file"))

    results_md = EXP / "RESULTS.md"
    if results_md.exists():
        md = results_md.read_text()
        checks.append(
            Check(
                "report was generated from this run",
                path.name in md,
                f"RESULTS.md cites a different source than {path.name}",
            )
        )
        checks.append(
            Check(
                "report is not labelled synthetic",
                "SYNTHETIC DATA" not in md,
                "RESULTS.md still carries the mock-data banner",
            )
        )

        # Independent recomputation of the headline metric, from the arm that
        # actually produced wrong answers.
        fg_k, fg_n = recompute_false_green_rate(inject_records or records)
        expected = 100 * fg_k / fg_n if fg_n else None
        published = re.search(
            r"\*\*false-green rate\*\*\s*\|\s*\*\*([\d.]+)%", md
        )
        if expected is None:
            checks.append(Check("false-green rate recomputation", False, "no wrong answers to verify"))
        elif not published:
            checks.append(Check("false-green rate published in report", False, "not found in RESULTS.md"))
        else:
            delta = abs(float(published.group(1)) - expected)
            checks.append(
                Check(
                    f"gate recomputes false-green rate independently: {expected:.1f}% "
                    f"(report says {published.group(1)}%)",
                    delta < 0.05,
                    f"report disagrees with raw data by {delta:.2f}pp — "
                    f"recomputed {fg_k}/{fg_n}",
                )
            )

    return checks


# --------------------------------------------------------------------------- #
# G5 — adversarial review
# --------------------------------------------------------------------------- #

REVIEW_MD = EXP / "REVIEW.md"

# The four risks Phase 5 is required to address, and a phrase that must appear.
REQUIRED_RISKS = {
    "R1": "harness",
    "R2": "format",
    "R3": "seed",
    "R4": "sensitiv",
}

VALID_VERDICTS = {"FIXED", "CLEAR", "SCOPED", "ACCEPTED", "PENDING LIVE DATA"}


@gate("G5", "REVIEW.md: every risk has a verdict and a proof that actually runs")
def gate_g5() -> list[Check]:
    checks: list[Check] = []
    checks.append(exists("experiments/verifier-gap/REVIEW.md", "file"))
    if not REVIEW_MD.exists():
        return checks
    md = REVIEW_MD.read_text()

    # --- the risk table --------------------------------------------------- #
    rows = re.findall(r"^\|\s*(R[\d.]+[a-z]?)\s+(.+?)\s*\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|$",
                      md, re.MULTILINE)
    checks.append(Check(f"risk rows found: {len(rows)}", len(rows) >= 4, "expected at least 4"))

    seen_ids = {r[0] for r in rows}
    for prefix, phrase in REQUIRED_RISKS.items():
        covered = any(rid.startswith(prefix) for rid in seen_ids)
        checks.append(
            Check(f"required risk {prefix} is addressed", covered, f"no row starting with {prefix}")
        )
        section = re.search(rf"^## {prefix}\b.*?$(.*?)(?=^## |\Z)", md, re.MULTILINE | re.DOTALL)
        checks.append(
            Check(
                f"risk {prefix} has a discussion section mentioning '{phrase}'",
                bool(section) and phrase.lower() in section.group(1).lower(),
                "missing section or the section never mentions the risk's subject",
            )
        )

    # --- each row: a verdict from the allowed set, and a proof ------------- #
    proofs: list[tuple[str, str]] = []
    for rid, _title, verdict, proof in rows:
        checks.append(
            Check(
                f"{rid}: verdict '{verdict}' is a known verdict",
                verdict.strip() in VALID_VERDICTS,
                f"must be one of {sorted(VALID_VERDICTS)}",
            )
        )
        target = re.search(r"`([^`]+)`", proof)
        checks.append(Check(f"{rid}: cites a proof", bool(target), f"no code reference in {proof!r}"))
        if target:
            proofs.append((rid, target.group(1)))

    # --- every cited proof must exist, and every cited test must pass ------ #
    node_ids: list[tuple[str, str]] = []
    for rid, ref in proofs:
        path_part = ref.split("::", 1)[0]
        checks.append(
            Check(
                f"{rid}: {path_part} exists",
                (ROOT / path_part).exists() or (EXP / path_part).exists(),
                f"cited proof file not found: {path_part}",
            )
        )
        if "::" in ref:
            node_ids.append((rid, ref))

    if node_ids:
        proc = run([interpreter(), "-m", "pytest", "-q", *[n for _, n in node_ids]])
        checks.append(
            Check(
                f"all {len(node_ids)} cited tests pass",
                proc.returncode == 0,
                (proc.stdout + proc.stderr).strip()[-800:],
            )
        )
        # A cited test that does not exist makes pytest error, not just fail.
        checks.append(
            Check(
                "no cited test is missing",
                "no tests ran" not in proc.stdout and "ERROR" not in proc.stdout,
                (proc.stdout + proc.stderr).strip()[-500:],
            )
        )

    # --- the review must not claim more than it proved -------------------- #
    unresolved = [rid for rid, _t, verdict, _p in rows if verdict.strip() == "PENDING LIVE DATA"]
    checks.append(
        Check(
            f"pending risks are declared, not hidden ({len(unresolved)} pending)",
            True,
            "",
        )
    )
    checks.append(
        Check(
            "review states the threats it does not remove",
            "does not remove" in md.lower() or "threats this review" in md.lower(),
            "missing a section on residual threats",
        )
    )

    return checks


# --------------------------------------------------------------------------- #
# G6 — ship
# --------------------------------------------------------------------------- #

README = ROOT / "README.md"

REQUIRED_README_SECTIONS = [
    "## Motivation",
    "## Method",
    "## Results",
    "## Reproduction",
]


@gate("G6", "Ship: README complete with CIs, charts embedded, reproduce-dry works")
def gate_g6() -> list[Check]:
    checks: list[Check] = []
    checks.append(exists("README.md", "file"))
    checks.append(exists("Makefile", "file"))
    if not README.exists():
        return checks
    md = README.read_text()

    # --- structure --------------------------------------------------------- #
    for heading in REQUIRED_README_SECTIONS:
        checks.append(Check(f"README has {heading}", heading in md, "missing section"))

    limitations = re.search(r"^## (What this experiment does \*not\* show|Limitations).*?$(.*?)(?=^## |\Z)",
                            md, re.MULTILINE | re.DOTALL)
    checks.append(Check("README has a limitations section", bool(limitations), "missing"))
    if limitations:
        body = limitations.group(2).lower()
        for topic, needle in (("n", "n = 10"), ("single model", "single capability"),
                              ("task distribution", "task distribution")):
            checks.append(
                Check(f"limitations name the {topic}", needle.lower() in body, f"no mention of {needle!r}")
            )

    # motivation must be prose, not a stub
    motivation = re.search(r"^## Motivation.*?$(.*?)(?=^## |\Z)", md, re.MULTILINE | re.DOTALL)
    paragraphs = [p for p in (motivation.group(1).strip().split("\n\n") if motivation else []) if p.strip()]
    checks.append(
        Check(f"motivation has {len(paragraphs)} paragraphs", len(paragraphs) >= 2, "expected 2")
    )

    # --- generated results block ------------------------------------------ #
    begin, end = "<!-- BEGIN GENERATED RESULTS -->", "<!-- END GENERATED RESULTS -->"
    has_markers = begin in md and end in md
    checks.append(Check("README results block is script-generated", has_markers, "markers missing"))
    block = md.split(begin, 1)[1].split(end, 1)[0] if has_markers else ""
    checks.append(Check("results block is populated", bool(block.strip()), "run report.py"))

    # --- CIs, not bare point estimates ------------------------------------ #
    intervals = re.findall(r"\d+\.\d+% \[\d+\.\d+, \d+\.\d+\]", block)
    checks.append(
        Check(
            f"results carry confidence intervals ({len(intervals)} found)",
            len(intervals) >= 4,
            "rates must be published as 'x% [lo, hi]', not point estimates alone",
        )
    )
    checks.append(
        Check(
            "the interval method is named",
            "Wilson" in block or "Wilson" in md,
            "say which interval is being reported",
        )
    )

    # --- charts embedded and present -------------------------------------- #
    embedded = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    checks.append(Check(f"charts embedded in README ({len(embedded)})", len(embedded) >= 2, f"{embedded}"))
    for rel in embedded:
        checks.append(exists(rel, "file"))

    # --- honesty invariant: synthetic results must be declared ------------- #
    synthetic = "SYNTHETIC DATA" in block
    if synthetic:
        checks.append(
            Check(
                "synthetic results carry a status banner",
                "## Status" in md and "has not been executed" in md,
                "the results are mocked but the README does not say so outside the table",
            )
        )
    else:
        checks.append(Check("results are from a live run", True, ""))

    # --- one-command reproduction actually works -------------------------- #
    checks.append(
        Check(
            "README documents a one-command reproduction",
            "make reproduce-dry" in md,
            "missing `make reproduce-dry`",
        )
    )
    makefile = (ROOT / "Makefile").read_text()
    checks.append(
        Check("Makefile defines reproduce-dry", "reproduce-dry:" in makefile, "target missing")
    )

    proc = run(["make", "reproduce-dry"], timeout=900)
    checks.append(
        Check(
            "make reproduce-dry succeeds",
            proc.returncode == 0,
            (proc.stdout + proc.stderr).strip()[-800:],
        )
    )
    produced = ROOT / "build" / "reproduce-dry"
    for rel in ("run.jsonl", "RESULTS.md", "assets/fig1_rates_by_mode.png",
                "assets/fig2_calibration.png"):
        checks.append(
            Check(f"reproduce-dry produced {rel}", (produced / rel).exists(), "missing output")
        )
    if (produced / "run.jsonl").exists():
        n = len([ln for ln in (produced / "run.jsonl").read_text().splitlines() if ln.strip()])
        checks.append(Check(f"reproduce-dry wrote {n} records", n == 100, "expected 100"))

    # --- commit history is organised by phase ----------------------------- #
    shallow = (ROOT / ".git" / "shallow").exists()
    proc = run(["git", "log", "--pretty=%s"])
    subjects = proc.stdout.splitlines()
    phases = {m.group(1) for s_ in subjects if (m := re.match(r"Phase (\d+):", s_))}
    checks.append(
        Check(
            f"commit history is organised by phase ({len(phases)} phases)",
            len(phases) >= 5,
            (
                f"only {len(subjects)} commit(s) visible — this is a SHALLOW clone, "
                "so the history exists but is not fetched. In CI set "
                "`actions/checkout` with `fetch-depth: 0`."
                if shallow or len(subjects) <= 2
                else f"found phase commits: {sorted(phases)}"
            ),
        )
    )

    return checks


# --------------------------------------------------------------------------- #
# G7 — experiment 2 substrate: environment, injections, discoverability
# --------------------------------------------------------------------------- #

EXP2 = ROOT / "experiments" / "agent-verifier-gap"


@gate("G7", "Agent substrate: deterministic env, plausible injections, every pair discoverable")
def gate_g7() -> list[Check]:
    checks: list[Check] = []
    for rel in (
        "experiments/agent-verifier-gap/RESEARCH.md",
        "experiments/agent-verifier-gap/PLAN.md",
        "experiments/agent-verifier-gap/env.py",
        "experiments/agent-verifier-gap/fixtures.py",
        "experiments/agent-verifier-gap/inject.py",
        "experiments/agent-verifier-gap/discoverability.py",
    ):
        checks.append(exists(rel, "file"))

    def _run2(code: str) -> subprocess.CompletedProcess:
        preamble = "import sys; sys.path.insert(0, r'%s')\n" % str(EXP2)
        return subprocess.run(
            [interpreter(), "-c", preamble + code],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )

    # --- the environment must be deterministic ----------------------------- #
    proc = _run2(
        "import env;"
        "a=env.Env.fresh().snapshot(); b=env.Env.fresh().snapshot();"
        "assert a==b, (a,b);"
        "e=env.Env.fresh(); before=e.snapshot(); e.set_status('O01','shipped');"
        "assert e.snapshot()!=before, 'mutation did not change the snapshot';"
        "print('deterministic')"
    )
    checks.append(
        Check("environment is deterministic", "deterministic" in proc.stdout,
              (proc.stdout + proc.stderr)[-300:])
    )

    # --- the redundancy detection depends on must hold --------------------- #
    proc = _run2(
        "import env;"
        "e=env.Env.fresh();"
        "bad=[(s,r) for s in (None,'pending','shipped','cancelled') "
        "for r in (None,'EU','US','APAC') "
        "if e.count_orders(s,r)!=len(e.list_orders(s,r))];"
        "assert not bad, bad;"
        "print('redundant routes agree')"
    )
    checks.append(
        Check(
            "count_orders agrees with list_orders on every filter",
            "redundant routes agree" in proc.stdout,
            "the two routes must agree, or a corrupted list is indistinguishable "
            "from ordinary inconsistency: " + (proc.stdout + proc.stderr)[-300:],
        )
    )

    # --- every injection/task pair must be solvable after corruption ------- #
    proc = run([interpreter(), str(EXP2 / "discoverability.py")])
    n_ok = re.search(r"(\d+)/(\d+) pairs discoverable", proc.stdout)
    checks.append(
        Check(
            f"every task/injection pair is discoverable ({n_ok.group(0) if n_ok else '?'})",
            proc.returncode == 0,
            "an undiscoverable injection is an impossible task, and would read "
            "as a spectacular verifier gap that is entirely our artefact:\n"
            + (proc.stdout + proc.stderr)[-600:],
        )
    )

    # --- the substrate's own tests ----------------------------------------- #
    proc = run([interpreter(), "-m", "pytest", "-q",
                "tests/test_env.py", "tests/test_inject.py",
                "tests/test_discoverability.py"])
    checks.append(
        Check("substrate tests green", proc.returncode == 0,
              (proc.stdout + proc.stderr)[-600:])
    )

    # --- the design must still be pre-registered, not back-filled ---------- #
    research = EXP2 / "RESEARCH.md"
    if research.exists():
        md = research.read_text()
        hyps = {k for k in split_sections(section_body(md, "Hypotheses"), 3)
                if re.match(r"^H\d+\b", k)}
        checks.append(
            Check(f"experiment 2 hypotheses pre-registered: {len(hyps)}",
                  len(hyps) >= 5, "expected at least 5")
        )
        missing = [h for h in sorted(hyps)
                   if not re.search(r"\*\*Falsified if:\*\*",
                                    split_sections(section_body(md, "Hypotheses"), 3)[h])]
        checks.append(
            Check("every experiment 2 hypothesis can be falsified", not missing,
                  f"no falsification condition: {missing}")
        )
        # A pre-registration states predictions, never observations. Two
        # checkable consequences: it carries no Results section, and every
        # number attached to a hypothesis is labelled a prediction.
        checks.append(
            Check("pre-registration has no Results section",
                  not re.search(r"^## Results", md, re.MULTILINE),
                  "findings belong in RESULTS.md, generated after the run")
        )
        hyp_bodies = split_sections(section_body(md, "Hypotheses"), 3)
        unlabelled = [
            h for h in sorted(hyps)
            if not re.search(r"\*\*Prediction:\*\*", hyp_bodies[h])
        ]
        checks.append(
            Check("every hypothesis labels its numbers as predictions",
                  not unlabelled,
                  f"missing '- **Prediction:**': {unlabelled}")
        )
        # Once results exist the design-phase check is obsolete, but the
        # property it protected is not: the pre-registration must PREDATE the
        # data. Verified against git rather than asserted.
        results = sorted((EXP2 / "results").glob("*.jsonl"))
        if not results:
            checks.append(Check("pre-registration precedes any data (none yet)", True, ""))
        else:
            def first_commit(rel: str) -> str:
                proc = run(["git", "log", "--reverse", "--format=%ct", "--", rel])
                lines = proc.stdout.split()
                return lines[0] if lines else ""

            design_t = first_commit("experiments/agent-verifier-gap/RESEARCH.md")
            data_t = first_commit(
                str(results[-1].relative_to(ROOT))
            )
            if not design_t:
                checks.append(Check("pre-registration precedes the data", False,
                                    "RESEARCH.md has no commit history"))
            elif not data_t:
                checks.append(Check("pre-registration precedes the data", True,
                                    "results not yet committed"))
            else:
                checks.append(
                    Check(
                        "pre-registration was committed before the data",
                        int(design_t) < int(data_t),
                        "the design must predate the results it predicts, or it is "
                        "not a pre-registration",
                    )
                )
    return checks


# --------------------------------------------------------------------------- #
# G8 — experiment 2 stage 1: trajectories, honest denominators, report matches
# --------------------------------------------------------------------------- #


@gate("G8", "Trajectory run: records valid, denominators honest, report matches raw data",
      requires_live=True)
def gate_g8() -> list[Check]:
    checks: list[Check] = []
    files = sorted((EXP2 / "results").glob("traj-stage*.jsonl"))
    checks.append(
        Check(f"trajectory results present ({len(files)} file(s))", bool(files),
              "no traj-stage*.jsonl — stage 1 has not run")
    )
    if not files:
        return checks

    path = files[-1]
    records = read_records(path)
    checks.append(Check(f"{path.name}: 80 trajectories", len(records) == 80,
                        f"got {len(records)}"))
    providers = sorted({r.get("provider") for r in records})
    checks.append(Check("records come from the live provider", providers == ["deepseek"],
                        f"providers: {providers} (mock output is not a result)"))
    models = sorted({r.get("model_resolved") for r in records if r.get("model_resolved")})
    checks.append(Check(f"single resolved model ({models[0] if models else '?'})",
                        len(models) == 1, f"run spans: {models}"))

    missing = [r["trajectory_id"] for r in records
               if not (r.get("tokens", {}).get("output", 0) > 0)]
    checks.append(Check("every trajectory has token counts", not missing, f"{missing[:5]}"))

    # The ceiling: without it, failure under injection is indistinguishable from
    # ordinary agent failure.
    clean = [r for r in records if r["mode"] == "clean"]
    passed = sum(1 for r in clean if r["outcome_correct"])
    rate = passed / len(clean) if clean else 0.0
    checks.append(
        Check(f"clean ceiling {passed}/{len(clean)} >= 70%", rate >= 0.70,
              "tasks too hard — injected results would be confounded by ordinary failure")
    )

    # Truncation would look exactly like "the agent failed to notice".
    capped = [r["trajectory_id"] for r in records if r.get("hit_step_cap")]
    cap_rate = len(capped) / len(records)
    checks.append(Check(f"step-cap rate {cap_rate:.1%} <= 10%", cap_rate <= 0.10,
                        f"{len(capped)} hit the cap: {capped[:5]}"))

    # An injection that never fired must be visible, not silently folded in.
    attempted = [r for r in records if r["mode"] in ("inject", "inject_verify")]
    fired = [r for r in attempted if (r.get("injection") or {}).get("applicable")]
    checks.append(
        Check(
            f"injection applicability is recorded ({len(fired)}/{len(attempted)} fired)",
            all("applicable" in (r.get("injection") or {}) for r in attempted),
            "a trajectory whose injection never fired is not a clean run",
        )
    )
    checks.append(
        Check(
            f"enough injections fired to bound a rate ({len(fired)})",
            len(fired) >= 15,
            "too few fired to say anything; fix applicability before reporting",
        )
    )

    # Independent recomputation of the headline, without importing the metrics.
    wrong = [r for r in records if not r.get("outcome_correct")]
    claimed = [r for r in wrong if r.get("claims_success")]
    expected = 100 * len(claimed) / len(wrong) if wrong else None
    results_md = EXP2 / "RESULTS.md"
    checks.append(exists("experiments/agent-verifier-gap/RESULTS.md", "file"))
    if results_md.exists() and expected is not None:
        md = results_md.read_text()
        checks.append(Check("report was generated from this run", path.name in md,
                            f"RESULTS.md cites a different source than {path.name}"))
        published = re.search(r"\*\*trajectory false-green rate\*\*\s*\|\s*\*\*([\d.]+)%", md)
        if not published:
            checks.append(Check("false-green rate published", False, "not found in RESULTS.md"))
        else:
            delta = abs(float(published.group(1)) - expected)
            checks.append(
                Check(
                    f"gate recomputes trajectory false-green independently: "
                    f"{expected:.1f}% (report says {published.group(1)}%)",
                    delta < 0.05,
                    f"report disagrees with raw data by {delta:.2f}pp "
                    f"({len(claimed)}/{len(wrong)})",
                )
            )

    # The stopping rule must be applied, and its outcome stated.
    if results_md.exists():
        md = results_md.read_text()
        checks.append(Check("stopping rule level is stated",
                            "99%" in md and "stopping rule" in md,
                            "the interim look must say which level decided it"))
        checks.append(Check("undecided hypotheses are named",
                            "UNDETERMINED" in md or "Continues to stage 2" in md,
                            "a hypothesis that did not resolve must say so"))
    return checks


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def _color(s: str, c: str) -> str:
    return s if not sys.stdout.isatty() else f"{c}{s}{RESET}"


def select_gates(offline: bool = False) -> tuple[list[str], list[str]]:
    """(gates to run, gates skipped). Pure: runs nothing, so it is testable."""
    every = sorted(REGISTRY)
    if not offline:
        return every, []
    return (
        [g for g in every if g not in REQUIRES_LIVE],
        [g for g in every if g in REQUIRES_LIVE],
    )


def run_gate(gate_id: str) -> bool:
    if gate_id not in REGISTRY:
        print(f"unknown gate: {gate_id}. known: {', '.join(sorted(REGISTRY))}")
        return False
    if os.environ.get(GATE_ENV):
        # Gates shell out to pytest; a test that runs a gate would recurse until
        # the timeout. Fail loudly instead of hanging.
        print(
            f"refusing to run {gate_id}: already inside a gate "
            f"({GATE_ENV} is set). Tests must call select_gates(), not run_gate()."
        )
        return False
    title, fn = REGISTRY[gate_id]
    print(f"\n=== {gate_id}: {title} ===")
    os.environ[GATE_ENV] = gate_id
    try:
        checks = list(fn())
    finally:
        os.environ.pop(GATE_ENV, None)
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
    ap.add_argument(
        "--offline",
        action="store_true",
        help="run every gate that does not require a live API run (CI default)",
    )
    ap.add_argument("--list", action="store_true", help="list registered gates")
    args = ap.parse_args(argv)

    if args.list:
        for gid in sorted(REGISTRY):
            tag = " [requires live run]" if gid in REQUIRES_LIVE else ""
            print(f"{gid}\t{REGISTRY[gid][0]}{tag}")
        return 0

    if args.all or args.offline:
        selected, skipped = select_gates(offline=args.offline)
        results = {gid: run_gate(gid) for gid in selected}
        print("\n=== summary ===")
        for gid, ok in results.items():
            print(f"  {gid}: {'PASS' if ok else 'FAIL'}")
        for gid in skipped:
            # Named, not hidden: a skipped gate is an open phase, not a pass.
            print(f"  {gid}: SKIPPED (requires a live API run) — {REGISTRY[gid][0]}")
        return 0 if all(results.values()) else 1

    if args.gate:
        return 0 if run_gate(args.gate.upper()) else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
