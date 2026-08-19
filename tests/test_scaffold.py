"""Phase 0 tests: the scaffold itself is well-formed."""

from pathlib import Path

import gates

ROOT = Path(__file__).resolve().parents[1]


def test_repo_structure_present():
    for rel in [
        "pyproject.toml",
        ".gitignore",
        "gates.py",
        "Makefile",
        "experiments/verifier-gap",
        "experiments/verifier-gap/tasks",
        "experiments/verifier-gap/results",
        "tests",
    ]:
        assert (ROOT / rel).exists(), f"missing {rel}"


def test_gate_registry_is_populated():
    assert "G0" in gates.REGISTRY
    for gid, (title, fn) in gates.REGISTRY.items():
        assert gid.startswith("G") and gid[1:].isdigit(), gid
        assert title, f"{gid} has no title"
        assert callable(fn)


def test_gate_ids_are_contiguous_from_zero():
    ids = sorted(int(g[1:]) for g in gates.REGISTRY)
    assert ids == list(range(len(ids))), f"gate ids not contiguous: {ids}"


def test_unknown_gate_fails_closed():
    assert gates.run_gate("G99") is False
    assert gates.main(["--gate", "G99"]) == 1


def test_list_gates_exits_zero():
    assert gates.main(["--list"]) == 0


def test_research_md_parses_into_expected_shape():
    """G1's parser must find the design's three machine-checked structures."""
    md = (ROOT / "experiments/verifier-gap/RESEARCH.md").read_text()
    hyps = gates.split_sections(gates.section_body(md, "Hypotheses"), 3)
    metrics = gates.split_sections(gates.section_body(md, "Metric definitions"), 3)
    tasks = gates.split_sections(gates.section_body(md, "Task design"), 3)
    assert len(hyps) >= 3
    assert len(metrics) >= 5
    assert len([t for t in tasks if t.startswith("T")]) == gates.N_TASKS
