"""R3 — what the seed does and does not reproduce.

Claiming seeded reproducibility over live sampling would be false: the Messages
API has no seed parameter. These tests pin the true scope of the claim.
"""

import inspect

import config as config_mod
import metrics
import provider
import runner


def test_config_carries_a_seed():
    assert isinstance(config_mod.load().seed, int)


def test_dry_run_is_byte_reproducible_under_one_seed(tmp_path):
    cfg = config_mod.load()

    def norm(records):
        return [
            (r["record_id"], r["completion_generation"], r["completion_verification"],
             r["truth_final"], r["verdict"], r["confidence"], r["tokens"])
            for r in records
        ]

    a = runner.run_matrix(cfg, dry_run=True, out_path=tmp_path / "a.jsonl", progress=False)
    b = runner.run_matrix(cfg, dry_run=True, out_path=tmp_path / "b.jsonl", progress=False)
    assert norm(a) == norm(b)


def test_a_different_seed_changes_the_dry_run(tmp_path):
    """If the seed did nothing, reproducibility would be vacuous."""
    import dataclasses

    cfg = config_mod.load()
    other = dataclasses.replace(cfg, seed=cfg.seed + 1)
    a = runner.run_matrix(cfg, dry_run=True, out_path=tmp_path / "a.jsonl", progress=False)
    b = runner.run_matrix(other, dry_run=True, out_path=tmp_path / "b.jsonl", progress=False)
    assert [r["completion_generation"] for r in a] != [r["completion_generation"] for r in b]


def test_the_api_is_never_sent_a_seed_parameter():
    """Evidence for the limitation: there is no seed to send."""
    source = inspect.getsource(provider.AnthropicProvider.complete)
    assert "seed" not in source
    cfg = config_mod.load()
    assert "seed" not in cfg.sampling_params()


def test_metrics_are_fully_reproducible_from_a_fixed_results_file(tmp_path, dry_run_records):
    """Whatever the sampling did, the analysis of a saved run is deterministic."""
    import json

    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in dry_run_records) + "\n")
    a = metrics.summarize(metrics.load_records(path), k=5)
    b = metrics.summarize(metrics.load_records(path), k=5)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
