# Raw results

Append-only JSON Lines, one record per line, one file per run:

- `run-live-<stamp>.jsonl` — a real API run. This is the experimental data.
- `run-dry-<stamp>.jsonl` — a mocked offline run. Synthetic; never a result.

Records are never edited. A correction is a new run with a new file, and
`runner.py` refuses to append to a results file that already has content.

Each record carries the resolved model string, both prompts, the raw
completions, the deterministic grade, the verifier's verdict and confidence,
per-call input/output tokens and wall-clock, and the computed cost.

`report.py` and `metrics.py` read these files; nothing writes back to them.
