"""tools/post_check.py — a post is publishable only when its numbers are in the artifacts."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import post_check as pc  # noqa: E402

POST = """---
title: "Agents Say Done Wrongly 45 Times Out of 45"
slug: agents-say-done
description: "{desc}"
date: '2026-09-22'
keywords:
- false green
- agent evals
category: engineering
author: Vitalii Serbyn
featured: false
---

# Agents Say Done Wrongly 45 Times Out of 45

I measured it: 45 of 45 wrong runs claimed success, against 0 of 50 on single answers, for $3.13.

## The Short Version

- What I tested. Whether an agent's own "done" can be trusted.

## What This Does Not Show

One model only.

## FAQ

**What is a false green?** A wrong answer marked correct.

**How much did it cost?** $3.13 for 680 runs.

**Where is the code?** In the [repository](https://github.com/vitamin33/agent-eval-labs).
"""


def _source_root(tmp_path: Path) -> Path:
    (tmp_path / "experiments" / "x" / "results").mkdir(parents=True)
    (tmp_path / "README.md").write_text("False greens: 45/45. Single answers 0/50. Total $3.13 for 680 records, 30,579 tokens.\n")
    (tmp_path / "experiments" / "x" / "RESULTS.md").write_text("| H1 | 7.1% | 1.64x |\n")
    return tmp_path


def _post(tmp_path: Path, body_extra: str = "", desc: str = "x" * 155) -> Path:
    p = tmp_path / "post.mdx"
    p.write_text(POST.format(desc=desc) + body_extra)
    return p


def test_grounded_post_passes(tmp_path):
    rep = pc.check_post(_post(tmp_path), external=False, root=_source_root(tmp_path))
    assert rep.passed, rep.findings
    assert any(f.check == "numbers_grounded" and f.status == "PASS" for f in rep.findings)


def test_unit_bearing_number_outside_the_sources_fails(tmp_path):
    rep = pc.check_post(_post(tmp_path, "\nIt improved 42% and cost 2.5x.\n"), external=False, root=_source_root(tmp_path))
    assert not rep.passed
    f = next(f for f in rep.findings if f.check == "numbers_grounded" and f.status == "FAIL")
    assert "42%" in f.detail and "2.5x" in f.detail


def test_bare_integer_outside_the_sources_only_warns(tmp_path):
    rep = pc.check_post(_post(tmp_path, "\nThree of the 12 tasks were easy in 2026.\n"), external=False, root=_source_root(tmp_path))
    assert rep.passed
    f = next(f for f in rep.findings if f.check == "numbers_grounded")
    assert f.status == "WARN" and "12" in f.detail and "2026" not in f.detail


def test_comma_and_unit_variants_ground_each_other(tmp_path):
    pack = pc.source_pack(_source_root(tmp_path))
    assert {"30579", "$3.13", "3.13", "7.1%", "7.1", "1.64x", "1.64"} <= pack


def test_urls_are_not_numbers(tmp_path):
    rep = pc.check_post(_post(tmp_path, "\nSee [the run](https://example.com/run/4711) and https://x.y/99z.\n"), external=False, root=_source_root(tmp_path))
    assert any(f.check == "numbers_grounded" and f.status == "PASS" for f in rep.findings), rep.findings


def test_relative_link_targets_and_domain_paths_are_not_numbers(tmp_path):
    body = "\n- [Cost 1.64x](/blog/self-verification-cost-1-64x-and-caught-nothing)\n[github.com/vitamin33/agent-eval-labs](https://github.com/vitamin33/agent-eval-labs)\n"
    rep = pc.check_post(_post(tmp_path, body), external=False, root=_source_root(tmp_path))
    assert any(f.check == "numbers_grounded" and f.status == "PASS" for f in rep.findings), rep.findings


def test_a_decimal_percent_is_grounded_by_its_bare_decimal_but_an_integer_is_not(tmp_path):
    root = _source_root(tmp_path)
    (root / "experiments" / "x" / "RESULTS.md").write_text("recovery 100.0% [67.6, 100.0]; n=42\n")
    ok = pc.check_post(_post(tmp_path, "\nThe lower bound is 67.6%.\n"), external=False, root=root)
    assert any(f.check == "numbers_grounded" and f.status == "PASS" for f in ok.findings), ok.findings
    bad = pc.check_post(_post(tmp_path, "\nIt improved 42%.\n"), external=False, root=root)
    assert any(f.check == "numbers_grounded" and f.status == "FAIL" for f in bad.findings)


def test_code_fences_are_not_prose(tmp_path):
    rep = pc.check_post(_post(tmp_path, "\n```python\nrate = 99.9%\n```\n"), external=False, root=_source_root(tmp_path))
    assert rep.passed


def test_shape_rules(tmp_path):
    root = _source_root(tmp_path)
    table = pc.check_post(_post(tmp_path, "\n| a | b |\n|---|---|\n| 1 | 2 |\n"), external=False, root=root)
    assert any(f.check == "no_tables" and f.status == "FAIL" for f in table.findings)
    no_faq = _post(tmp_path)
    no_faq.write_text(no_faq.read_text().replace("## FAQ", "## Questions"))
    rep = pc.check_post(no_faq, external=False, root=root)
    assert any(f.check == "faq" and f.status == "FAIL" for f in rep.findings)
    no_repo = _post(tmp_path)
    no_repo.write_text(no_repo.read_text().replace("github.com/vitamin33/agent-eval-labs", "example.com"))
    assert any(f.check == "repo_link" for f in pc.check_post(no_repo, external=False, root=root).findings)


def test_frontmatter_rules(tmp_path):
    root = _source_root(tmp_path)
    p = _post(tmp_path, desc="too short")
    rep = pc.check_post(p, external=False, root=root)
    assert any(f.check == "frontmatter" and f.status == "WARN" for f in rep.findings)
    p.write_text(p.read_text().replace("category: engineering", "category: evals"))
    rep = pc.check_post(p, external=False, root=root)
    assert any(f.check == "frontmatter" and f.status == "FAIL" and "evals" in f.detail for f in rep.findings)


def test_external_checkers_report_skipped_not_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "EXTERNAL", {"voice": (tmp_path / "nope.py", [])})
    monkeypatch.setattr(pc, "ASCEND", tmp_path / "no-ascend")
    rep = pc.check_post(_post(tmp_path), external=True, root=_source_root(tmp_path))
    statuses = {f.check: f.status for f in rep.findings if f.check in ("voice", "slop_gate")}
    assert statuses == {"voice": "SKIPPED", "slop_gate": "SKIPPED"}


def test_cli_exit_code(tmp_path):
    root = _source_root(tmp_path)
    p = _post(tmp_path, "\nA made-up 99.9% here.\n")
    import post_check
    post_check.ROOT = root
    try:
        assert post_check.main([str(p), "--no-external"]) == 1
        assert post_check.main([str(_post(tmp_path)), "--no-external"]) == 0
    finally:
        post_check.ROOT = ROOT


def test_the_published_posts_ground_against_the_real_repo():
    """The three live posts must keep passing the number gate against the real artifacts."""
    candidates = (ROOT / "drafts" / "live", Path.home() / "development" / "serbyn-pro" / "content" / "blog")
    site = next((c for c in candidates if c.exists()), None)
    if site is None:
        import pytest
        pytest.skip("no copy of the live posts present (drafts/live or the serbyn-pro checkout)")
    for slug in ("same-model-0-and-100-where-the-verifier-gap-actually-lives",
                 "the-api-served-a-different-model-and-my-check-passed",
                 "self-verification-cost-1-64x-and-caught-nothing"):
        p = site / f"{slug}.mdx"
        if not p.exists():
            continue
        rep = pc.check_post(p, extra=[site], external=False)
        assert not any(f.status == "FAIL" for f in rep.findings), (slug, rep.findings)
