"""Parse the verifier's structured verdict.

A verdict the harness cannot parse is a potential harness-manufactured result,
so parsing never guesses: it returns None and the run is counted in
`verdict_parse_failure_rate`. In particular an unparseable response is NOT
treated as "wrong" (which would flatter the false-green rate) and NOT treated
as "correct" (which would inflate it).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE = re.compile(r"```(?:json)?\s*\r?\n(.*?)```", re.DOTALL)
_DECODER = json.JSONDecoder()


@dataclass(frozen=True)
class Verdict:
    verdict: str | None
    confidence: int | None
    revised: str | None
    source: str

    @property
    def parsed(self) -> bool:
        return self.verdict is not None


UNPARSED = Verdict(None, None, None, "unparsed")


def _coerce(obj: object, source: str) -> Verdict:
    if not isinstance(obj, dict):
        return UNPARSED
    raw_verdict = obj.get("verdict")
    if not isinstance(raw_verdict, str):
        return UNPARSED
    v = raw_verdict.strip().lower()
    if v not in ("correct", "wrong"):
        return UNPARSED

    conf = obj.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        conf = None
    else:
        conf = int(round(conf))
        if not 0 <= conf <= 100:
            conf = None

    revised = obj.get("revised")
    if not isinstance(revised, str) or not revised.strip():
        revised = None

    return Verdict(v, conf, revised, source)


def _scan_objects(text: str) -> list[dict]:
    """Every complete JSON object in `text`, in order.

    A reasoning model sometimes emits the required object, then second-guesses
    itself in prose and emits it again ("Wait - the schema says JSON object
    only"). The whole body is then not valid JSON, and a greedy `{.*}` match
    spans from the first brace to the last and is not valid either, so a
    perfectly clear verdict was being recorded as a parse failure. Scanning for
    complete objects reads what the model actually emitted without guessing at
    what it meant.
    """
    objects: list[dict] = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            obj, end = _DECODER.raw_decode(text[start:])
        except ValueError:
            i = start + 1
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        i = start + end
    return objects


def parse_verdict(text: str, *, structured: bool) -> Verdict:
    """Parse a verification response into a verdict."""
    if not text or not text.strip():
        return UNPARSED

    # Structured output guarantees the whole body is the JSON object.
    try:
        return _coerce(json.loads(text), "structured" if structured else "direct_json")
    except ValueError:
        pass

    fence = _FENCE.search(text)
    if fence:
        try:
            return _coerce(json.loads(fence.group(1)), "fenced_json")
        except ValueError:
            pass

    # Complete objects embedded in prose. Several may be present; they must
    # agree on the verdict, or this stays a parse failure rather than a guess.
    candidates = [v for v in (_coerce(o, "embedded_json") for o in _scan_objects(text)) if v.parsed]
    if candidates:
        if len({v.verdict for v in candidates}) > 1:
            return UNPARSED
        # The last one is the model's final word, matching how `extract.py`
        # chooses between several code fences.
        return candidates[-1]

    return UNPARSED
