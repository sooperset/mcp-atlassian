"""URL-related utility functions for MCP Atlassian."""

import ipaddress
import os
import re
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse


def make_ssrf_redirect_hook() -> Callable[..., Any]:
    """Return a requests ``response`` hook that blocks SSRF-unsafe redirects.

    Attach to any session (``session.hooks["response"].append(...)``) so that an
    open redirect cannot steer an outbound request to an internal/metadata host.
    """

    def hook(response: Any, **kwargs: Any) -> Any:
        if response.is_redirect:
            redirect_url = urljoin(response.url, response.headers.get("Location", ""))
            error = validate_url_for_ssrf(redirect_url)
            if error:
                response.close()
                raise ValueError(f"Redirect blocked (SSRF): {error}")
        return response

    return hook


def resolve_relative_url(url: str, base_url: str) -> str:
    """Resolve a relative URL against a base URL.

    Only modifies URLs that start with '/'. Absolute URLs are returned as-is.

    Args:
        url: The URL to resolve (may be relative or absolute).
        base_url: The base URL to prepend for relative URLs.

    Returns:
        The resolved absolute URL.
    """
    if url.startswith("/"):
        # Strip trailing slash from base_url to avoid double slashes
        return base_url.rstrip("/") + url
    return url


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
    # Use endswith() to prevent URL validation bypass via substring matching
    # Includes US Government cloud domains (FedRAMP Moderate/High)
    return (
        hostname.endswith(".atlassian.net")
        or hostname.endswith(".jira.com")
        or hostname.endswith(".jira-dev.com")
        or hostname == "api.atlassian.com"
        or hostname.endswith(".atlassian.com")
        or hostname.endswith(".atlassian-us-gov-mod.net")  # US Gov Moderate (FedRAMP)
        or hostname.endswith(".atlassian-us-gov.net")  # US Gov (FedRAMP)
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

    # requests (and browsers, per WHATWG) treat a backslash in the authority as a
    # path separator, so "http://localhost\@evil.com/" parses (urlparse) to host
    # evil.com but actually connects to localhost. Reject the parse mismatch.
    if "\\" in parsed.netloc:
        return f"Blocked backslash in URL authority: {url}"

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
        # Allowlisted hosts may live on a private network (on-prem DC), but
        # never on loopback, link-local or a cloud-metadata address: the domain
        # trust must not extend to whatever a subdomain happens to resolve to.
        return _check_dns_resolution(hostname, allow_private=True)

    # DNS resolution check - resolve hostname and check all IPs
    dns_error = _check_dns_resolution(hostname)
    if dns_error:
        return dns_error

    return None


# NAT64 prefixes (RFC 6052 well-known, RFC 8215 local-use). The well-known
# /96 prefix carries the IPv4 address in its last 32 bits; the local-use /48
# prefix lets operators pick the embedding length, so it is rejected outright.
_NAT64_WELL_KNOWN = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_LOCAL_USE = ipaddress.IPv6Network("64:ff9b:1::/48")
# IPv4-compatible IPv6 (RFC 4291, deprecated): ::a.b.c.d in ::/96.
_IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")


def _embedded_ipv4(addr: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """Return the IPv4 address an IPv6 transition form routes to, if any.

    Covers IPv4-mapped (``::ffff:a.b.c.d``), 6to4 (``2002::/16``), NAT64
    well-known prefix (``64:ff9b::/96``) and IPv4-compatible (``::a.b.c.d``).
    ``ipaddress`` reports several of these as global regardless of the IPv4
    they wrap, so a guard must judge the embedded address instead.

    Args:
        addr: The IPv6 address to inspect.

    Returns:
        The embedded IPv4 address, or None when ``addr`` carries none.
    """
    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    if addr.sixtofour is not None:
        return addr.sixtofour
    if addr in _NAT64_WELL_KNOWN or (addr in _IPV4_COMPATIBLE and int(addr) > 0xFFFF):
        # ``int(addr) > 0xFFFF`` leaves ``::`` and ``::1`` to the IPv6 checks.
        return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return None


# Cloud metadata services outside the link-local range.
_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("fd00:ec2::254"),  # AWS IMDS over IPv6
        ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud metadata
    }
)


def _is_blocked_ip(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private: bool = False,
) -> bool:
    """Return True when ``addr`` (or the IPv4 it embeds) must not be contacted.

    Args:
        addr: The address to judge.
        allow_private: Accept private-network addresses (RFC 1918, ULA, CGNAT)
            for operator-allowlisted hosts. Loopback, link-local, unspecified,
            multicast and cloud-metadata addresses stay blocked.

    Returns:
        True if the address must be blocked.
    """
    if isinstance(addr, ipaddress.IPv6Address):
        if addr in _NAT64_LOCAL_USE:
            return True
        embedded = _embedded_ipv4(addr)
        if embedded is not None:
            addr = embedded
    if addr.is_multicast:
        # ipaddress reports some multicast ranges (e.g. 224.0.0.1, ff0e::1)
        # as global; a guarded request never has a multicast destination.
        return True
    if addr.is_global:
        return False
    if not allow_private:
        return True
    return (
        addr.is_loopback
        or addr.is_link_local
        or addr.is_unspecified
        or addr.is_multicast
        or addr in _METADATA_ADDRESSES
    )


def _check_ip_address(hostname: str, *, allow_private: bool = False) -> str | None:
    """Check if hostname is a blocked IP address.

    Args:
        hostname: The hostname to check.
        allow_private: Accept private-network addresses (see ``_is_blocked_ip``).

    Returns:
        None if safe, error message string if blocked.
    """
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return None  # Not an IP literal - skip

    if _is_blocked_ip(addr, allow_private=allow_private):
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


def _check_dns_resolution(hostname: str, *, allow_private: bool = False) -> str | None:
    """Resolve hostname via DNS and check if any IP is non-global.

    Args:
        hostname: The hostname to resolve and check.
        allow_private: Accept private-network addresses for an allowlisted
            host. A resolution failure is then not an error either, because
            the connect-time pinning adapter re-checks whatever resolves later.

    Returns:
        None if safe, error message string if blocked.
    """
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        if allow_private:
            return None
        return f"DNS resolution failed for {hostname}"
    except (OSError, UnicodeError):
        if allow_private:
            return None
        return f"DNS resolution error for {hostname}"

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
            if _is_blocked_ip(addr, allow_private=allow_private):
                return f"DNS for {hostname} resolves to non-global IP: {ip_str}"
        except ValueError:
            continue

    return None
