"""Confluence API integration module.

This module provides access to Confluence content through the Model Context Protocol.
"""

from .client import ConfluenceClient
from .comments import CommentsMixin
from .config import ConfluenceConfig
from .pages import PagesMixin
from .search import SearchMixin
from .spaces import SpacesMixin


class ConfluenceFetcher(SearchMixin, SpacesMixin, PagesMixin, CommentsMixin):
    """Main entry point for Confluence operations, providing backward compatibility.

    This class combines functionality from various mixins to maintain the same
    API as the original ConfluenceFetcher class.
    """

    def get_page_labels(self, page_id: str) -> list[str]:
        """
        Get labels of a specific Confluence page.

        This method calls the implementation in PagesMixin.

        Args:
            page_id: The ID of the page to get labels for.

        Returns:
            List of label strings, or an empty list if an error occurs.
        """
        return super().get_page_labels(page_id)


__all__ = ["ConfluenceFetcher", "ConfluenceConfig", "ConfluenceClient"]
