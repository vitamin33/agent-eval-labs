TASK = {
    "id": "T08",
    "name": "offbyone_window_max",
    "type": "off-by-one algorithmics",
    "kind": "python",
    "entrypoint": "max_window_sum",
    "prompt": (
        "Write a Python function `max_window_sum(nums: list[int], k: int) -> int | None` "
        "returning the largest sum of any contiguous window of EXACTLY length k.\n\n"
        "Requirements:\n"
        "- If `k` is larger than `len(nums)`, or `nums` is empty, return None.\n"
        "- Windows at the very end of the list must be considered.\n"
        "- Negative numbers are allowed; the answer may be negative.\n"
        "- `k` is a positive integer.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "max_window_sum([1, 2, 3, 4], 2) == 7",
        "max_window_sum([5, 1, 1, 1], 2) == 6",
        "max_window_sum([1, 1, 1, 9], 2) == 10",
        "max_window_sum([1, 2, 3], 3) == 6",
        "max_window_sum([1, 2], 3) is None",
        "max_window_sum([], 1) is None",
        "max_window_sum([-5, -1, -9], 2) == -6",
    ],
    "reference": '''
def max_window_sum(nums, k):
    if not nums or k > len(nums):
        return None
    best = cur = sum(nums[:k])
    for i in range(k, len(nums)):
        cur += nums[i] - nums[i - k]
        if cur > best:
            best = cur
    return best
''',
    # range(len - k) drops the final window; right unless the max sits at the tail.
    "silent_failure": '''
def max_window_sum(nums, k):
    if not nums or k > len(nums):
        return None
    best = None
    for i in range(len(nums) - k):
        s = sum(nums[i:i + k])
        if best is None or s > best:
            best = s
    return best
''',
}
