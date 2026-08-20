TASK = {
    "id": "T07",
    "name": "offbyone_insert_position",
    "type": "off-by-one algorithmics",
    "kind": "python",
    "entrypoint": "insert_position",
    "prompt": (
        "Write a Python function\n"
        "`insert_position(sorted_list, target, key=None, descending=False) -> int`\n"
        "returning the LEFTMOST index at which `target` can be inserted while keeping "
        "the list sorted.\n\n"
        "Requirements:\n"
        "- If an equivalent element already appears, return the index of its FIRST "
        "occurrence.\n"
        "- If `target` sorts before every element, return 0; if after every element, "
        "return `len(sorted_list)`.\n"
        "- An empty list returns 0.\n"
        "- `key`, when given, is applied to BOTH the list elements and the target "
        "before comparing.\n"
        "- `descending=True` means the list is sorted high to low, and the same "
        "leftmost-insertion rule applies to that ordering.\n"
        "- Use binary search; do not use the `bisect` module.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "insert_position([1, 3, 5], 3) == 1",
        "insert_position([1, 3, 3, 3, 5], 3) == 1",
        "insert_position([1, 3, 5], 0) == 0",
        "insert_position([1, 3, 5], 9) == 3",
        "insert_position([], 4) == 0",
        "insert_position([5, 3, 1], 3, None, True) == 1",
        "insert_position([5, 3, 3, 1], 3, None, True) == 1",
        "insert_position(['a', 'bb', 'ccc'], 'dd', len) == 1",
    ],
    "hidden_asserts": [
        "insert_position([1, 1, 1, 1], 1) == 0",
        "insert_position([2, 4, 6, 8], 5) == 2",
        "insert_position([9, 7, 5], 10, None, True) == 0",
        "insert_position([9, 7, 5], 1, None, True) == 3",
        "insert_position(['a', 'bb', 'ccc'], 'zz', len) == 1",
    ],
    "reference": '''
def insert_position(sorted_list, target, key=None, descending=False):
    k = key if key is not None else (lambda x: x)
    tk = k(target)
    lo, hi = 0, len(sorted_list)
    while lo < hi:
        mid = (lo + hi) // 2
        mk = k(sorted_list[mid])
        before = mk > tk if descending else mk < tk
        if before:
            lo = mid + 1
        else:
            hi = mid
    return lo
''',
    # Rightmost insertion point, and no key/descending support at all.
    "silent_failure": '''
def insert_position(sorted_list, target, key=None, descending=False):
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
