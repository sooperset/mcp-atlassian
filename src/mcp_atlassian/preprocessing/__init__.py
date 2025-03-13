"""Preprocessing modules for handling text conversion between different formats."""

# Re-export the TextPreprocessor and other utilities
# Backward compatibility
from .base import BasePreprocessor
from .base import BasePreprocessor as TextPreprocessor
from .confluence import ConfluencePreprocessor
from .jira import JiraPreprocessor
from .utils import markdown_to_confluence_storage

__all__ = [
    "BasePreprocessor",
    "ConfluencePreprocessor",
    "JiraPreprocessor",
    "TextPreprocessor",  # For backwards compatibility
    "markdown_to_confluence_storage",
]
