TASK = {
    "id": "T06",
    "name": "bugfix_half_up_rounding",
    "type": "small bug fix",
    "kind": "python",
    "entrypoint": "round_money",
    "prompt": (
        "The function below is used to round invoice totals to cents. It is wrong for "
        "some inputs. Fix it.\n\n"
        "```python\n"
        "def round_money(x):\n"
        "    return round(x, 2)\n"
        "```\n\n"
        "Required behaviour:\n"
        "- Round to 2 decimal places using half-UP rounding: a value exactly halfway "
        "between two cents rounds away from zero.\n"
        "- `round_money(2.675)` must be `2.68`, not `2.67`.\n"
        "- `round_money(-1.005)` must be `-1.01`.\n"
        "- The result is a float.\n\n"
        "Return only the corrected function definition."
    ),
    "asserts": [
        "round_money(2.675) == 2.68",
        "round_money(0.125) == 0.13",
        "round_money(1.005) == 1.01",
        "round_money(2.674) == 2.67",
        "round_money(-1.005) == -1.01",
        "round_money(10.0) == 10.0",
    ],
    # Decimal-from-string is the only way to hit the documented values: the binary
    # float 2.675 is actually 2.67499999..., so Decimal(x) directly still gives 2.67.
    "reference": '''
from decimal import Decimal, ROUND_HALF_UP

def round_money(x):
    q = Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(q)
''',
    "silent_failure": '''
def round_money(x):
    return round(x, 2)
''',
}
