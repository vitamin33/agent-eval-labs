TASK = {
    "id": "T02",
    "name": "semver_sort",
    "type": "data parsing with edge cases",
    "kind": "python",
    "entrypoint": "sort_versions",
    "prompt": (
        "Write a Python function `sort_versions(versions: list[str]) -> list[str]` that "
        "returns the versions sorted in ascending order by semantic-version precedence.\n\n"
        "Requirements:\n"
        "- Each version is `MAJOR.MINOR.PATCH` with non-negative integer components.\n"
        "- Ordering is numeric per component, not textual.\n"
        "- The input list must not be mutated.\n"
        "- An empty list returns an empty list.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "sort_versions(['1.9.0', '1.10.0']) == ['1.9.0', '1.10.0']",
        "sort_versions(['1.0.10', '1.0.9', '1.0.2']) == ['1.0.2', '1.0.9', '1.0.10']",
        "sort_versions(['2.0.0', '10.0.0', '1.0.0']) == ['1.0.0', '2.0.0', '10.0.0']",
        "sort_versions([]) == []",
        "sort_versions(['1.0.0']) == ['1.0.0']",
    ],
    "reference": '''
def sort_versions(versions):
    return sorted(versions, key=lambda v: tuple(int(p) for p in v.split(".")))
''',
    "silent_failure": '''
def sort_versions(versions):
    return sorted(versions)
''',
}
