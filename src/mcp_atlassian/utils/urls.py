"""URL-related utility functions for MCP Atlassian."""

import re
from urllib.parse import urlparse


def is_atlassian_cloud_url(url: str) -> bool:
    """Determine if a URL belongs to Atlassian Cloud or Server/Data Center.

    Args:
        url: The URL to check

    Returns:
        True if the URL is for an Atlassian Cloud instance, False for Server/Data Center
    """
    # Localhost and IP-based URLs are always Server/Data Center
    if url is None or not url:
        return False

    parsed_url = urlparse(url)
    hostname = parsed_url.hostname or ""

    # Check for localhost or IP address
    if (
        hostname == "localhost"
        or re.match(r"^127\.", hostname)
        or re.match(r"^192\.168\.", hostname)
        or re.match(r"^10\.", hostname)
        or re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", hostname)
    ):
        return False

    # The standard check for Atlassian cloud domains
    return (
        ".atlassian.net" in hostname
        or ".jira.com" in hostname
        or ".jira-dev.com" in hostname
    )
