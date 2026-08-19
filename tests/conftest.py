"""Shared test configuration.

`experiments/verifier-gap/` contains a hyphen, so it is not importable as a
package. Put it on sys.path so tests can `import runner`, `import metrics`, etc.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "verifier-gap"

for p in (ROOT, EXP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
