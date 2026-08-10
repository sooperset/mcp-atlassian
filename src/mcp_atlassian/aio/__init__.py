"""AIO Tests API module for mcp_atlassian.

Provides the client used to talk to the AIO Tests REST API, which powers test
management inside Jira.
"""

from .cases import TestCasesMixin
from .client import AIOApiError, AIOClient
from .config import AIOConfig, is_aio_enabled
from .folders import FoldersMixin
from .projects import ProjectsMixin
from .tags import TagsMixin


class AIOFetcher(TestCasesMixin, ProjectsMixin, FoldersMixin, TagsMixin):
    """The main AIO Tests client providing access to all AIO Tests operations.

    This class inherits from multiple mixins that provide specific functionality:
    - TestCasesMixin: Test case search, read, create and update operations
    - ProjectsMixin: Project configuration and test case schema operations
    - FoldersMixin: Folder hierarchy operations
    - TagsMixin: Tag operations
    """

    pass


__all__ = [
    "AIOApiError",
    "AIOClient",
    "AIOConfig",
    "AIOFetcher",
    "FoldersMixin",
    "ProjectsMixin",
    "TagsMixin",
    "TestCasesMixin",
    "is_aio_enabled",
]
