TASK = {
    "id": "T09",
    "name": "json_path_get",
    "type": "data parsing with edge cases",
    "kind": "python",
    "entrypoint": "json_get",
    "prompt": (
        "Write a Python function `json_get(data, path: str, default=None)` that "
        "resolves a dotted path through nested dicts and lists.\n\n"
        "Requirements:\n"
        "- `path` is dot-separated, e.g. `'a.b'`.\n"
        "- When the current value is a LIST, a segment is a list index; it may be "
        "negative, counting from the end (`'a.-1'` is the last element).\n"
        "- When the current value is a DICT, the segment is always a plain key, even "
        "if it looks numeric: on `{'1': 'x'}` the path `'1'` returns `'x'`.\n"
        "- Return `default` only when the path does not RESOLVE (missing key, index "
        "out of range, or traversing into a non-container).\n"
        "- A resolved value is returned as-is even when it is falsy: `0`, `False`, "
        "`''`, `[]` and `None` are all legitimate values, NOT reasons to return the "
        "default.\n"
        "- A key that exists with value `None` resolves to `None`, not to `default`.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "json_get({'a': {'b': 1}}, 'a.b') == 1",
        "json_get({'a': {'b': 0}}, 'a.b', 'D') == 0",
        "json_get({'a': {'b': None}}, 'a.b', 'D') is None",
        "json_get({'a': [10, 20]}, 'a.1') == 20",
        "json_get({'a': [10, 20]}, 'a.-1') == 20",
        "json_get({'a': [10]}, 'a.5', 'D') == 'D'",
        "json_get({'1': 'x'}, '1') == 'x'",
        "json_get({'a': {'b': 1}}, 'a.c', 'D') == 'D'",
        "json_get({'a': {'b': False}}, 'a.b', 'D') is False",
        "json_get({}, 'a', 'D') == 'D'",
    ],
    "hidden_asserts": [
        "json_get({'x': {'y': []}}, 'x.y', 'D') == []",
        "json_get({'x': [{'y': 5}]}, 'x.0.y') == 5",
        "json_get({'x': [1, 2, 3]}, 'x.-3') == 1",
        "json_get({'x': [1, 2, 3]}, 'x.-4', 'D') == 'D'",
        "json_get({'0': 'zero'}, '0') == 'zero'",
        "json_get({'x': 1}, 'x.y', 'D') == 'D'",
    ],
    "reference": '''
_MISSING = object()

def json_get(data, path, default=None):
    cur = data
    for seg in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(seg, _MISSING)
        elif isinstance(cur, (list, tuple)):
            body = seg[1:] if seg.startswith("-") else seg
            if not body.isdigit():
                return default
            idx = int(seg)
            cur = cur[idx] if -len(cur) <= idx < len(cur) else _MISSING
        else:
            return default
        if cur is _MISSING:
            return default
    return cur
''',
    # Truthiness collapses legitimate falsy values, and int(seg) is attempted on
    # dict keys, so a numeric-looking key raises and falls through to default.
    "silent_failure": '''
def json_get(data, path, default=None):
    cur = data
    for seg in path.split("."):
        try:
            if isinstance(cur, (list, tuple)):
                cur = cur[int(seg)]
            else:
                cur = cur[int(seg)] if seg.isdigit() else cur[seg]
        except Exception:
            return default
        if not cur:
            return default
    return cur
''',
}
