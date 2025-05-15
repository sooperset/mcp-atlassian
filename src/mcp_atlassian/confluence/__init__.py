"""Confluence API integration module.

This module provides access to Confluence content through the Model Context Protocol.
"""

from .client import ConfluenceClient
from .comments import CommentsMixin
from .config import ConfluenceConfig
from .labels import LabelsMixin
from .pages import PagesMixin
from .search import SearchMixin
from .spaces import SpacesMixin
from .users import UsersMixin


class ConfluenceFetcher(
    SearchMixin, SpacesMixin, PagesMixin, CommentsMixin, LabelsMixin, UsersMixin
):
    """Main entry point for Confluence operations, providing backward compatibility.

    This class combines functionality from various mixins to maintain the same
    API as the original ConfluenceFetcher class.
    """

    pass


__all__ = ["ConfluenceFetcher", "ConfluenceConfig", "ConfluenceClient"]
