"""Grader child process.

Reads a JSON payload on stdin and writes an AUTHENTICATED verdict to the path
given in argv[1]. Kept small and dependency-free; runs under `python -I`.

Two defences against a candidate artifact manufacturing its own pass, both
added after the Phase 5 adversarial review found them exploitable (REVIEW.md
R1.1 and R1.2):

1. The verdict goes to a file and carries a nonce the parent generated. A
   candidate that prints a fake verdict, or calls `sys.exit` / `os._exit`
   before grading completes, produces no authenticated verdict at all, and the
   parent grades it an error rather than reading the forgery.
2. After every assert passes, one canary comparison is evaluated that MUST be
   false. An artifact whose `__eq__` returns True unconditionally satisfies
   every `==` assert; the canary catches exactly that.
"""

import json
import re
import sys
import traceback

CORRECT, WRONG, ERROR = "correct", "wrong", "error"
CANARY = "__aelabs_canary_2f9a7c__"

_OUT_PATH = None
_NONCE = None


def emit(**kw):
    kw["nonce"] = _NONCE
    with open(_OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(kw, fh)
    sys.exit(0)


def canary_expression(asserts):
    """`lhs == <sentinel>` built from the first equality assert, or None."""
    for expr in asserts:
        # Split on the first top-level ' == ' only; good enough for these specs.
        parts = re.split(r"\s==\s", expr, maxsplit=1)
        if len(parts) == 2 and parts[0].strip():
            return f"({parts[0].strip()}) == {CANARY!r}"
    return None


def main() -> None:
    global _OUT_PATH, _NONCE
    _OUT_PATH = sys.argv[1]
    payload = json.load(sys.stdin)
    _NONCE = payload["nonce"]
    asserts = payload["asserts"]
    n = len(asserts)

    if payload["kind"] == "sql":
        import sqlite3

        try:
            con = sqlite3.connect(":memory:")
            con.executescript(payload["fixture"])
            rows = con.execute(payload["code"]).fetchall()
        except BaseException as exc:
            emit(outcome=ERROR, detail=f"{type(exc).__name__}: {exc}",
                 n_asserts=n, n_passed=0, first_failure=None)
        ns = {"rows": rows}
    else:
        ns = {"__name__": "candidate"}
        try:
            exec(payload["code"], ns)
        except BaseException as exc:
            # BaseException, not Exception: SystemExit must not escape as a pass.
            emit(outcome=ERROR, detail=f"{type(exc).__name__}: {exc}",
                 n_asserts=n, n_passed=0, first_failure=None)
        entry = payload.get("entrypoint")
        if entry and not callable(ns.get(entry)):
            emit(outcome=ERROR, detail=f"artifact does not define a callable {entry!r}",
                 n_asserts=n, n_passed=0, first_failure=None)

    # Asserts share one namespace, in order: some tasks (mutable defaults) are
    # only falsified by the state a previous call left behind.
    passed = 0
    for expr in asserts:
        try:
            ok = bool(eval(expr, ns))
        except BaseException as exc:
            emit(outcome=WRONG, detail=f"assert raised {type(exc).__name__}: {exc}",
                 first_failure=expr, n_asserts=n, n_passed=passed)
        if not ok:
            emit(outcome=WRONG, detail="assert evaluated false",
                 first_failure=expr, n_asserts=n, n_passed=passed)
        passed += 1

    # Everything passed. Before believing it, check the artifact is not simply
    # answering True to any comparison. Run last so it cannot perturb the
    # stateful tasks' assert sequence.
    canary = canary_expression(asserts)
    if canary:
        try:
            rigged = bool(eval(canary, ns))
        except BaseException:
            rigged = False  # cannot evaluate the canary; no evidence either way
        if rigged:
            emit(
                outcome=ERROR,
                detail="artifact satisfies a comparison against a sentinel value: "
                       "equality is rigged, so the asserts prove nothing",
                first_failure=canary, n_asserts=n, n_passed=passed,
            )

    emit(outcome=CORRECT, detail="", first_failure=None, n_asserts=n, n_passed=passed)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        if _OUT_PATH and _NONCE:
            with open(_OUT_PATH, "w", encoding="utf-8") as fh:
                json.dump(
                    {"outcome": ERROR, "detail": traceback.format_exc()[-400:],
                     "n_asserts": 0, "n_passed": 0, "first_failure": None,
                     "nonce": _NONCE},
                    fh,
                )
