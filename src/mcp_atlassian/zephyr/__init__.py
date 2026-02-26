"""Zephyr Scale API module for mcp_atlassian.

This module provides Zephyr Scale API client implementations for test management.
"""

from .client import ZephyrClient
from .config import ZephyrConfig
from .testcases import TestCasesMixin
from .testcycles import TestCyclesMixin
from .testexecutions import TestExecutionsMixin


class ZephyrFetcher(
    TestCasesMixin,
    TestCyclesMixin,
    TestExecutionsMixin,
):
    """
    The main Zephyr Scale client class providing access to all Zephyr operations.

    This class inherits from multiple mixins that provide specific functionality:
    - TestCasesMixin: Test case operations
    - TestCyclesMixin: Test cycle operations
    - TestExecutionsMixin: Test execution operations

    The class structure is designed to maintain consistency with the existing
    Jira and Confluence client patterns.
    """

    pass


__all__ = [
    "ZephyrFetcher",
    "ZephyrConfig",
    "ZephyrClient",
    "TestCasesMixin",
    "TestCyclesMixin",
    "TestExecutionsMixin",
]
