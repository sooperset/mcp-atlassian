"""A requests transport adapter that pins DNS resolution against SSRF.

``validate_url_for_ssrf`` resolves and checks a host once (in middleware), but the
outbound request re-resolves the hostname at connect time, so a DNS-rebinding
response can swap in an internal address between validation and connection — the
TOCTOU that bypasses a validate-then-reconnect SSRF guard (GHSA-49xv, 72fm, 489g).

This adapter closes that window at the connection itself: it resolves each host
exactly once, rejects any candidate address that is not globally routable
(cloud-metadata / private / loopback), and connects to that same validated
address — there is no separate re-resolution to rebind. The original hostname is
preserved for TLS SNI and certificate verification, so HTTPS is unaffected.

The configured ``JIRA_URL`` / ``CONFLUENCE_URL`` hosts are exempt from the
non-global rejection (on-prem DC instances legitimately live on private networks
or localhost); those exact hosts come from the server environment, which an
attacker cannot influence through a request. ``MCP_ALLOWED_URL_DOMAINS`` entries
are domain patterns that request-supplied URLs may also match, so a host under
them may resolve to a private network address but never to loopback, link-local
or cloud-metadata addresses. The single-resolution pin still applies to every
host.
"""

import os
import socket
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.poolmanager import PoolManager

from .urls import _check_ip_address, _get_domain_allowlist, _hostname_matches_allowlist


def _configured_service_hosts() -> list[str]:
    """Exact service hosts the operator configured via environment."""
    hosts = []
    for env in ("JIRA_URL", "CONFLUENCE_URL"):
        raw = os.environ.get(env, "").strip()
        if raw:
            hostname = urlparse(raw).hostname
            if hostname:
                hosts.append(hostname.lower())
    return hosts


def _operator_trusted_hosts() -> list[str]:
    """Hosts the operator explicitly configured or allowlisted via environment."""
    return [*_configured_service_hosts(), *(_get_domain_allowlist() or [])]


def _is_configured_service_host(host: str) -> bool:
    """Return True when ``host`` is exactly a configured service host."""
    return host.lower() in _configured_service_hosts()


def _pinned_create_connection(
    address: tuple[str, int],
    timeout: Any = socket._GLOBAL_DEFAULT_TIMEOUT,  # type: ignore[attr-defined]  # noqa: SLF001
    source_address: tuple[str, int] | None = None,
    socket_options: Any = None,
) -> socket.socket:
    """Resolve once, reject non-global addresses, connect to the validated IP.

    A single ``getaddrinfo`` result is both validated and connected to, so a
    rebinding name cannot return a public IP to the check and a private IP to the
    connection.
    """
    host, port = address
    host_trusted = _is_configured_service_host(host)
    host_allowlisted = _hostname_matches_allowlist(host, _get_domain_allowlist() or [])
    err: Exception | None = None
    for af, socktype, proto, _canonname, sa in socket.getaddrinfo(
        host, port, 0, socket.SOCK_STREAM
    ):
        ip = sa[0]
        if (
            not host_trusted
            and _check_ip_address(ip, allow_private=host_allowlisted) is not None
        ):
            msg = f"SSRF blocked: {host} resolves to non-global address {ip}"
            raise OSError(msg)
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            if socket_options:
                for opt in socket_options:
                    sock.setsockopt(*opt)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:  # type: ignore[attr-defined]  # noqa: SLF001
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            return sock
        except OSError as e:
            err = e
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    msg = f"getaddrinfo returned no addresses for {host}"
    raise OSError(msg)


class _PinnedConnMixin:
    """Route socket creation through the validating, single-resolution connector."""

    def _new_conn(self) -> socket.socket:
        try:
            return _pinned_create_connection(
                (self._dns_host, self.port),  # type: ignore[attr-defined]
                self.timeout,  # type: ignore[attr-defined]
                source_address=self.source_address,  # type: ignore[attr-defined]
                socket_options=self.socket_options,  # type: ignore[attr-defined]
            )
        except OSError as e:
            raise NewConnectionError(
                self,  # type: ignore[arg-type]
                f"Failed to establish a new connection: {e}",
            ) from e


class _PinnedHTTPConnection(_PinnedConnMixin, HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedConnMixin, HTTPSConnection):
    pass


class _PinnedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


_CREDENTIAL_HEADERS = ("Authorization", "Cookie", "Proxy-Authorization")


class SsrfPinningAdapter(HTTPAdapter):
    """A requests adapter that validates and pins DNS resolution for every call."""

    def __init__(
        self, *args: Any, trusted_urls: Iterable[str] = (), **kwargs: Any
    ) -> None:
        self._trusted_hosts: set[str] = set()
        self._trust_urls(trusted_urls)
        self._credential_hosts: set[str] = set()
        self._credential_headers: set[str] = set()
        super().__init__(*args, **kwargs)

    def _trust_urls(self, urls: Iterable[str]) -> None:
        for url in urls:
            hostname = urlparse(url).hostname
            if hostname:
                self._trusted_hosts.add(hostname.lower())

    def send(
        self,
        request: Any,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> Any:
        """Keep caller-controlled destinations on the pinned direct path.

        An HTTP proxy resolves the target itself, outside this process, so merely
        installing pinned connection pools on ``ProxyManager`` would only pin the
        proxy host. Operator-configured service and allowlisted hosts may use a
        deployment proxy; other destinations connect directly through this
        adapter's validating pool.
        """
        hostname = (urlparse(request.url or "").hostname or "").lower()
        if self._credential_hosts and not _hostname_matches_allowlist(
            hostname, [*self._credential_hosts, *(_get_domain_allowlist() or [])]
        ):
            # Off-host request (absolute attachment link, redirect hop): send it
            # without the service credentials or the operator's custom headers.
            for name in (*_CREDENTIAL_HEADERS, *self._credential_headers):
                request.headers.pop(name, None)
            cert = None
        if proxies and not _hostname_matches_allowlist(
            hostname, [*_operator_trusted_hosts(), *self._trusted_hosts]
        ):
            proxies = {}
        return super().send(
            request,
            stream=stream,
            timeout=timeout,
            verify=verify,
            cert=cert,
            proxies=proxies,
        )

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any
    ) -> None:
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs
        )
        # Runtime attribute of urllib3's PoolManager; absent from the type stubs.
        self.poolmanager.pool_classes_by_scheme = {  # type: ignore[attr-defined]
            "http": _PinnedHTTPConnectionPool,
            "https": _PinnedHTTPSConnectionPool,
        }


def mount_ssrf_pinning(session: Session, *trusted_urls: str) -> None:
    """Mount the SSRF DNS-pinning adapter for http/https on ``session``.

    Preserves the retry policy of any adapter already mounted (e.g. the one the
    Atlassian client configures), so pinning does not silently drop retries.

    Args:
        session: Requests session to protect.
        trusted_urls: Operator-controlled transport URLs that may use proxies.
    """
    for scheme in ("https://", "http://"):
        existing = session.adapters.get(scheme)
        retries = getattr(existing, "max_retries", None)
        adapter = (
            SsrfPinningAdapter(max_retries=retries)
            if retries is not None
            else SsrfPinningAdapter()
        )
        session.mount(scheme, adapter)

    for adapter in session.adapters.values():
        if isinstance(adapter, SsrfPinningAdapter):
            adapter._trust_urls(trusted_urls)


def bind_credentials_to_host(
    session: Session, service_url: str, header_names: Iterable[str] = ()
) -> None:
    """Send ``session`` credentials only to the service host.

    Requests to any other host (an absolute attachment URL, or a redirect hop
    such as a CDN) go out without ``Authorization``, ``Cookie``, the client
    certificate or the named custom headers. ``requests`` itself drops only
    ``Authorization`` on a cross-host redirect, and nothing on an initial
    request to another host. Hosts under ``MCP_ALLOWED_URL_DOMAINS`` count as
    the service host, so an operator can allow a known alternate base URL.

    Args:
        session: Session whose SSRF pinning adapters carry the credentials.
        service_url: The URL the credentials belong to.
        header_names: Custom or passthrough header names to treat as secrets.
    """
    hostname = urlparse(service_url).hostname if isinstance(service_url, str) else None
    if not hostname:
        return
    for adapter in session.adapters.values():
        if isinstance(adapter, SsrfPinningAdapter):
            adapter._credential_hosts.add(hostname.lower())
            adapter._credential_headers.update(header_names)
