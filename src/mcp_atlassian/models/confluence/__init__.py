"""
Confluence data models for the MCP Atlassian integration.
This package provides Pydantic models for Confluence API data structures,
organized by entity type.

Key models:
- ConfluencePage: Complete model for Confluence page content and metadata
- ConfluenceSpace: Space information and settings
- ConfluenceUser: User account details
- ConfluenceSearchResult: Container for Confluence search (CQL) results
- ConfluenceComment: Page and inline comments
- ConfluenceVersion: Content versioning information
"""

from .comment import ConfluenceComment
from .common import ConfluenceAttachment, ConfluenceUser
from .label import ConfluenceLabel
from .page import ConfluencePage, ConfluenceVersion
from .search import ConfluenceSearchResult
from .space import ConfluenceSpace
from .user_search import ConfluenceUserSearchResult, ConfluenceUserSearchResults

__all__ = [
    "ConfluenceUser",
    "ConfluenceAttachment",
    "ConfluenceSpace",
    "ConfluenceVersion",
    "ConfluenceComment",
    "ConfluenceLabel",
    "ConfluencePage",
    "ConfluenceSearchResult",
    "ConfluenceUserSearchResult",
    "ConfluenceUserSearchResults",
]
