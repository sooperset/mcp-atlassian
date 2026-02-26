"""URL-related utility functions for MCP Atlassian."""

import ipaddress
import os
import re
import socket
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
    # Includes US Government cloud domains (FedRAMP Moderate/High)
    return (
        ".atlassian.net" in hostname
        or ".jira.com" in hostname
        or ".jira-dev.com" in hostname
        or "api.atlassian.com" in hostname
        or ".atlassian-us-gov-mod.net" in hostname  # US Gov Moderate (FedRAMP)
        or ".atlassian-us-gov.net" in hostname  # US Gov (FedRAMP)
        or "zephyrscale.smartbear.com" in hostname
    )


def validate_url_for_ssrf(url: str) -> str | None:
    """Validate a URL to prevent SSRF attacks.

    Returns None if the URL is safe, or an error message string
    describing why it was blocked.

    Args:
        url: The URL to validate.

    Returns:
        None if safe, error message string if blocked.
    """
    if not url or not url.strip():
        return "Empty URL"

    try:
        parsed = urlparse(url)
    except Exception:
        return f"Invalid URL: {url}"

    # Scheme check
    if parsed.scheme not in ("http", "https"):
        return f"Blocked scheme: {parsed.scheme} (only http/https allowed)"

    hostname = parsed.hostname
    if not hostname:
        return "No hostname in URL"

    # Check blocked hostnames
    blocked_hostnames = {"localhost", "metadata.google.internal"}
    if hostname.lower() in blocked_hostnames:
        return f"Blocked hostname: {hostname}"

    # Check if hostname is an IP address
    ip_error = _check_ip_address(hostname)
    if ip_error:
        return ip_error

    # Domain allowlist check
    allowlist = _get_domain_allowlist()
    if allowlist is not None:
        if not _hostname_matches_allowlist(hostname, allowlist):
            return f"Hostname {hostname} not in allowed domains"
        return None  # explicitly allowlisted — skip DNS check

    # DNS resolution check - resolve hostname and check all IPs
    dns_error = _check_dns_resolution(hostname)
    if dns_error:
        return dns_error

    return None


def _check_ip_address(hostname: str) -> str | None:
    """Check if hostname is a blocked IP address.

    Args:
        hostname: The hostname to check.

    Returns:
        None if safe, error message string if blocked.
    """
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return None  # Not an IP literal - skip

    # Handle IPv4-mapped IPv6 (e.g., ::ffff:127.0.0.1)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped

    if not addr.is_global:
        return f"Blocked IP address: {hostname} (non-global)"

    return None


def _get_domain_allowlist() -> list[str] | None:
    """Get domain allowlist from environment variable.

    Returns:
        List of allowed domain strings, or None if not set.
    """
    raw = os.environ.get("MCP_ALLOWED_URL_DOMAINS", "").strip()
    if not raw:
        return None
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _hostname_matches_allowlist(
    hostname: str,
    allowlist: list[str],
) -> bool:
    """Check if hostname matches any entry in the allowlist.

    Args:
        hostname: The hostname to check.
        allowlist: List of allowed domain strings.

    Returns:
        True if hostname matches, False otherwise.
    """
    hostname_lower = hostname.lower()
    for domain in allowlist:
        if hostname_lower == domain or hostname_lower.endswith(f".{domain}"):
            return True
    return False


def _check_dns_resolution(hostname: str) -> str | None:
    """Resolve hostname via DNS and check if any IP is non-global.

    Args:
        hostname: The hostname to resolve and check.

    Returns:
        None if safe, error message string if blocked.
    """
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return f"DNS resolution failed for {hostname}"
    except (OSError, UnicodeError):
        return f"DNS resolution error for {hostname}"

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
            # Handle IPv4-mapped IPv6
            if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
                addr = addr.ipv4_mapped
            if not addr.is_global:
                return f"DNS for {hostname} resolves to non-global IP: {ip_str}"
        except ValueError:
            continue

    return None
