#!/usr/bin/env python3
"""Print the report.py arguments for the runs currently on disk.

Two rules, and they are the whole point:

1. The **published** run of each arm is the newest one the API served under the
   model id the config pins. A run served a different id is raw data, not a
   result, and cannot become the headline by being newest.
2. **Every other run of that arm is passed as a replication comparison.** A run
   that exists on disk is therefore always named in the report — it can be
   contradicted, but it cannot be omitted.

    python experiments/verifier-gap/report.py $(python experiments/verifier-gap/pick.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _off_pin(path: Path) -> bool:
    try:
        records = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return True
    real = [r for r in records if r.get("provider") != "mock"]
    requested = {r.get("model_requested") for r in real if r.get("model_requested")}
    served = {r.get("model_resolved") for r in real if r.get("model_resolved")}
    return bool(served) and bool(requested) and bool(served - requested)


def arm_files(inject: bool) -> list[Path]:
    files = sorted(RESULTS.glob("run-live-inject-*.jsonl")) if inject else sorted(
        f for f in RESULTS.glob("run-live-*.jsonl") if "-inject-" not in f.name
    )
    return files


def split(files: list[Path]) -> tuple[Path | None, list[Path]]:
    on = [f for f in files if not _off_pin(f)]
    published = on[-1] if on else None
    others = [f for f in files if f != published]
    return published, others


def main() -> int:
    gen_pub, gen_others = split(arm_files(inject=False))
    inj_pub, inj_others = split(arm_files(inject=True))
    if gen_pub is None:
        print(
            "no generation run is on the pinned model; nothing is publishable. "
            "Re-run against the pinned id or pin the id actually served.",
            file=sys.stderr,
        )
        return 2

    args = ["--results", str(gen_pub)]
    if inj_pub is not None:
        args += ["--inject-results", str(inj_pub)]
    if gen_others:
        args += ["--replicate-gen"] + [str(f) for f in gen_others]
    if inj_others:
        args += ["--replicate-inject"] + [str(f) for f in inj_others]
    print(" ".join(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
