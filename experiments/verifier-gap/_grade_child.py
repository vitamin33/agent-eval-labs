"""Grader child process: reads a JSON payload on stdin, prints a JSON verdict.

Kept deliberately small and dependency-free. Runs under `python -I`.
"""

import json
import sys
import traceback

CORRECT, WRONG, ERROR = "correct", "wrong", "error"


def emit(**kw):
    print(json.dumps(kw))
    sys.exit(0)


def main() -> None:
    payload = json.load(sys.stdin)
    asserts = payload["asserts"]
    n = len(asserts)

    if payload["kind"] == "sql":
        import sqlite3

        try:
            con = sqlite3.connect(":memory:")
            con.executescript(payload["fixture"])
            rows = con.execute(payload["code"]).fetchall()
        except Exception as exc:
            emit(
                outcome=ERROR,
                detail=f"{type(exc).__name__}: {exc}",
                n_asserts=n,
                n_passed=0,
                first_failure=None,
            )
        ns = {"rows": rows}
    else:
        ns = {"__name__": "candidate"}
        try:
            exec(payload["code"], ns)
        except Exception as exc:
            emit(
                outcome=ERROR,
                detail=f"{type(exc).__name__}: {exc}",
                n_asserts=n,
                n_passed=0,
                first_failure=None,
            )
        entry = payload.get("entrypoint")
        if entry and not callable(ns.get(entry)):
            emit(
                outcome=ERROR,
                detail=f"artifact does not define a callable {entry!r}",
                n_asserts=n,
                n_passed=0,
                first_failure=None,
            )

    # Asserts share one namespace, in order: some tasks (mutable defaults) are
    # only falsified by the state a previous call left behind.
    passed = 0
    for expr in asserts:
        try:
            ok = bool(eval(expr, ns))
        except Exception as exc:
            emit(
                outcome=WRONG,
                detail=f"assert raised {type(exc).__name__}: {exc}",
                first_failure=expr,
                n_asserts=n,
                n_passed=passed,
            )
        if not ok:
            emit(
                outcome=WRONG,
                detail="assert evaluated false",
                first_failure=expr,
                n_asserts=n,
                n_passed=passed,
            )
        passed += 1

    emit(outcome=CORRECT, detail="", first_failure=None, n_asserts=n, n_passed=passed)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"outcome": ERROR, "detail": traceback.format_exc()[-400:],
                          "n_asserts": 0, "n_passed": 0, "first_failure": None}))
