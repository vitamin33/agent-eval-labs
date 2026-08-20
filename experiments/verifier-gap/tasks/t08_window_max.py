TASK = {
    "id": "T08",
    "name": "offbyone_window_max",
    "type": "off-by-one algorithmics",
    "kind": "python",
    "entrypoint": "max_window_sum",
    "prompt": (
        "Write a Python function `max_window_sum(nums, k)` returning a tuple\n"
        "`(best_sum, start_index)` for the contiguous window of EXACTLY length k with "
        "the largest sum.\n\n"
        "Requirements:\n"
        "- Return None if `nums` is empty, if `k` is larger than `len(nums)`, or if "
        "`k` is 0 or negative.\n"
        "- Windows at the very end of the list must be considered.\n"
        "- On a tie, return the EARLIEST such window's start index.\n"
        "- Negative numbers are allowed; the answer may be negative.\n\n"
        "Return only the function definition."
    ),
    "asserts": [
        "max_window_sum([1, 2, 3, 4], 2) == (7, 2)",
        "max_window_sum([5, 1, 1, 1], 2) == (6, 0)",
        "max_window_sum([1, 1, 1, 9], 2) == (10, 2)",
        "max_window_sum([1, 2, 3], 3) == (6, 0)",
        "max_window_sum([2, 2, 2], 2) == (4, 0)",
        "max_window_sum([1, 2], 3) is None",
        "max_window_sum([], 1) is None",
        "max_window_sum([1, 2, 3], 0) is None",
        "max_window_sum([-5, -1, -9], 2) == (-6, 0)",
    ],
    "hidden_asserts": [
        "max_window_sum([3, 3, 3], 1) == (3, 0)",
        "max_window_sum([0, 0, 100], 3) == (100, 0)",
        "max_window_sum([2, -1, 2, -1, 2], 3) == (3, 0)",
        "max_window_sum([4], 1) == (4, 0)",
        "max_window_sum([1, 2, 3], -1) is None",
    ],
    "reference": '''
def max_window_sum(nums, k):
    if not nums or k <= 0 or k > len(nums):
        return None
    cur = sum(nums[:k])
    best, best_i = cur, 0
    for i in range(k, len(nums)):
        cur += nums[i] - nums[i - k]
        if cur > best:
            best, best_i = cur, i - k + 1
    return (best, best_i)
''',
    # Drops the final window, takes the LAST tied window, and treats k=0 as valid.
    "silent_failure": '''
def max_window_sum(nums, k):
    if not nums or k > len(nums):
        return None
    best, best_i = None, 0
    for i in range(len(nums) - k):
        s = sum(nums[i:i + k])
        if best is None or s >= best:
            best, best_i = s, i
    return (best, best_i)
''',
}
