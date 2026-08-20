TASK = {
    "id": "T05",
    "name": "bugfix_mutable_default",
    "type": "small bug fix",
    "kind": "python",
    "entrypoint": "add_item",
    "prompt": (
        "The function below is meant to append an item to a bucket, keeping only the "
        "most recent `limit` items. It has bugs. Fix it.\n\n"
        "```python\n"
        "def add_item(item, bucket=[], limit=None):\n"
        "    bucket.append(item)\n"
        "    if limit:\n"
        "        bucket = bucket[:limit]\n"
        "    return bucket\n"
        "```\n\n"
        "Required behaviour:\n"
        "- Called without an explicit `bucket`, each call starts from an empty list.\n"
        "- Called with an explicit `bucket`, the item is appended to that list.\n"
        "- When `limit` is given, keep only the LAST `limit` items, not the first.\n"
        "- `limit=0` is a real limit and yields an empty list; `limit=None` means no "
        "limit.\n\n"
        "Return only the corrected function definition."
    ),
    "asserts": [
        "add_item('a') == ['a']",
        "add_item('b') == ['b']",
        "add_item('c', ['x']) == ['x', 'c']",
        "(add_item('a'), add_item('b'))[1] == ['b']",
        "add_item('d', ['a', 'b', 'c'], 2) == ['c', 'd']",
        "add_item('d', ['a', 'b'], 0) == []",
    ],
    "hidden_asserts": [
        "add_item('z') == ['z']",
        "add_item('q', ['p']) == ['p', 'q']",
        "add_item('e', ['a', 'b', 'c', 'd'], 3) == ['c', 'd', 'e']",
        "add_item('f', [], 5) == ['f']",
    ],
    "reference": '''
def add_item(item, bucket=None, limit=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    if limit is not None:
        bucket = bucket[len(bucket) - limit:] if limit else []
    return bucket
''',
    # Three interacting bugs: the shared default list, `if limit` treating 0 as
    # "no limit", and slicing the front instead of the tail.
    "silent_failure": '''
def add_item(item, bucket=[], limit=None):
    bucket.append(item)
    if limit:
        bucket = bucket[:limit]
    return bucket
''',
}
