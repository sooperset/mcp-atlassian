"""Confluence API integration module.

This module provides access to Confluence content through the Model Context Protocol.
"""

from .analytics import AnalyticsMixin
from .client import ConfluenceClient
from .comments import CommentsMixin
from .config import ConfluenceConfig
from .labels import LabelsMixin
from .pages import PagesMixin
from .search import SearchMixin
from .spaces import SpacesMixin
from .users import UsersMixin


class ConfluenceFetcher(
    SearchMixin,
    SpacesMixin,
    PagesMixin,
    CommentsMixin,
    LabelsMixin,
    UsersMixin,
    AnalyticsMixin,
):
    """Main entry point for Confluence operations, providing backward compatibility.

    This class combines functionality from various mixins to maintain the same
    API as the original ConfluenceFetcher class.

    Available mixins:
    - SearchMixin: CQL search operations
    - SpacesMixin: Space operations
    - PagesMixin: Page operations
    - CommentsMixin: Comment operations
    - LabelsMixin: Label operations
    - UsersMixin: User operations
    - AnalyticsMixin: Page view analytics (Cloud only)
    """

    pass


__all__ = [
    "ConfluenceFetcher",
    "ConfluenceConfig",
    "ConfluenceClient",
    "AnalyticsMixin",
]
