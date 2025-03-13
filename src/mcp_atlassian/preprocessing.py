"""
Preprocessing module for Confluence and Jira content.

This module is maintained for backwards compatibility.
New code should use the modules in the preprocessing/ directory directly.
"""

# Re-export specific components from the preprocessing package for backwards compatibility
from .preprocessing.base import BasePreprocessor
from .preprocessing.base import BasePreprocessor as TextPreprocessor
from .preprocessing.confluence import ConfluencePreprocessor
from .preprocessing.jira import JiraPreprocessor
from .preprocessing.utils import markdown_to_confluence_storage

__all__ = [
    "BasePreprocessor",
    "TextPreprocessor",
    "ConfluencePreprocessor",
    "JiraPreprocessor",
    "markdown_to_confluence_storage",
]
