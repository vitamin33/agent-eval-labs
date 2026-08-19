"""Shared test configuration.

`experiments/verifier-gap/` contains a hyphen, so it is not importable as a
package. Put it on sys.path so tests can `import runner`, `import metrics`, etc.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "verifier-gap"

for p in (ROOT, EXP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


import pytest  # noqa: E402


def make_record(**overrides) -> dict:
    """A schema-valid record, for tests that need to inject specific states."""
    rec = {
        "schema_version": 1,
        "record_id": "T01|self_verify|0",
        "task_id": "T01",
        "task_name": "csv_quoted",
        "task_type": "data parsing with edge cases",
        "task_kind": "python",
        "mode": "self_verify",
        "run_index": 0,
        "provider": "mock",
        "model_requested": "claude-haiku-4-5",
        "model_resolved": "claude-haiku-4-5",
        "temperature": 0.0,
        "seed": 1,
        "prompts": {"system": "s", "generation": "g", "verification": "v"},
        "completion_generation": "",
        "completion_verification": "",
        "grade_initial": {"outcome": "wrong"},
        "grade_final": {"outcome": "wrong"},
        "truth_initial": "wrong",
        "truth_final": "wrong",
        "verdict": None,
        "confidence": None,
        "verdict_source": None,
        "revised_applied": False,
        "calls": [],
        "tokens": {"input": 100, "output": 50},
        "cost_usd": 0.001,
        "wall_clock_s": 0.1,
        "timestamp": "2026-08-19T00:00:00+00:00",
    }
    rec.update(overrides)
    return rec


@pytest.fixture
def record_factory():
    return make_record


@pytest.fixture(scope="session")
def dry_run_records(tmp_path_factory):
    """One shared dry-run matrix, reused by tests that need real records."""
    import runner
    import config as config_mod

    out = tmp_path_factory.mktemp("dry") / "run.jsonl"
    cfg = config_mod.load()
    return runner.run_matrix(cfg, dry_run=True, out_path=out, progress=False)
