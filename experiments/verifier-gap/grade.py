"""Deterministic grading.

Ground truth is the task's ASSERTS list and nothing else. No model is consulted.

The candidate artifact is executed in a subprocess with a wall-clock timeout so
that a hang, a crash, or a `sys.exit` cannot take the harness with it.

The child's verdict is authenticated with a per-call nonce and delivered via a
file rather than stdout, so a candidate cannot forge a passing grade by printing
one and exiting early. See REVIEW.md R1.1.

SECURITY: this executes model-generated code. The subprocess is isolated
(`-I`) and time-bounded, but it is NOT a security sandbox — it has the same
filesystem and network access as the parent. Run the live matrix only against
tasks you wrote, on a machine you are willing to run arbitrary Python on.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from extract import Extraction, extract

HERE = Path(__file__).resolve().parent
CHILD = HERE / "_grade_child.py"

# The four possible outcomes. Only CORRECT counts as a solved task; everything
# else is ground-truth wrong for false-green purposes.
CORRECT = "correct"
WRONG = "wrong"
ERROR = "error"
NO_ANSWER = "no_answer"


@dataclass
class Grade:
    outcome: str
    detail: str = ""
    first_failure: str | None = None
    n_asserts: int = 0
    n_passed: int = 0
    extraction_reason: str = ""
    # True when the artifact satisfied every visible case and then failed a
    # held-out one — a solution written against the examples, not the spec.
    hardcoded: bool = False

    @property
    def is_correct(self) -> bool:
        return self.outcome == CORRECT

    def to_dict(self) -> dict:
        return asdict(self)


def grade_completion(completion: str, task: dict, timeout_s: int = 10) -> Grade:
    """Extract an artifact from `completion` and grade it against the task."""
    ext: Extraction = extract(completion or "", task)
    if not ext.found:
        return Grade(
            outcome=NO_ANSWER,
            detail=ext.reason,
            n_asserts=len(task["asserts"]),
            extraction_reason=ext.reason,
        )
    grade = grade_artifact(ext.code, task, timeout_s=timeout_s)
    grade.extraction_reason = ext.reason
    return grade


def grade_artifact(code: str, task: dict, timeout_s: int = 10) -> Grade:
    """Grade an already-extracted artifact."""
    nonce = secrets.token_hex(16)
    payload = {
        "kind": task["kind"],
        "code": code,
        "entrypoint": task.get("entrypoint"),
        "asserts": task["asserts"],
        "hidden_asserts": task.get("hidden_asserts", []),
        "fixture": task.get("fixture", ""),
        "hidden_fixture": task.get("hidden_fixture", ""),
        "nonce": nonce,
    }
    n_asserts = len(task["asserts"]) + len(task.get("hidden_asserts", []))

    with tempfile.TemporaryDirectory(prefix="aelabs-grade-") as tmpdir:
        verdict_path = Path(tmpdir) / "verdict.json"
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(CHILD), str(verdict_path)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return Grade(ERROR, f"timeout after {timeout_s}s", n_asserts=n_asserts)

        # The verdict is read from the file, never from stdout: a candidate that
        # prints a plausible verdict and exits produces no file at all.
        try:
            result = json.loads(verdict_path.read_text())
        except (OSError, ValueError):
            return Grade(
                ERROR,
                "grader child produced no verdict "
                f"(rc={proc.returncode}): {(proc.stderr or proc.stdout)[-300:]}",
                n_asserts=n_asserts,
            )

    # The nonce authenticates the verdict as the grader's, not the candidate's.
    if result.get("nonce") != nonce:
        return Grade(
            ERROR,
            "verdict failed nonce authentication — the candidate artifact may have "
            "written it",
            n_asserts=n_asserts,
        )
    return Grade(
        outcome=result["outcome"],
        detail=result.get("detail", ""),
        first_failure=result.get("first_failure"),
        n_asserts=result.get("n_asserts", 0),
        n_passed=result.get("n_passed", 0),
        hardcoded=bool(result.get("hardcoded", False)),
    )
