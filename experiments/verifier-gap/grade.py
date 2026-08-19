"""Deterministic grading.

Ground truth is the task's ASSERTS list and nothing else. No model is consulted.

The candidate artifact is executed in a subprocess with a wall-clock timeout so
that a hang, a crash, or a `sys.exit` cannot take the harness with it.

SECURITY: this executes model-generated code. The subprocess is isolated
(`-I`) and time-bounded, but it is NOT a security sandbox — it has the same
filesystem and network access as the parent. Run the live matrix only against
tasks you wrote, on a machine you are willing to run arbitrary Python on.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
    payload = {
        "kind": task["kind"],
        "code": code,
        "entrypoint": task.get("entrypoint"),
        "asserts": task["asserts"],
        "fixture": task.get("fixture", ""),
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(CHILD)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return Grade(ERROR, f"timeout after {timeout_s}s", n_asserts=len(task["asserts"]))

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return Grade(
            ERROR,
            f"grader child produced no verdict: {(proc.stderr or proc.stdout)[-300:]}",
            n_asserts=len(task["asserts"]),
        )
    return Grade(
        outcome=result["outcome"],
        detail=result.get("detail", ""),
        first_failure=result.get("first_failure"),
        n_asserts=result.get("n_asserts", 0),
        n_passed=result.get("n_passed", 0),
    )
