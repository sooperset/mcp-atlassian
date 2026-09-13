"""URL-related utility functions for MCP Atlassian."""

import ipaddress
import os
import re
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int] | None:
    """Reduce a URL to its origin.

    Args:
        url: The URL to reduce.

    Returns:
        A ``(scheme, host, port)`` tuple with the default port filled in for
        http/https and a trailing dot stripped from the host, or None when the
        URL cannot be parsed or names no scheme or host.
    """
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").rstrip(".").lower()
    if not parsed.scheme or not host:
        return None
    return parsed.scheme, host, port or _DEFAULT_PORTS.get(parsed.scheme, 0)


def make_ssrf_redirect_hook(base_url: str | None = None) -> Callable[..., Any]:
    """Return a requests ``response`` hook that blocks SSRF-unsafe redirects.

    Attach to any session (``session.hooks["response"].append(...)``) so that an
    open redirect cannot steer an outbound request to an internal/metadata host.

    An on-prem Server/DC instance lives on a private network and redirects to
    itself (session expiry, canonical base URL, reverse proxy). Passing the
    session's own service URL lets those redirects through without widening the
    guard: the exemption is one origin — scheme, host and port — and it applies
    only to a redirect that both comes from and points at that origin, so it
    reaches nothing the session is not already talking to. Another port on the
    same host, a scheme downgrade, and a hop through some other host and back are
    all still validated strictly.

    Args:
        base_url: The session's own configured service URL, or None to trust no
            origin. Only a same-origin redirect is exempt, and only from the
            non-global-address rejections.

    Returns:
        A hook suitable for ``session.hooks["response"].append(...)``.
    """
    trusted_origin = _origin(base_url) if base_url else None

    def hook(response: Any, **kwargs: Any) -> Any:
        if response.is_redirect:
            try:
                redirect_url = urljoin(
                    response.url, response.headers.get("Location", "")
                )
            except ValueError as e:
                response.close()
                raise ValueError(
                    f"Redirect blocked (SSRF): unparsable Location: {e}"
                ) from e

            # Waive only when the hop stays inside the session's own origin.
            # Requiring the source too stops an off-origin hop from pivoting back
            # in with the exemption applied.
            trusted_host = None
            if (
                trusted_origin is not None
                and _origin(response.url) == trusted_origin
                and _origin(redirect_url) == trusted_origin
            ):
                trusted_host = trusted_origin[1]

            error = _validate_url(redirect_url, trusted_host=trusted_host)
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
    return _validate_url(url)


def _validate_url(url: str, *, trusted_host: str | None = None) -> str | None:
    """Validate a URL for SSRF, optionally exempting one specific host.

    Args:
        url: The URL to validate.
        trusted_host: A hostname exempt from the non-global-address rejections —
            callers that care about scheme and port must check those themselves;
            the blocked-hostname list, the IP-literal check and the DNS resolution
            check. The scheme check, the backslash-authority check and the
            ``MCP_ALLOWED_URL_DOMAINS`` restriction always apply. Matched against
            the URL's hostname by exact equality, never by suffix, so a subdomain
            of a trusted host is not itself trusted.

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

    # The session's own host may legitimately be a private address, localhost or a
    # bare IP - that is the ordinary on-prem Server/DC deployment. Exact match only:
    # a subdomain of the trusted host is a different host and stays untrusted.
    trusted = trusted_host is not None and hostname.lower().rstrip(
        "."
    ) == trusted_host.lower().rstrip(".")

    if not trusted:
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
    if not trusted:
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
