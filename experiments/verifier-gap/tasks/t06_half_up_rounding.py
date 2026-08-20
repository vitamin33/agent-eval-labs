TASK = {
    "id": "T06",
    "name": "bugfix_half_up_rounding",
    "type": "small bug fix",
    "kind": "python",
    "entrypoint": "round_money",
    "prompt": (
        "The function below rounds invoice totals to cents. It is wrong for some "
        "inputs. Fix it.\n\n"
        "```python\n"
        "def round_money(x):\n"
        "    return round(x, 2)\n"
        "```\n\n"
        "Required behaviour:\n"
        "- Round to 2 decimal places using half-UP rounding: a value exactly halfway "
        "between two cents rounds AWAY from zero.\n"
        "- `round_money(2.675)` must be `2.68`, not `2.67`.\n"
        "- `round_money(-1.005)` must be `-1.01`.\n"
        "- The input may also be a decimal STRING such as `'2.675'`, which must round "
        "identically to the float.\n"
        "- The result is always a float.\n\n"
        "Return only the corrected function definition."
    ),
    "asserts": [
        "round_money(2.675) == 2.68",
        "round_money(0.125) == 0.13",
        "round_money(1.005) == 1.01",
        "round_money(2.674) == 2.67",
        "round_money(-1.005) == -1.01",
        "round_money('2.675') == 2.68",
        "round_money('0.125') == 0.13",
        "round_money(10.0) == 10.0",
    ],
    "hidden_asserts": [
        "round_money(3.045) == 3.05",
        "round_money('-2.675') == -2.68",
        "round_money(0.005) == 0.01",
        "round_money('7.999') == 8.0",
    ],
    # Decimal(str(x)) is the only route that hits the documented values: the binary
    # float 2.675 is 2.67499999..., so Decimal(x) directly still yields 2.67.
    "reference": '''
from decimal import Decimal, ROUND_HALF_UP

def round_money(x):
    d = Decimal(str(x))
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
''',
    "silent_failure": '''
def round_money(x):
    return round(float(x), 2)
''',
}
