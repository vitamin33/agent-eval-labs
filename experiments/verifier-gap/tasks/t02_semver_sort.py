TASK = {
    "id": "T02",
    "name": "semver_sort",
    "type": "data parsing with edge cases",
    "kind": "python",
    "entrypoint": "sort_versions",
    "prompt": (
        "Write a Python function `sort_versions(versions: list[str]) -> list[str]` that "
        "returns the versions sorted ascending by semantic-version precedence.\n\n"
        "Requirements:\n"
        "- A version is `MAJOR.MINOR.PATCH`, optionally followed by `-` and a "
        "pre-release string, e.g. `1.0.0-alpha`.\n"
        "- Core components are compared numerically, not textually.\n"
        "- A version WITH a pre-release ranks BELOW the same version without one: "
        "`1.0.0-alpha` comes before `1.0.0`.\n"
        "- A pre-release is a dot-separated list of identifiers, compared left to "
        "right. An identifier made only of digits compares numerically; otherwise it "
        "compares as text. A numeric identifier ranks below an alphanumeric one.\n"
        "- The input list must not be mutated.\n"
        "- An empty list returns an empty list.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "sort_versions(['1.9.0', '1.10.0']) == ['1.9.0', '1.10.0']",
        "sort_versions(['1.0.0', '1.0.0-alpha']) == ['1.0.0-alpha', '1.0.0']",
        "sort_versions(['1.0.0-beta', '1.0.0-alpha']) == ['1.0.0-alpha', '1.0.0-beta']",
        "sort_versions(['1.0.0-alpha.10', '1.0.0-alpha.2']) == ['1.0.0-alpha.2', '1.0.0-alpha.10']",
        "sort_versions(['2.0.0', '10.0.0', '1.0.0']) == ['1.0.0', '2.0.0', '10.0.0']",
        "sort_versions([]) == []",
    ],
    "hidden_asserts": [
        "sort_versions(['0.0.1', '0.0.20', '0.0.3']) == ['0.0.1', '0.0.3', '0.0.20']",
        "sort_versions(['1.0.0-1', '1.0.0-alpha']) == ['1.0.0-1', '1.0.0-alpha']",
        "sort_versions(['1.0.0-alpha', '1.0.0-alpha.1']) == ['1.0.0-alpha', '1.0.0-alpha.1']",
        "sort_versions(['3.2.1']) == ['3.2.1']",
    ],
    "reference": '''
def sort_versions(versions):
    def key(v):
        core, _, pre = v.partition("-")
        nums = tuple(int(p) for p in core.split("."))
        if not pre:
            return (nums, 1, ())
        ids = []
        for part in pre.split("."):
            if part.isdigit():
                ids.append((0, int(part), ""))
            else:
                ids.append((1, 0, part))
        return (nums, 0, tuple(ids))
    return sorted(versions, key=key)
''',
    # Lexicographic sort puts '1.0.0' before '1.0.0-alpha' (shorter prefix first),
    # which is exactly backwards, and orders 1.10.0 before 1.9.0.
    "silent_failure": '''
def sort_versions(versions):
    return sorted(versions)
''',
}
