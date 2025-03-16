"""Preprocessing modules for handling text conversion between different formats."""

# Re-export the TextPreprocessor and other utilities
# Backward compatibility
from .base import BasePreprocessor
from .base import BasePreprocessor as TextPreprocessor
from .confluence import ConfluencePreprocessor
from .jira import JiraPreprocessor

__all__ = [
    "BasePreprocessor",
    "ConfluencePreprocessor",
    "JiraPreprocessor",
    "TextPreprocessor",  # For backwards compatibility
]
