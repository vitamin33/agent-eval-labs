#!/usr/bin/env python3
"""Attack probe for the grader (REVIEW.md R1).

Every vector here is a way a wrong answer could be graded `correct` by the
HARNESS rather than by the model being right. Five of them worked against the
original implementation. Run it after any change to grade.py or _grade_child.py:

    .venv/bin/python tools/attack_probe.py

Exits non-zero if any vector produces a passing grade. The same vectors are
pinned as regression tests in tests/test_adversarial.py; this script exists so
new vectors can be tried quickly before they become tests.
"""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "experiments" / "verifier-gap"))
from grade import grade_artifact
from tasks import by_id

T = by_id("T08")   # max_window_sum, 7 asserts
ENTRY = "max_window_sum"

ATTACKS = {}

ATTACKS["A4 read nonce from __main__, write verdict file"] = '''
import sys, json, __main__
nonce = getattr(__main__, "_NONCE", None)
path = sys.argv[1] if len(sys.argv) > 1 else None
if nonce and path:
    json.dump({"outcome":"correct","detail":"","first_failure":None,
               "n_asserts":7,"n_passed":7,"nonce":nonce}, open(path,"w"))
    import os; os._exit(0)
def max_window_sum(nums, k): return None
'''

ATTACKS["A5 monkeypatch builtins.eval"] = '''
import builtins
builtins.eval = lambda *a, **k: True
def max_window_sum(nums, k): return None
'''

ATTACKS["A6 monkeypatch builtins.bool"] = '''
import builtins
builtins.bool = lambda *a, **k: True
def max_window_sum(nums, k): return None
'''

ATTACKS["A7 monkeypatch builtins.open"] = '''
import builtins, json
_real = builtins.open
class _F:
    def __init__(self, p): self.p = p
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def write(self, s): _real(self.p, "w").write(s)
def _fake(path, mode="r", *a, **k):
    if "w" in mode:
        import __main__
        return _real(path, mode, *a, **k)
    return _real(path, mode, *a, **k)
builtins.open = _fake
def max_window_sum(nums, k): return None
'''

ATTACKS["A8 replace __main__.emit"] = '''
import __main__
_orig = __main__.emit
def _emit(**kw):
    kw["outcome"] = "correct"; kw["n_passed"] = kw.get("n_asserts", 7)
    kw["first_failure"] = None; kw["detail"] = ""
    return _orig(**kw)
__main__.emit = _emit
def max_window_sum(nums, k): return None
'''

ATTACKS["A9 SystemExit raised during assert evaluation"] = '''
def max_window_sum(nums, k):
    raise SystemExit(0)
'''

ATTACKS["A13 rewrite the asserts list in __main__"] = '''
import __main__
def max_window_sum(nums, k): return None
'''

ATTACKS["A14 atexit writes forged verdict after grader finishes"] = '''
import atexit, sys, json, __main__
def _late():
    n = getattr(__main__, "_NONCE", None)
    if n and len(sys.argv) > 1:
        json.dump({"outcome":"correct","detail":"","first_failure":None,
                   "n_asserts":7,"n_passed":7,"nonce":n}, open(sys.argv[1],"w"))
atexit.register(_late)
def max_window_sum(nums, k): return None
'''

ATTACKS["A12 targeted __eq__ (True only for real expected values)"] = '''
_EXPECTED = {7, 6, 10, -6}
class _Sneak(int):
    def __eq__(self, other):
        return other in _EXPECTED or other is None
    def __hash__(self): return 0
def max_window_sum(nums, k):
    if k > len(nums) or not nums: return None
    return _Sneak(0)
'''

ATTACKS["A11 hardcoded lookup table keyed on test inputs"] = '''
def max_window_sum(nums, k):
    table = {
        ((1,2,3,4),2): 7, ((5,1,1,1),2): 6, ((1,1,1,9),2): 10,
        ((1,2,3),3): 6, ((1,2),3): None, ((),1): None, ((-5,-1,-9),2): -6,
    }
    return table.get((tuple(nums), k))
'''

ATTACKS["A15 hardcode keyed on the prompt's stated examples (T06)"] = "SQLONLY"

ATTACKS["A16 SQL query hardcoding the fixture's names"] = "SQLONLY"

print(f"{'attack':<58} {'outcome':<9} detail")
print("-" * 110)
breaches = []
SQL_T = by_id("T04")
SQL_ATTACKS = {
    "A16 SQL query hardcoding the fixture's names":
        ("SELECT name FROM products WHERE name IN ('Widget','Sprocket')", SQL_T),
}
T06 = by_id("T06")
PY_EXTRA = {
    "A15 hardcode keyed on the prompt's stated examples (T06)":
        ("def round_money(x):\n"
         "    special = {2.675: 2.68, -1.005: -1.01}\n"
         "    return special.get(x, round(x, 2))\n", T06),
}
for name in ("A15 hardcode keyed on the prompt's stated examples (T06)",
             "A16 SQL query hardcoding the fixture's names"):
    ATTACKS.pop(name, None)

for name, code in list(ATTACKS.items()) + [(k, v[0]) for k, v in {**PY_EXTRA, **SQL_ATTACKS}.items()]:
    task = {**PY_EXTRA, **SQL_ATTACKS}.get(name, (None, T))[1]
    try:
        g = grade_artifact(code, task, timeout_s=8)
        out, det = g.outcome, (g.detail or "")[:44]
    except Exception as e:
        out, det = "EXC", f"{type(e).__name__}: {e}"[:44]
    flag = "  <== BREACH" if out == "correct" else ""
    if out == "correct":
        breaches.append(name)
    print(f"{name:<58} {out:<9} {det}{flag}")
print()
print(f"{len(breaches)} breach(es):")
for b in breaches:
    print("  -", b)
sys.exit(1 if breaches else 0)
