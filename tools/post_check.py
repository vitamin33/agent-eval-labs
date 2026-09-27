"""Publication gate for a blog post written from this repository's experiments.

A post is publishable when every number in it exists in a published artifact
of this repo, its shape matches what the site renders and what mixed readers
understood in persona rounds, and the external checkers (voice, audience
clarity, anti-slop) pass. This script is the one command that runs all of it.

    python tools/post_check.py path/to/post.mdx [--extra other-posts-dir] [--json]
    python tools/post_check.py --source-pack            # print the allowed numbers

Number grounding, the rule that matters most: a unit-bearing number ($, %, x,
a decimal) that appears nowhere in README.md, the experiment documents or the
run summaries is a fabricated metric and FAILS. A bare integer that is not in
the sources WARNS (counts get reused from context legitimately). Years pass.

External checkers are looked up, never vendored: this repository is public
and the voice rules are not. Each one reports PASS, FAIL or SKIPPED with the
path it looked for, so a skipped check is visible, never a silent pass.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()

# Every number a post may cite must come from one of these.
SOURCE_GLOBS = (
    "README.md",
    "experiments/*/RESULTS.md",
    "experiments/*/CALIBRATION.md",
    "experiments/*/RESEARCH.md",
    "experiments/*/REVIEW.md",
    "experiments/*/PLAN.md",
    "experiments/*/results/README.md",
    "experiments/*/results/*.summary.json",
)
# What the serbyn.io publisher accepts (mirrors ascend/scripts/blog_publisher.py).
VALID_CATEGORIES = {"architecture", "engineering", "operations", "strategy"}
REQUIRED_FIELDS = ("title", "slug", "description", "date", "category", "keywords")
REPO_URL = "github.com/vitamin33/agent-eval-labs"

EXTERNAL = {
    "voice": (HOME / ".claude/skills/voice/checker.py", ["--destination", "blog"]),
    "audience-clarity": (HOME / ".claude/skills/audience-clarity/checker.py", []),
}
ASCEND = HOME / "ascend"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
_FENCE = re.compile(r"```.*?```", re.S)
# Link targets, bare URLs and domain paths are not numbers: a slug like
# /blog/self-verification-cost-1-64x or the vitamin33 in a repo path would
# otherwise read as "64x" and "33".
_URL = re.compile(r"\]\([^)]*\)|https?://\S+|\b[\w-]+\.(?:com|io|pro|org|net)/\S*")
_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:%|x\b)?")
_YEAR = re.compile(r"\A(?:19|20)\d{2}\Z")
_TABLE = re.compile(r"^\s*\|.*\|\s*$", re.M)
_H4 = re.compile(r"^####", re.M)
_FAQ = re.compile(r"(?:^|\n)##\s+FAQ\s*\n(.*?)(?:\n##\s|\Z)", re.S)
_FAQ_ITEM = re.compile(r"^\*\*(.+?\?)\*\*\s+\S", re.S)
_LIMITS = re.compile(r"^##\s+.*\b(?:not show|limitations|caveats|does not)\b", re.I | re.M)
_SUMMARY = re.compile(r"^##\s+.*\b(?:short version|summary|tl;dr|in short)\b", re.I | re.M)
_ABS_SELF_LINK = re.compile(r"\]\(https?://serbyn\.(?:io|pro)/")


@dataclass
class Finding:
    check: str
    status: str  # PASS | WARN | FAIL | SKIPPED
    detail: str = ""


@dataclass
class Report:
    passed: bool
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "findings": [asdict(f) for f in self.findings]}


def normalise(token: str) -> str:
    """'30,579' and '30579' are the same number; '$3.13' keeps its unit."""
    return token.replace(",", "")


def numbers_in(text: str) -> set[str]:
    return {normalise(m.group(0)) for m in _NUM.finditer(_URL.sub(" ", text))}


def unit_bearing(token: str) -> bool:
    return token.startswith("$") or token.endswith(("%", "x")) or "." in token


def _grounded_percent(token: str, pack: set[str]) -> bool:
    """'67.6%' is grounded by a published '67.6': interval bounds are printed as
    bare decimals in RESULTS.md. Integers get no such pass ('42' must not
    ground a made-up '42%'); a decimal is specific enough."""
    return token.endswith("%") and "." in token and token[:-1] in pack


def source_pack(root: Path = ROOT, extra: list[Path] | None = None) -> set[str]:
    """Every number that appears in a published artifact, plus optional extras
    (for example the titles of other posts a series list links to)."""
    text = ""
    for pattern in SOURCE_GLOBS:
        for p in sorted(root.glob(pattern)):
            text += p.read_text(encoding="utf-8", errors="replace") + "\n"
    for p in extra or []:
        if p.is_dir():
            for f in sorted(p.glob("*.mdx")):
                # only the title line: the rest of another post is not a source
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
                    if line.startswith("title:"):
                        text += line + "\n"
        elif p.exists():
            text += p.read_text(encoding="utf-8", errors="replace") + "\n"
    pack = numbers_in(text)
    # a grounded "$0.2004" also grounds the bare "0.2004"; a grounded "7.1%" the bare "7.1"
    pack |= {t.lstrip("$").rstrip("%x") for t in pack}
    # ascend's slop gate splits "30,579" on the comma; keep the raw form and its pieces too
    raw = {m.group(0) for m in _NUM.finditer(_URL.sub(" ", text)) if "," in m.group(0)}
    pack |= raw | {piece for t in raw for piece in t.lstrip("$").rstrip("%x").split(",")}
    return pack


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    m = _FRONTMATTER.match(text)
    if not m:
        raise ValueError("missing leading '---' frontmatter fence")
    meta: dict[str, object] = {}
    key = None
    for line in m.group(1).splitlines():
        if line.startswith("- ") and key:
            meta.setdefault(key, [])
            v = meta[key]
            if isinstance(v, list):
                v.append(line[2:].strip())
        elif ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip("'\"")
            meta[key] = val if val else []
    return meta, m.group(2)


def check_frontmatter(meta: dict[str, object]) -> list[Finding]:
    out: list[Finding] = []
    missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
    if missing:
        out.append(Finding("frontmatter", "FAIL", f"missing: {', '.join(missing)}"))
    cat = meta.get("category")
    if cat and cat not in VALID_CATEGORIES:
        out.append(Finding("frontmatter", "FAIL", f"category {cat!r} not in {sorted(VALID_CATEGORIES)}"))
    date = str(meta.get("date", ""))
    if date and not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        out.append(Finding("frontmatter", "FAIL", f"date {date!r} is not YYYY-MM-DD"))
    desc = str(meta.get("description", ""))
    if desc and not 120 <= len(desc) <= 170:
        out.append(Finding("frontmatter", "WARN", f"description is {len(desc)} chars; 150-160 is the target"))
    if not out:
        out.append(Finding("frontmatter", "PASS"))
    return out


def check_shape(body: str) -> list[Finding]:
    out: list[Finding] = []
    prose = _FENCE.sub("", body)
    if _TABLE.search(prose):
        out.append(Finding("no_tables", "FAIL", "markdown table found; the site renderer prints raw pipes"))
    if _H4.search(prose):
        out.append(Finding("heading_depth", "FAIL", "'####' found; the site uses ## and ### only"))
    faq = _FAQ.search(body)
    items = [p for p in re.split(r"\n\s*\n", faq.group(1)) if _FAQ_ITEM.match(p.strip())] if faq else []
    if not faq:
        out.append(Finding("faq", "FAIL", "no '## FAQ' section"))
    elif not 3 <= len(items) <= 5:
        out.append(Finding("faq", "WARN", f"{len(items)} FAQ items in the '**Question?** Answer' shape; 3-5 expected"))
    if not _LIMITS.search(prose):
        out.append(Finding("limits_section", "FAIL", "no 'What this does not show' style heading"))
    if not _SUMMARY.search(prose):
        out.append(Finding("summary_section", "FAIL", "no short-version / summary heading"))
    if REPO_URL not in body:
        out.append(Finding("repo_link", "FAIL", f"no link to {REPO_URL}; readers must be able to check the numbers"))
    if _ABS_SELF_LINK.search(body):
        out.append(Finding("relative_links", "WARN", "absolute serbyn.io link; the site expects /blog/<slug>"))
    if not out:
        out.append(Finding("shape", "PASS"))
    return out


def check_numbers(body: str, pack: set[str]) -> list[Finding]:
    out: list[Finding] = []
    prose = _FENCE.sub("", body)
    hard, soft = [], []
    for tok in sorted(numbers_in(prose)):
        if tok in pack or _YEAR.match(tok) or _grounded_percent(tok, pack):
            continue
        (hard if unit_bearing(tok) else soft).append(tok)
    if hard:
        out.append(Finding("numbers_grounded", "FAIL", f"unit-bearing numbers not in any published artifact: {', '.join(hard)}"))
    if soft:
        out.append(Finding("numbers_grounded", "WARN", f"bare numbers not in the sources: {', '.join(soft[:12])}"))
    if not out:
        out.append(Finding("numbers_grounded", "PASS", f"{len(numbers_in(prose))} numbers, all in the sources"))
    return out


def run_external(post: Path, pack: set[str]) -> list[Finding]:
    """Voice, audience-clarity and the ascend slop gate, when installed."""
    out: list[Finding] = []
    for name, (script, args) in EXTERNAL.items():
        if not script.exists():
            out.append(Finding(name, "SKIPPED", f"{script} not found; install with `make skill-sync` in ascend"))
            continue
        proc = subprocess.run([sys.executable, str(script), str(post), *args], capture_output=True, text=True)
        first = (proc.stdout.strip().splitlines() or [""])[0]
        out.append(Finding(name, "PASS" if proc.returncode == 0 else "FAIL", first))
    gate = ASCEND / "scripts" / "blog_slop_gate.py"
    py = ASCEND / ".venv" / "bin" / "python"
    if not (gate.exists() and py.exists()):
        out.append(Finding("slop_gate", "SKIPPED", f"{gate} or its venv not found"))
        return out
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        "from pathlib import Path\n"
        "from scripts.blog_slop_gate import evaluate_slop\n"
        "mdx = Path(sys.argv[1]).read_text(); allowed = set(sys.argv[2].split(','))\n"
        "r = evaluate_slop(mdx, allowed_numbers=allowed)\n"
        "print('ok' if r.ok else 'REJECT ' + '; '.join(r.rejects)); print('; '.join(r.warnings))\n"
        "sys.exit(0 if r.ok else 1)\n"
    )
    proc = subprocess.run([str(py), "-c", code, str(post.resolve()), ",".join(sorted(pack))],
                          capture_output=True, text=True, cwd=ASCEND)
    lines = proc.stdout.strip().splitlines() or [proc.stderr.strip()[-200:]]
    out.append(Finding("slop_gate", "PASS" if proc.returncode == 0 else "FAIL", " | ".join(lines)[:300]))
    return out


def check_post(post: Path, *, extra: list[Path] | None = None, external: bool = True, root: Path = ROOT) -> Report:
    text = post.read_text(encoding="utf-8")
    try:
        meta, body = split_frontmatter(text)
    except ValueError as exc:
        return Report(False, [Finding("frontmatter", "FAIL", str(exc))])
    pack = source_pack(root, extra)
    findings = check_frontmatter(meta) + check_shape(body) + check_numbers(body, pack)
    if external:
        findings += run_external(post, pack)
    return Report(passed=not any(f.status == "FAIL" for f in findings), findings=findings)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="publication gate for a post written from this repo's experiments")
    ap.add_argument("post", nargs="?", type=Path)
    ap.add_argument("--extra", action="append", type=Path, default=[], help="extra source: a file, or a directory of other posts (titles only)")
    ap.add_argument("--no-external", action="store_true", help="skip voice / clarity / slop (CI, tests)")
    ap.add_argument("--source-pack", action="store_true", help="print the allowed numbers and exit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.source_pack:
        print("\n".join(sorted(source_pack(ROOT, args.extra))))
        return 0
    if not args.post:
        ap.error("post path required")
    rep = check_post(args.post.resolve(), extra=args.extra, external=not args.no_external)
    if args.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(f"post-check {'PASS' if rep.passed else 'FAIL'}: {args.post}")
        for f in rep.findings:
            print(f"  [{f.status:7}] {f.check}: {f.detail}")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
