TASK = {
    "id": "T07",
    "name": "offbyone_insert_position",
    "type": "off-by-one algorithmics",
    "kind": "python",
    "entrypoint": "insert_position",
    "prompt": (
        "Write a Python function `insert_position(sorted_list: list[int], target: int) -> int` "
        "that returns the LEFTMOST index at which `target` can be inserted while keeping "
        "`sorted_list` sorted.\n\n"
        "Requirements:\n"
        "- If `target` already appears, return the index of its FIRST occurrence.\n"
        "- If `target` is smaller than every element, return 0.\n"
        "- If `target` is larger than every element, return `len(sorted_list)`.\n"
        "- An empty list returns 0.\n"
        "- Use binary search; do not use the `bisect` module.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "insert_position([1, 3, 5], 3) == 1",
        "insert_position([1, 3, 3, 3, 5], 3) == 1",
        "insert_position([1, 3, 5], 0) == 0",
        "insert_position([1, 3, 5], 9) == 3",
        "insert_position([], 4) == 0",
        "insert_position([2, 2], 2) == 0",
    ],
    "hidden_asserts": [
        "insert_position([1, 1, 1, 1], 1) == 0",
        "insert_position([2, 4, 6, 8], 5) == 2",
        "insert_position([7], 7) == 0",
        "insert_position([1, 2, 3, 4, 5, 6, 7], 8) == 7",
    ],
    "reference": '''
def insert_position(sorted_list, target):
    lo, hi = 0, len(sorted_list)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_list[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo
''',
    # Rightmost insertion point: identical on distinct elements, wrong on duplicates.
    "silent_failure": '''
def insert_position(sorted_list, target):
    lo, hi = 0, len(sorted_list)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_list[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo
''',
}
