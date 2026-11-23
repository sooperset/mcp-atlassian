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
from urllib.parse import unquote, urlparse, urlsplit

from requests import PreparedRequest, Request, Session
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.poolmanager import PoolManager

from .http import current_call_budget, resolve_address
from .urls import _check_ip_address, _get_domain_allowlist, _hostname_matches_allowlist

_DEFAULT_PORTS = {"http": 80, "https": 443}

Origin = tuple[str, str, int]


def url_origin(url: object) -> Origin | None:
    """Return ``(scheme, host, effective port)`` for an http(s) URL, or None.

    The host is lower-cased and a missing port becomes the scheme's default,
    so ``https://Jira.example.com`` and ``https://jira.example.com:443`` are
    the same origin while ``http://jira.example.com`` and
    ``https://jira.example.com:8443`` are not.
    """
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in _DEFAULT_PORTS or not hostname:
        return None
    return scheme, hostname, port if port is not None else _DEFAULT_PORTS[scheme]


def _configured_service_urls() -> list[str]:
    return [
        raw
        for raw in (
            os.environ.get(env, "").strip() for env in ("JIRA_URL", "CONFLUENCE_URL")
        )
        if raw
    ]


def _configured_service_origins() -> set[Origin]:
    """Exact service origins the operator configured via environment."""
    return {
        origin
        for origin in (url_origin(raw) for raw in _configured_service_urls())
        if origin is not None
    }


def is_operator_trusted_url(url: object, extra_origins: Iterable[Origin] = ()) -> bool:
    """Return True when ``url`` is a destination the operator trusts.

    Trusted means the exact origin (scheme, host, port) of ``JIRA_URL``,
    ``CONFLUENCE_URL`` or one of ``extra_origins``, or a host under an
    ``MCP_ALLOWED_URL_DOMAINS`` entry (domain and its subdomains, as
    documented for that variable). Subdomains, other schemes and other ports
    of a configured service host are not trusted through the service URL.
    """
    return is_trusted_for_origins(url, {*_configured_service_origins(), *extra_origins})


def is_trusted_for_origins(url: object, origins: Iterable[Origin]) -> bool:
    """Return True when ``url`` has one of ``origins`` or an allowlisted host.

    Unlike :func:`is_operator_trusted_url`, the configured service URLs are
    not added, so a caller can limit trust to one service's own origin.
    """
    origin = url_origin(url)
    if origin is None:
        return False
    if origin in set(origins):
        return True
    return _hostname_matches_allowlist(origin[1], _get_domain_allowlist() or [])


def _is_configured_service_endpoint(host: str, port: int) -> bool:
    """Return True for exactly the host and port of a configured service URL."""
    host = host.lower()
    return any(
        o_host == host and o_port == port
        for _scheme, o_host, o_port in _configured_service_origins()
    )


def loggable_url(url: str) -> str:
    """Return ``scheme://host:port/path`` of ``url`` for logs and messages.

    User info, query and fragment are left out: they can carry credentials
    or signed tokens.
    """
    origin = url_origin(url)
    if origin is None:
        return "<unparseable URL>"
    return f"{origin[0]}://{origin[1]}:{origin[2]}{urlparse(url.strip()).path}"


def ensure_attachment_origin(url: str, own_urls: Iterable[object]) -> None:
    """Refuse an attachment URL that is not on the service's own origin.

    Allowed: the exact origin (scheme, host, port) of one of ``own_urls`` (the
    fetcher's configured URL and its client's base URL), or a host under
    ``MCP_ALLOWED_URL_DOMAINS``. The operator's JIRA_URL/CONFLUENCE_URL is not
    trusted here, so a fetcher for a request-supplied host cannot be sent to
    the operator's instance.

    Args:
        url: The absolute URL about to be fetched.
        own_urls: URLs of the service the fetcher talks to.

    Raises:
        ValueError: If ``url`` is on another origin. The message names only
            the origin, never the path, query or user info.
    """
    allowed = {url_origin(u) for u in own_urls} - {None}
    origin = url_origin(url)
    if origin is not None and (
        origin in allowed
        or _hostname_matches_allowlist(origin[1], _get_domain_allowlist() or [])
    ):
        return
    shown = f"{origin[0]}://{origin[1]}:{origin[2]}" if origin else "<unparseable URL>"
    msg = f"Refusing to fetch attachment from a different host: {shown}"
    raise ValueError(msg)


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

    Inside a fetcher call, each address is tried only while the call is still
    running, and for no longer than the time left before its deadline.
    """
    host, port = address
    budget = current_call_budget()
    host_trusted = _is_configured_service_endpoint(host, port)
    host_allowlisted = _hostname_matches_allowlist(host, _get_domain_allowlist() or [])
    err: Exception | None = None
    # Only calls with a deadline (made for a request-supplied site) use the
    # bounded lookup threads. Calls without one (operator sites, allowlisted
    # and Cloud hosts) resolve in their own thread, so they never wait behind
    # header hosts.
    use_bounded = budget is not None and budget.deadline is not None
    addresses = resolve_address(host, port, timeout, bounded=use_bounded)
    for af, socktype, proto, _canonname, sa in addresses:
        ip = sa[0]
        if (
            not host_trusted
            and _check_ip_address(ip, allow_private=host_allowlisted) is not None
        ):
            msg = f"SSRF blocked: {host} resolves to non-global address {ip}"
            raise OSError(msg)
        attempt_timeout = timeout
        if budget is not None:
            left = budget.remaining()
            if left is not None and not (
                isinstance(timeout, int | float) and timeout <= left
            ):
                attempt_timeout = left
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            if socket_options:
                for opt in socket_options:
                    sock.setsockopt(*opt)
            if attempt_timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:  # type: ignore[attr-defined]  # noqa: SLF001
                sock.settimeout(attempt_timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            return sock
        except OSError as e:
            err = e
            if sock is not None:
                sock.close()
            if budget is not None:
                budget.check()
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
        self._trusted_origins: set[Origin] = set()
        self._trust_urls(trusted_urls)
        self._credential_origins: set[Origin] = set()
        self._credential_headers: set[str] = set()
        super().__init__(*args, **kwargs)

    def _trust_urls(self, urls: Iterable[str]) -> None:
        for url in urls:
            origin = url_origin(url)
            if origin is not None:
                self._trusted_origins.add(origin)

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
        url = request.url or ""
        if self._credential_origins and not (
            url_origin(url) in self._credential_origins
            or _hostname_matches_allowlist(
                (urlparse(url).hostname or "").lower(), _get_domain_allowlist() or []
            )
        ):
            # Off-host request (absolute attachment link, redirect hop): send it
            # without the service credentials or the operator's custom headers.
            for name in (*_CREDENTIAL_HEADERS, *self._credential_headers):
                request.headers.pop(name, None)
            cert = None
        if proxies and not is_operator_trusted_url(url, self._trusted_origins):
            proxies = {}
        if verify is False and url_origin(url) not in self._credential_origins:
            # *_SSL_VERIFY=false is for this session's own service origin
            # (exact scheme, host and port). Other service URLs, other hosts
            # under MCP_ALLOWED_URL_DOMAINS, redirect hops and absolute links
            # are verified.
            verify = (
                os.environ.get("REQUESTS_CA_BUNDLE")
                or os.environ.get("CURL_CA_BUNDLE")
                or True
            )
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


def _has_dot_segment(url: str) -> bool:
    """Return whether the path of ``url`` contains a ``.`` or ``..`` segment.

    The check sees the path the way a client, proxy or server may come to
    read it: percent-encoding is decoded until the path stops changing (so
    ``%252e`` is read as ``.``), a backslash counts as a separator, and a
    ``;parameter`` suffix on a segment is ignored. Every decoding stage is
    checked. A path still changing after ``_MAX_PATH_DECODES`` decodings is
    treated as having a dot segment. The query string is not checked.

    Args:
        url: The request URL as the caller built it, before normalization.

    Returns:
        ``True`` if any path segment is ``.`` or ``..`` at any decoding stage,
        or if the path does not settle within ``_MAX_PATH_DECODES`` decodings.
    """
    path = urlsplit(url).path
    for _ in range(_MAX_PATH_DECODES):
        if _has_dot_segment_in(path):
            return True
        decoded = unquote(path)
        if decoded == path:
            return False
        path = decoded
    return True


# No Atlassian path is percent-encoded this many times over.
_MAX_PATH_DECODES = 8


def _has_dot_segment_in(path: str) -> bool:
    segments = path.replace("\\", "/").split("/")
    return any(segment.split(";", 1)[0] in (".", "..") for segment in segments)


def _refuse_dot_segments(session: Session) -> None:
    """Make ``session`` refuse a request whose path has a ``.`` or ``..`` segment.

    Request paths are built from tool arguments. ``requests`` resolves dot
    segments while it prepares a request, so a value such as
    ``../../OTHER-1/comment/5`` would address a different resource than the one
    the caller was checked for. No Jira or Confluence endpoint needs such a
    path, so the request is refused before it is prepared. A request sent
    through ``Session.request`` passes here with its path still as written;
    a ``PreparedRequest`` handed straight to ``Session.send`` does not.

    Args:
        session: Requests session to protect.
    """
    prepare = session.prepare_request
    if getattr(prepare, "refuses_dot_segments", False):
        return

    def prepare_request(request: Request) -> PreparedRequest:
        if _has_dot_segment(str(request.url)):
            msg = "Refusing a request whose path contains a '.' or '..' segment"
            raise ValueError(msg)
        return prepare(request)

    prepare_request.refuses_dot_segments = True  # type: ignore[attr-defined]
    session.prepare_request = prepare_request  # type: ignore[method-assign]


def mount_ssrf_pinning(session: Session, *trusted_urls: str) -> None:
    """Mount the SSRF DNS-pinning adapter for http/https on ``session``.

    Preserves the retry policy of any adapter already mounted (e.g. the one the
    Atlassian client configures), so pinning does not silently drop retries.
    The session also refuses request paths with ``.`` or ``..`` segments.

    Args:
        session: Requests session to protect.
        trusted_urls: Operator-controlled transport URLs that may use proxies.
    """
    _refuse_dot_segments(session)
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
    """Send ``session`` credentials only to the service origin.

    The origin is the exact scheme, host and port of ``service_url``. Requests
    to any other origin (an absolute attachment URL, or a redirect hop
    such as a CDN) go out without ``Authorization``, ``Cookie``, the client
    certificate or the named custom headers. ``requests`` itself drops only
    ``Authorization`` on a cross-host redirect, and nothing on an initial
    request to another host. Hosts under ``MCP_ALLOWED_URL_DOMAINS`` (a domain
    and its subdomains) count as the service, so an operator can allow a known
    alternate base URL.

    Args:
        session: Session whose SSRF pinning adapters carry the credentials.
        service_url: The URL the credentials belong to.
        header_names: Custom or passthrough header names to treat as secrets.
    """
    origin = url_origin(service_url)
    if origin is None:
        return
    for adapter in session.adapters.values():
        if isinstance(adapter, SsrfPinningAdapter):
            adapter._credential_origins.add(origin)
            adapter._credential_headers.update(header_names)
