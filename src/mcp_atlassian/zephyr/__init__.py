"""Zephyr Essential API module for mcp_atlassian.

This module provides various Zephyr Essential API client implementations.
"""

from .client import ZephyrClient
from .config import ZephyrConfig
from .test_cases import TestCaseMixin
from .test_cycles import TestCycleMixin
from .test_executions import TestExecutionMixin


class ZephyrFetcher(TestCaseMixin, TestCycleMixin, TestExecutionMixin):
    """
    The main Zephyr Essential client class providing access to all Zephyr operations.
    
    This class inherits from multiple mixins that provide specific functionality:
    - TestCaseMixin: Test case operations
    - TestCycleMixin: Test cycle operations
    - TestExecutionMixin: Test execution operations
    
    The class structure is designed to maintain separation of concerns while
    providing a unified interface for Zephyr Essential operations.
    """
    
    pass


__all__ = ["ZephyrFetcher", "ZephyrConfig", "ZephyrClient"]