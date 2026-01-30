"""Bitbucket API module for mcp_atlassian.

This module provides Bitbucket API client implementations.
"""

from .client import BitbucketClient
from .config import BitbucketConfig
from .projects import ProjectsMixin
from .pull_requests import PullRequestsMixin


class BitbucketFetcher(
    ProjectsMixin,
    PullRequestsMixin,
):
    """
    The main Bitbucket client class providing access to all Bitbucket operations.

    This class inherits from multiple mixins that provide specific functionality:
    - ProjectsMixin: Project-related operations
    - PullRequestsMixin: Pull request operations

    The class structure is designed to maintain backward compatibility while
    improving code organization and maintainability.
    """

    pass


__all__ = [
    "BitbucketFetcher",
    "BitbucketConfig",
    "BitbucketClient",
]
