"""Pull the code artifact out of a model completion.

This module is a false-green surface in its own right. If extraction silently
returns something plausible for a response that contained no real answer, the
grader may execute a leftover, a truncated fragment, or an empty string, and the
experiment would report a harness bug as a model result. So every path returns
an explicit reason, and "found nothing" is `None` — never `""`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)(?:```|\Z)", re.DOTALL)

SQL_START_RE = re.compile(r"^\s*(?:WITH|SELECT)\b", re.IGNORECASE | re.MULTILINE)

REFUSAL_MARKERS = (
    "i can't", "i cannot", "i won't", "i'm unable", "i am unable",
    "i'm not able", "i am not able", "as an ai",
)


@dataclass(frozen=True)
class Extraction:
    code: str | None
    reason: str

    @property
    def found(self) -> bool:
        return self.code is not None


def _fenced_blocks(text: str) -> list[tuple[str, str]]:
    """[(language, body)] for every fenced block, including unterminated ones."""
    return [(m.group(1).lower(), m.group(2)) for m in FENCE_RE.finditer(text)]


def _looks_like_refusal(text: str) -> bool:
    head = text.strip().lower()[:400]
    return any(marker in head for marker in REFUSAL_MARKERS)


def extract_python(text: str, entrypoint: str) -> Extraction:
    """Extract a Python artifact defining `entrypoint`."""
    if not text or not text.strip():
        return Extraction(None, "empty completion")

    blocks = _fenced_blocks(text)
    defining = [b for _, b in blocks if re.search(rf"\bdef\s+{re.escape(entrypoint)}\b", b)]
    if defining:
        # Several fences may each define it (e.g. "before" and "after" snippets);
        # the last one is the model's final word.
        return Extraction(defining[-1], f"fenced block defining {entrypoint}")

    if blocks:
        code_ish = [b for lang, b in blocks if lang in ("", "python", "py")]
        if code_ish:
            return Extraction(
                code_ish[-1], f"fenced block, but no `def {entrypoint}` in it"
            )

    if re.search(rf"\bdef\s+{re.escape(entrypoint)}\b", text):
        return Extraction(text, f"unfenced text defining {entrypoint}")

    if _looks_like_refusal(text):
        return Extraction(None, "refusal")
    return Extraction(None, "no code found")


def extract_sql(text: str) -> Extraction:
    """Extract a single SQL query."""
    if not text or not text.strip():
        return Extraction(None, "empty completion")

    blocks = _fenced_blocks(text)
    sql_blocks = [b for lang, b in blocks if lang in ("", "sql") and SQL_START_RE.search(b)]
    if sql_blocks:
        return Extraction(sql_blocks[-1].strip(), "fenced SQL block")

    if SQL_START_RE.search(text):
        # Strip prose before the first SELECT/WITH and after the terminating ';'.
        start = SQL_START_RE.search(text).start()
        body = text[start:]
        semi = body.find(";")
        if semi != -1:
            body = body[: semi + 1]
        return Extraction(body.strip(), "unfenced SQL")

    if _looks_like_refusal(text):
        return Extraction(None, "refusal")
    return Extraction(None, "no SQL found")


def extract(text: str, task: dict) -> Extraction:
    """Dispatch on task kind."""
    if task["kind"] == "sql":
        return extract_sql(text)
    return extract_python(text, task["entrypoint"])
