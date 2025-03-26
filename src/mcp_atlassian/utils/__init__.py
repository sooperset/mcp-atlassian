"""
Utility functions for the MCP Atlassian integration.
This package provides various utility functions used throughout the codebase.
"""

# Re-export from ssl module
# Re-export from io module
from .io import is_read_only_mode

# Export new logging utilities
from .logging import setup_logging
from .ssl import SSLIgnoreAdapter, configure_ssl_verification

# Re-export from urls module
from .urls import is_atlassian_cloud_url

# Export all utility functions for backward compatibility
__all__ = [
    "SSLIgnoreAdapter",
    "configure_ssl_verification",
    "is_atlassian_cloud_url",
    "is_read_only_mode",
    "setup_logging",
]
