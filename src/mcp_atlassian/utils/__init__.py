"""
Utility functions for the MCP Atlassian integration.
This package provides various utility functions used throughout the codebase.
"""

# Re-export from modules
from .date import parse_date, parse_date_human_readable, parse_date_ymd
from .io import is_read_only_mode
from .logging import setup_logging
from .ssl import SSLIgnoreAdapter, configure_ssl_verification
from .urls import is_atlassian_cloud_url

# Export all utility functions for backward compatibility
__all__ = [
    "SSLIgnoreAdapter",
    "configure_ssl_verification",
    "is_atlassian_cloud_url",
    "is_read_only_mode",
    "parse_date",
    "parse_date_human_readable",
    "parse_date_ymd",
    "setup_logging",
]
