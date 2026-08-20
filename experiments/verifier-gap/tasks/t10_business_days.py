TASK = {
    "id": "T10",
    "name": "offbyone_business_days",
    "type": "off-by-one algorithmics",
    "kind": "python",
    "entrypoint": "business_days",
    "prompt": (
        "Write a Python function `business_days(start_iso: str, end_iso: str) -> int` that "
        "counts weekdays (Monday-Friday) between two dates, INCLUSIVE of both endpoints.\n\n"
        "Requirements:\n"
        "- Dates are ISO strings, `'YYYY-MM-DD'`.\n"
        "- Both the start date and the end date count if they are weekdays.\n"
        "- If start == end, the answer is 1 for a weekday and 0 for a weekend day.\n"
        "- If end is before start, return 0.\n"
        "- Handle leap years correctly.\n"
        "- Public holidays are NOT considered.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "business_days('2024-02-26', '2024-03-01') == 5",
        "business_days('2024-02-28', '2024-03-01') == 3",
        "business_days('2024-03-01', '2024-03-01') == 1",
        "business_days('2024-03-02', '2024-03-02') == 0",
        "business_days('2024-03-02', '2024-03-03') == 0",
        "business_days('2023-12-29', '2024-01-01') == 2",
        "business_days('2024-03-05', '2024-03-04') == 0",
    ],
    "hidden_asserts": [
        "business_days('2024-07-01', '2024-07-05') == 5",
        "business_days('2024-07-06', '2024-07-07') == 0",
        "business_days('2020-02-27', '2020-03-02') == 3",
        "business_days('2024-12-30', '2025-01-02') == 4",
    ],
    "reference": '''
from datetime import date, timedelta

def business_days(start_iso, end_iso):
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    if end < start:
        return 0
    n, cur = 0, start
    while cur <= end:
        if cur.weekday() < 5:
            n += 1
        cur += timedelta(days=1)
    return n
''',
    # Exclusive of the end date: undercounts by one whenever end is a weekday.
    "silent_failure": '''
from datetime import date, timedelta

def business_days(start_iso, end_iso):
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    if end < start:
        return 0
    n, cur = 0, start
    while cur < end:
        if cur.weekday() < 5:
            n += 1
        cur += timedelta(days=1)
    return n
''',
}
