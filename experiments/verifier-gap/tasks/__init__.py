"""Task registry.

Each task module exports TASK. Ground truth is the ASSERTS list — executable
expressions, evaluated against the candidate's own namespace. No model is
consulted at any point in grading.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent


def load_tasks() -> list[dict]:
    """Every task, ordered by id."""
    tasks = []
    for mod in pkgutil.iter_modules([str(TASK_DIR)]):
        if not mod.name.startswith("t"):
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        tasks.append(module.TASK)
    return sorted(tasks, key=lambda t: t["id"])


def by_id(task_id: str) -> dict:
    for t in load_tasks():
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)
