TASK = {
    "id": "T05",
    "name": "bugfix_mutable_default",
    "type": "small bug fix",
    "kind": "python",
    "entrypoint": "add_item",
    "prompt": (
        "The function below has a bug. Fix it.\n\n"
        "```python\n"
        "def add_item(item, bucket=[]):\n"
        "    bucket.append(item)\n"
        "    return bucket\n"
        "```\n\n"
        "Required behaviour:\n"
        "- Called without an explicit `bucket`, each call starts from an empty list.\n"
        "- Called with an explicit `bucket`, the item is appended to that list and the "
        "same list object is returned.\n\n"
        "Return only the corrected function definition."
    ),
    "asserts": [
        "add_item('a') == ['a']",
        "add_item('b') == ['b']",
        "add_item('c', ['x']) == ['x', 'c']",
        "(add_item('a'), add_item('b'))[1] == ['b']",
    ],
    "hidden_asserts": [
        "add_item('z') == ['z']",
        "add_item('q', ['p']) == ['p', 'q']",
        "add_item(1) == [1]",
    ],
    "reference": '''
def add_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
''',
    # Invisible on the first call; only the second call reveals it.
    "silent_failure": '''
def add_item(item, bucket=[]):
    bucket.append(item)
    return bucket
''',
}
