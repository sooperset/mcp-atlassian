"""Constants for Zephyr Scale operations."""

# Default fields to include when fetching test cases
DEFAULT_TEST_CASE_FIELDS = [
    "key",
    "name",
    "objective",
    "precondition",
    "priority",
    "status",
    "projectKey",
    "createdOn",
    "updatedOn",
]

# Test execution statuses
TEST_EXECUTION_STATUSES = ["Pass", "Fail", "Blocked", "Not Executed", "In Progress"]

# Test case priorities
TEST_CASE_PRIORITIES = ["High", "Medium", "Low"]

# Test case statuses
TEST_CASE_STATUSES = ["Draft", "Approved", "Deprecated"]

# Test cycle statuses
TEST_CYCLE_STATUSES = ["Not Started", "In Progress", "Done"]
