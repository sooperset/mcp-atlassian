"""Shared HTTP layer hardening: retry, Retry-After respect, optional
concurrency cap and outbound rate limit.

Patches max_retries on every adapter currently mounted on a Session so that
both the default HTTPAdapter and any service-specific adapters (e.g.
SSLIgnoreAdapter mounted by configure_ssl_verification) get the same retry
behavior. Call AFTER configure_ssl_verification.

Reads (GET/HEAD/OPTIONS) are retried a small, bounded number of times by
default; the concurrency cap, rate limiter, and circuit breaker are disabled by
default and gated behind env vars. The send wrappers patch
adapter.send in place (rather than replacing the adapter), so they compose with
whatever adapter is mounted.
"""

import functools
import hashlib
import hmac
import logging
import secrets
import socket
import threading
import time
import zlib
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from requests import Session
from requests.adapters import BaseAdapter, HTTPAdapter
from requests.exceptions import RequestException
from urllib3 import response as _urllib3_response
from urllib3.exceptions import HTTPError as Urllib3HTTPError
from urllib3.exceptions import InvalidHeader
from urllib3.response import GzipDecoder, MultiDecoder
from urllib3.util.retry import Retry

from .env import (
    get_float_env,
    get_int_env,
    is_env_extended_truthy,
    is_env_truthy,
)
from .urls import upstream_key

logger = logging.getLogger("mcp-atlassian.http")

T = TypeVar("T")
S = TypeVar("S")

DEFAULT_RETRY_TOTAL = 3
DEFAULT_RETRY_BACKOFF = 1.0
DEFAULT_RETRY_MAX_RETRY_AFTER = 60
DEFAULT_RETRY_STATUSES = (429, 502, 503, 504)
_READ_METHODS = frozenset(["GET", "HEAD", "OPTIONS"])
_ALL_METHODS = frozenset(["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
_THROTTLED_ATTR = "_mcp_atlassian_throttled"
_RATE_LIMITED_ATTR = "_mcp_atlassian_rate_limited"
_CIRCUIT_BREAKER_ATTR = "_mcp_atlassian_circuit_breaker"
_DEFAULT_TIMEOUT_ATTR = "_mcp_atlassian_default_timeout"
_BUDGET_TRACKED_ATTR = "_mcp_atlassian_budget_tracked"
_RESPONSE_SOCK_ATTR = "_mcp_atlassian_response_sock"
_CONNECT_CHECKED_ATTR = "_mcp_atlassian_connect_checked"
_UNLIMITED_ATTR = "_mcp_atlassian_unlimited_body"

MAX_RESPONSE_BYTES_ENV = "ATLASSIAN_MAX_RESPONSE_BYTES"
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
_READ_CHUNK = 64 * 1024
_DECODE_STEP = 16 * 1024
_DEFLATE_PROBE_BYTES = 64 * 1024


class _BoundedRetry(Retry):
    """urllib3 Retry whose ``Retry-After`` waits are bounded on both sides.

    * Cap: a server ``Retry-After`` longer than ``max_retry_after`` seconds is
      cut down to it (urllib3's own ceiling is six hours).
    * Floor: when the header is present the wait is never shorter than the
      exponential backoff, nor than ``backoff_factor``, so ``Retry-After: 0``
      cannot cause zero-delay retries (the #1543 storm).
    * An unparseable header falls back to plain backoff instead of raising.
    """

    def __init__(
        self,
        *args: Any,
        max_retry_after: float = DEFAULT_RETRY_MAX_RETRY_AFTER,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.max_retry_after = max_retry_after

    def new(self, **kw: Any) -> "_BoundedRetry":
        # Retry.new() rebuilds via type(self)(**params) with only the stock
        # parameters; carry the cap over to each incremented copy.
        new_retry = super().new(**kw)
        new_retry.max_retry_after = self.max_retry_after
        return new_retry

    def get_retry_after(self, response: Any) -> float | None:
        try:
            return super().get_retry_after(response)
        except InvalidHeader:
            logger.debug("Ignoring invalid Retry-After header; using backoff")
            return None

    def sleep_for_retry(self, response: Any = None) -> bool:
        retry_after = self.get_retry_after(response)
        if retry_after is None:
            return False
        floor = max(self.backoff_factor, self.get_backoff_time())
        delay = max(min(retry_after, self.max_retry_after), floor)
        if delay > 0:
            _sleep(delay)
        return True

    def _sleep_backoff(self) -> None:
        backoff = self.get_backoff_time()
        if backoff > 0:
            _sleep(backoff)


class CircuitBreakerOpenError(Exception):
    """Raised by the circuit breaker when in the open state."""


class UpstreamCallAborted(Exception):  # noqa: N818 - public name reads as an event
    """Raised in a worker thread whose call was cancelled or ran out of time."""


# How often a fetcher call blocked on a lock or a lookup checks whether it was
# stopped.
_STOP_POLL_SECONDS = 0.05


class CallBudget:
    """Wall-clock budget of one offloaded fetcher call.

    The async side runs the call through :meth:`run` in a worker thread and
    calls :meth:`abort` when the caller is cancelled or the deadline passes.
    Abort refuses every later request and retry wait of that call, and shuts
    down the sockets it is reading, so the thread returns within one connect
    timeout instead of whenever the upstream finishes.
    """

    def __init__(self, deadline: float | None = None) -> None:
        #: ``time.monotonic()`` value the call must finish by, if any.
        self.deadline = deadline
        self._aborted = threading.Event()
        self._lock = threading.Lock()
        self._conns: set[Any] = set()

    @property
    def aborted(self) -> bool:
        return self._aborted.is_set()

    def run(self, func: Callable[[], T]) -> T:
        """Run ``func`` in the current thread under this budget."""
        previous = getattr(_call_budget, "current", None)
        _call_budget.current = self
        try:
            return func()
        finally:
            _call_budget.current = previous
            with self._lock:
                self._conns.clear()

    def abort(self) -> None:
        """Stop the call: later requests fail and open sockets are shut down."""
        # Everything happens under the lock: a connection goes back to a pool
        # shared with other calls only after :meth:`untrack`, which takes the
        # same lock, so every socket shut down here still belongs to this call.
        # A connection returned with its socket shut down is detected as
        # dropped and reopened by the next call that takes it from the pool.
        with self._lock:
            # Set under the lock so a connection that finishes opening either
            # sees the abort in :meth:`connected` or is in ``conns`` with its
            # socket already in place.
            self._aborted.set()
            for conn in self._conns:
                # A response that closes the connection takes its socket along
                # and leaves ``conn.sock`` empty, so fall back to the one it was
                # given.
                sock = getattr(conn, "sock", None) or getattr(
                    conn, _RESPONSE_SOCK_ATTR, None
                )
                if not isinstance(sock, socket.socket):
                    # urllib3's SSLTransport (HTTPS through an HTTPS proxy)
                    # keeps the real socket in ``.socket``.
                    sock = getattr(sock, "socket", None)
                if isinstance(sock, socket.socket):
                    try:
                        # The base method: SSLSocket.shutdown also drops its TLS
                        # object, which the reading thread is still using.
                        socket.socket.shutdown(sock, socket.SHUT_RDWR)
                    except OSError:
                        pass

    def check(self) -> None:
        if self._aborted.is_set():
            raise UpstreamCallAborted(
                "Upstream call stopped: it was cancelled or ran past its deadline."
            )

    def remaining(self) -> float | None:
        """Seconds left until the deadline, or None when there is none.

        Raises:
            UpstreamCallAborted: The call was stopped.
            TimeoutError: The deadline has passed.
        """
        self.check()
        if self.deadline is None:
            return None
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("Upstream call ran past its deadline.")
        return left

    def sleep(self, seconds: float) -> None:
        self._aborted.wait(seconds)
        self.check()

    def acquire(self, sem: threading.Semaphore) -> None:
        """Take ``sem``, giving up with :class:`UpstreamCallAborted` on abort."""
        while not sem.acquire(timeout=_STOP_POLL_SECONDS):
            self.check()

    def track(self, conn: object) -> None:
        with self._lock:
            self._conns.add(conn)

    def connected(self, conn: Any) -> None:
        """Drop ``conn`` if the call was stopped while it was opening.

        An abort that lands during the DNS lookup or connect finds no socket to
        shut down, so the new connection is closed here before any request is
        written to it.
        """
        with self._lock:
            if not self._aborted.is_set():
                return
        conn.close()
        self.check()

    def untrack(self, conn: object) -> None:
        with self._lock:
            self._conns.discard(conn)


_call_budget = threading.local()


def current_call_budget() -> CallBudget | None:
    """Return the budget of the fetcher call running in this thread, if any."""
    budget = getattr(_call_budget, "current", None)
    return budget if isinstance(budget, CallBudget) else None


def _sleep(seconds: float) -> None:
    budget = current_call_budget()
    if budget is None:
        time.sleep(seconds)
    else:
        budget.sleep(seconds)


class _TokenBucket:
    """Simple thread-safe token bucket. Rate is steady-state tokens/second;
    capacity equals one second of tokens (small burst tolerance)."""

    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.capacity = max(1.0, rate)
        self.tokens = self.capacity
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        if self.rate <= 0:
            return
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last
                self.last = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.rate
            _sleep(wait)


class _CircuitBreaker:
    """Trip after N consecutive 429/503 responses; fail fast during cooldown.

    closed -> (failures >= threshold) -> open -> (cooldown elapsed) ->
    half-open (single probe allowed) -> closed | open. We don't model
    half-open as a separate state explicitly; cooldown elapsed lets one
    request through which either resets failures (success) or re-opens
    immediately (failure).
    """

    def __init__(self, threshold: int, cooldown: float) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at: float | None = None
        self.probe_in_flight = False
        self.lock = threading.Lock()

    def before_send(self) -> bool:
        with self.lock:
            if self.opened_at is None:
                return False

            elapsed = time.monotonic() - self.opened_at
            if elapsed >= self.cooldown:
                if self.probe_in_flight:
                    raise CircuitBreakerOpenError(
                        "Atlassian circuit breaker half-open probe already in "
                        "flight. Wait for the probe request to complete before "
                        "retrying."
                    )
                self.probe_in_flight = True
                return True

            remaining = self.cooldown - elapsed
            raise CircuitBreakerOpenError(
                f"Atlassian circuit breaker open after {self.threshold} consecutive "
                f"429/503 responses. Cooling down for ~{remaining:.1f}s before "
                "allowing another request. The upstream server appears overloaded; "
                "back off and retry later."
            )

    def on_response(self, status_code: int | None, *, probe: bool) -> None:
        with self.lock:
            if probe:
                self.probe_in_flight = False
                if status_code in (429, 503):
                    self.failures = max(self.failures, self.threshold)
                    self.opened_at = time.monotonic()
                    logger.warning(
                        "Circuit breaker probe failed with %d; cooling down %.1fs",
                        status_code,
                        self.cooldown,
                    )
                else:
                    self.failures = 0
                    self.opened_at = None
                return

            if status_code is None or self.opened_at is not None:
                return

            if status_code in (429, 503):
                self.failures += 1
                if self.failures >= self.threshold and self.opened_at is None:
                    self.opened_at = time.monotonic()
                    logger.warning(
                        "Circuit breaker tripped after %d 429/503 responses; "
                        "cooling down %.1fs",
                        self.failures,
                        self.cooldown,
                    )
            else:
                self.failures = 0

    def on_exception(self, *, probe: bool) -> None:
        if not probe:
            return
        with self.lock:
            self.probe_in_flight = False
            self.failures = max(self.failures, self.threshold)
            self.opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker probe failed before response; cooling down %.1fs",
                self.cooldown,
            )


@dataclass
class _SiteEntry(Generic[S]):
    value: S
    in_use: int = 0


class _SiteRegistry(Generic[S]):
    """Per-upstream-site state, created on first use and bounded in number.

    Least recently used first. Entries with requests in flight are never
    evicted, so the size stays at ``MAX_SITE_ENTRIES`` plus at most the number
    of concurrent requests.
    """

    def __init__(self) -> None:
        self._entries: OrderedDict[str, _SiteEntry[S]] = OrderedDict()
        self._lock = threading.Lock()

    @contextmanager
    def use(self, key: str, factory: Callable[[], S]) -> Iterator[S]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _SiteEntry(factory())
                self._entries[key] = entry
            else:
                self._entries.move_to_end(key)
            entry.in_use += 1
            self._evict_idle()
        try:
            yield entry.value
        finally:
            with self._lock:
                entry.in_use -= 1
                self._evict_idle()

    def get(self, key: str) -> S | None:
        with self._lock:
            entry = self._entries.get(key)
            return entry.value if entry is not None else None

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _evict_idle(self) -> None:
        excess = len(self._entries) - MAX_SITE_ENTRIES
        if excess <= 0:
            return
        for old_key in list(self._entries):
            if excess <= 0:
                break
            if self._entries[old_key].in_use == 0:
                del self._entries[old_key]
                excess -= 1


# Each upstream site (see utils.urls.upstream_key) gets its own concurrency
# cap, rate bucket and circuit breakers, so a slow or failing site, which a
# request header may name, uses only its own budget.
MAX_SITE_ENTRIES = 1024
_concurrency_semaphores: _SiteRegistry[threading.BoundedSemaphore] = _SiteRegistry()
_rate_limit_buckets: _SiteRegistry[_TokenBucket] = _SiteRegistry()
_circuit_breakers: _SiteRegistry[_CircuitBreaker] = _SiteRegistry()
_CREDENTIAL_KEY = secrets.token_bytes(32)


def configure_retry(session: Session, *, service: str = "atlassian") -> None:
    """Apply a bounded urllib3 Retry policy to all adapters on the session.

    Enabled by default with 3 retries for idempotent reads (GET/HEAD/OPTIONS).
    This replaces atlassian-python-api's unbounded ``retry_with_header`` loop,
    which callers must disable (see #1543), so this is the only retry layer.

    Env knobs:
      ATLASSIAN_RETRY_TOTAL          (int,   default 3; <=0 disables retries)
      ATLASSIAN_RETRY_BACKOFF        (float, default 1.0 seconds — exponential factor)
      ATLASSIAN_RETRY_INCLUDE_WRITES (bool,  default false; if true also retries
                                     POST/PUT/PATCH/DELETE — only safe when the
                                     server is known to be idempotent for them)
      ATLASSIAN_RETRY_IGNORE_RETRY_AFTER (bool, default false; ignore the server's
                                     Retry-After header and always use exponential
                                     backoff)
      ATLASSIAN_RETRY_MAX_RETRY_AFTER (int, default 60 seconds; longer Retry-After
                                     values are capped to this)

    Retries fire on 429, 502, 503, 504 and on connection errors; other statuses
    (including 401/403) are returned immediately. The Retry-After header is
    honored up to ATLASSIAN_RETRY_MAX_RETRY_AFTER, and never waits less than the
    exponential backoff, so ``Retry-After: 0`` cannot cause a tight loop.

    Retries happen inside ``adapter.send``, so the circuit breaker and rate
    limiter (which wrap ``send``) see one call per logical request.
    """
    total = get_int_env("ATLASSIAN_RETRY_TOTAL", DEFAULT_RETRY_TOTAL)
    if total <= 0:
        logger.debug("%s: retry disabled (ATLASSIAN_RETRY_TOTAL=%d)", service, total)
        return

    backoff = get_float_env("ATLASSIAN_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF)
    include_writes = is_env_extended_truthy("ATLASSIAN_RETRY_INCLUDE_WRITES")
    methods = _ALL_METHODS if include_writes else _READ_METHODS

    max_retry_after = max(
        0,
        get_int_env("ATLASSIAN_RETRY_MAX_RETRY_AFTER", DEFAULT_RETRY_MAX_RETRY_AFTER),
    )

    retry = _BoundedRetry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=list(DEFAULT_RETRY_STATUSES),
        allowed_methods=methods,
        respect_retry_after_header=not is_env_truthy(
            "ATLASSIAN_RETRY_IGNORE_RETRY_AFTER"
        ),
        raise_on_status=False,
        max_retry_after=max_retry_after,
    )

    if not session.adapters:
        return

    for adapter in session.adapters.values():
        # session.adapters always contains HTTPAdapter instances; the abstract
        # BaseAdapter doesn't expose max_retries so we narrow the type here.
        if isinstance(adapter, HTTPAdapter):
            adapter.max_retries = retry

    logger.debug(
        "%s: retry configured total=%d backoff=%.2fs statuses=%s writes=%s "
        "max_retry_after=%ds",
        service,
        total,
        backoff,
        DEFAULT_RETRY_STATUSES,
        include_writes,
        max_retry_after,
    )


def _reset_concurrency_semaphore_for_tests() -> None:
    _concurrency_semaphores.clear()


def _request_upstream(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    request = args[0] if args else kwargs.get("request")
    url = getattr(request, "url", None)
    return upstream_key(url) if isinstance(url, str) else ""


def _request_principal(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    """Return the upstream site plus a keyed fingerprint of the credential."""
    site = _request_upstream(args, kwargs)
    request = args[0] if args else kwargs.get("request")
    headers = getattr(request, "headers", None)
    credential = headers.get("Authorization") if headers is not None else None
    if not isinstance(credential, str) or not credential:
        return site
    digest = hmac.new(_CREDENTIAL_KEY, credential.encode(), hashlib.sha256)
    return f"{site}#{digest.hexdigest()[:32]}"


def _wrap_adapter_send(adapter: BaseAdapter, cap: int) -> None:
    if getattr(adapter, _THROTTLED_ATTR, False):
        return
    original_send = adapter.send

    def throttled_send(*args: object, **kwargs: object) -> object:
        key = _request_upstream(args, kwargs)
        with _concurrency_semaphores.use(
            key, lambda: threading.BoundedSemaphore(cap)
        ) as sem:
            budget = current_call_budget()
            if budget is None:
                sem.acquire()
            else:
                budget.acquire(sem)
            try:
                return original_send(*args, **kwargs)
            finally:
                sem.release()

    adapter.send = throttled_send  # type: ignore[method-assign]
    setattr(adapter, _THROTTLED_ATTR, True)


def configure_concurrency(session: Session, *, service: str = "atlassian") -> None:
    """Cap concurrent outbound requests to each upstream site.

    Disabled by default. Set ATLASSIAN_MAX_CONCURRENT_REQUESTS to a positive
    integer to enable. The cap is per upstream site and shared by every
    session in the process (Jira + Confluence) that talks to that site, so it
    protects each Atlassian instance, and a slow site cannot hold the permits
    of another.

    Recommended starting value for self-hosted: 2-4.
    """
    cap = get_int_env("ATLASSIAN_MAX_CONCURRENT_REQUESTS", 0)
    if cap <= 0:
        logger.debug("%s: concurrency cap disabled", service)
        return

    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_send(adapter, cap)
    logger.info(
        "%s: concurrency cap=%d applied to %d adapter(s)",
        service,
        cap,
        len(session.adapters),
    )


def _reset_rate_limit_bucket_for_tests() -> None:
    _rate_limit_buckets.clear()


def _wrap_adapter_rate_limit(adapter: BaseAdapter, rate: float) -> None:
    if getattr(adapter, _RATE_LIMITED_ATTR, False):
        return
    original_send = adapter.send

    def rate_limited_send(*args: object, **kwargs: object) -> object:
        key = _request_upstream(args, kwargs)
        with _rate_limit_buckets.use(key, lambda: _TokenBucket(rate)) as bucket:
            bucket.acquire()
        return original_send(*args, **kwargs)

    adapter.send = rate_limited_send  # type: ignore[method-assign]
    setattr(adapter, _RATE_LIMITED_ATTR, True)


def configure_rate_limit(session: Session, *, service: str = "atlassian") -> None:
    """Cap outbound request rate (tokens/second) to each upstream site.

    Disabled by default. Set ATLASSIAN_REQUESTS_PER_SECOND to a positive
    float to enable. Each upstream site has one bucket, shared by every
    session in the process that talks to it, so the cap protects that
    Atlassian instance, not each client independently, and spending one
    site's tokens does not delay another site.

    Recommended starting value for self-hosted: 2-5 rps.
    """
    rate = get_float_env("ATLASSIAN_REQUESTS_PER_SECOND", 0.0)
    if rate <= 0:
        logger.debug("%s: rate limit disabled", service)
        return

    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_rate_limit(adapter, rate)
    logger.info("%s: rate limit %.2f rps applied", service, rate)


def _reset_circuit_breaker_for_tests() -> None:
    _circuit_breakers.clear()


def _wrap_adapter_circuit_breaker(
    adapter: BaseAdapter, threshold: int, cooldown: float
) -> None:
    if getattr(adapter, _CIRCUIT_BREAKER_ATTR, False):
        return
    original_send = adapter.send

    def breaker_send(*args: object, **kwargs: object) -> object:
        with _circuit_breakers.use(
            _request_principal(args, kwargs),
            lambda: _CircuitBreaker(threshold, cooldown),
        ) as breaker:
            probe = breaker.before_send()
            try:
                response = original_send(*args, **kwargs)
            except Exception:
                breaker.on_exception(probe=probe)
                raise
            status = getattr(response, "status_code", None)
            breaker.on_response(
                status if isinstance(status, int) else None, probe=probe
            )
            return response

    adapter.send = breaker_send  # type: ignore[method-assign]
    setattr(adapter, _CIRCUIT_BREAKER_ATTR, True)


def configure_circuit_breaker(session: Session, *, service: str = "atlassian") -> None:
    """Trip a circuit breaker after N consecutive 429/503 responses.

    Disabled by default. Breaker state is kept per upstream site and
    credential, so one site's 429/503 responses do not block requests to
    other sites, and one user's rate limit on a site does not block the other
    users of that site. When tripped, in-flight Sessions raise
    CircuitBreakerOpenError immediately instead of waiting on the per-request
    timeout (default 75s) for each additional doomed request.

    Env knobs:
      ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD (int,   default 0 = disabled)
      ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN  (float, default 30.0 seconds)

    Recommended starting value for self-hosted: threshold=5, cooldown=30s.
    """
    threshold = get_int_env("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", 0)
    if threshold <= 0:
        logger.debug("%s: circuit breaker disabled", service)
        return
    cooldown = get_float_env("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", 30.0)
    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_circuit_breaker(adapter, threshold, cooldown)
    logger.info(
        "%s: circuit breaker armed threshold=%d cooldown=%.1fs",
        service,
        threshold,
        cooldown,
    )


# Threads for DNS lookups made inside a fetcher call.
DNS_LOOKUP_WORKERS = 8
_dns_slots = threading.BoundedSemaphore(DNS_LOOKUP_WORKERS)


def resolve_address(
    host: str, port: int, timeout: object = None, *, bounded: bool = True
) -> list[tuple[Any, ...]]:
    """``getaddrinfo`` for a stream socket that a stopped call does not wait out.

    A lookup cannot be interrupted, so inside a fetcher call it runs on one of
    ``DNS_LOOKUP_WORKERS`` threads of its own, which keeps its place until the
    lookup returns. The call stops waiting when its budget is aborted or after
    ``timeout`` seconds (the connect timeout), whichever comes first. Outside a
    fetcher call, or with ``bounded=False`` (calls without a deadline, which
    serve operator-configured, allowlisted and Cloud sites and must not wait
    behind request-supplied hosts), this is a plain ``getaddrinfo`` in the
    calling thread.

    Raises:
        UpstreamCallAborted: The call was cancelled or ran past its deadline.
        TimeoutError: The lookup took longer than ``timeout``.
    """
    budget = current_call_budget()
    if budget is None or not bounded:
        return socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout if isinstance(timeout, int | float) else None

    def wait_or_stop(ready: Callable[[float], bool]) -> None:
        while not ready(_STOP_POLL_SECONDS):
            budget.check()
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"DNS lookup of {host} timed out")

    wait_or_stop(lambda t: _dns_slots.acquire(timeout=t))
    done = threading.Event()
    outcome: list[Any] = []

    def lookup() -> None:
        try:
            outcome.append(socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM))
        except BaseException as exc:  # noqa: BLE001 - re-raised by the caller
            outcome.append(exc)
        finally:
            _dns_slots.release()
            done.set()

    threading.Thread(target=lookup, name="dns-lookup", daemon=True).start()
    wait_or_stop(done.wait)
    if isinstance(outcome[0], BaseException):
        raise outcome[0]
    return outcome[0]  # type: ignore[no-any-return]


def _check_budget_after_connect(conn: Any) -> None:
    """Make ``conn`` close itself when its call was stopped while it opened."""
    if getattr(conn, _CONNECT_CHECKED_ATTR, False):
        return
    connect = conn.connect

    def connect_then_check(*args: Any, **kwargs: Any) -> Any:
        result = connect(*args, **kwargs)
        budget = current_call_budget()
        if budget is not None:
            budget.connected(conn)
        return result

    conn.connect = connect_then_check
    setattr(conn, _CONNECT_CHECKED_ATTR, True)


def _remember_response_socket(conn: Any) -> None:
    """Keep the socket ``conn`` hands to each response reachable for abort.

    ``http.client`` moves the socket to the response and clears ``conn.sock``
    when the response closes the connection (``Connection: close``, HTTP/1.0),
    while the body is still being read from it.
    """
    if getattr(conn, _RESPONSE_SOCK_ATTR, False) is not False:
        return
    getresponse = conn.getresponse

    def getresponse_keeping_socket(*args: Any, **kwargs: Any) -> Any:
        setattr(conn, _RESPONSE_SOCK_ATTR, conn.sock)
        return getresponse(*args, **kwargs)

    setattr(conn, _RESPONSE_SOCK_ATTR, None)
    conn.getresponse = getresponse_keeping_socket


class ResponseTooLargeError(Urllib3HTTPError, RequestException):
    """A response body passed ``ATLASSIAN_MAX_RESPONSE_BYTES`` after decoding.

    It is a urllib3 error so that urllib3, draining the body of a response it
    retries or redirects, stops reading and moves on; and a requests error so
    that callers handle it like any other failed request.
    """


def max_response_bytes() -> int:
    """Return the decoded body limit for one response; ``0`` turns it off."""
    return max(get_int_env(MAX_RESPONSE_BYTES_ENV, DEFAULT_MAX_RESPONSE_BYTES), 0)


class _DecodingStep(Protocol):
    """The part of urllib3's ``ContentDecoder`` interface used here."""

    def decompress(self, data: bytes, max_length: int = -1) -> bytes: ...

    @property
    def has_unconsumed_tail(self) -> bool: ...

    def flush(self) -> bytes: ...


class _DeflateStep:
    """Decode ``deflate`` the way urllib3 does: zlib-wrapped, else raw.

    urllib3 keeps every input byte until the first decoded byte, in case the
    zlib attempt fails and the raw retry needs them; a stream of empty blocks
    never decodes a byte, so all of it stays. This keeps at most
    ``_DEFLATE_PROBE_BYTES`` for the retry, then commits to the zlib format.
    """

    def __init__(self) -> None:
        self._obj = zlib.decompressobj()
        self._probe: bytearray | None = bytearray()

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        data = self._obj.unconsumed_tail + data
        if self._probe is None:
            return self._obj.decompress(data, max(max_length, 0))
        self._probe += data
        try:
            out = self._obj.decompress(data, max(max_length, 0))
        except zlib.error:
            probe, self._probe = bytes(self._probe), None
            self._obj = zlib.decompressobj(-zlib.MAX_WBITS)
            return self._obj.decompress(probe, max(max_length, 0))
        if out or len(self._probe) > _DEFLATE_PROBE_BYTES:
            self._probe = None
        return out

    @property
    def has_unconsumed_tail(self) -> bool:
        return bool(self._obj.unconsumed_tail)

    def flush(self) -> bytes:
        return self._obj.flush()


@functools.cache
def _brotli_output_is_bounded() -> bool:
    """Whether the installed Brotli honours an output limit (Brotli >= 1.2).

    Without it urllib3 falls back to decoding a whole input at once.
    """
    obj = getattr(_urllib3_response, "brotli").Decompressor()  # noqa: B009
    decompress = getattr(obj, "decompress", None) or obj.process
    try:
        decompress(b"", output_buffer_limit=1)
    except TypeError:
        return False
    except Exception:  # noqa: BLE001 - the argument was accepted
        return True
    return True


def _decoding_step(mode: str) -> _DecodingStep | None:
    """One decoding step, chosen as ``urllib3.response._get_decoder`` does.

    Returns ``None`` for a coding that cannot be decoded within a limit.
    """
    if mode in ("gzip", "x-gzip"):
        return GzipDecoder()  # type: ignore[return-value]
    if mode == "br" and getattr(_urllib3_response, "brotli", None) is not None:
        if not _brotli_output_is_bounded():
            return None
        return getattr(_urllib3_response, "BrotliDecoder")()  # type: ignore[no-any-return]  # noqa: B009
    if mode == "zstd" and getattr(_urllib3_response, "HAS_ZSTD", False):
        return getattr(_urllib3_response, "ZstdDecoder")()  # type: ignore[no-any-return]  # noqa: B009
    return _DeflateStep()


class _DecodeStoppedError(Exception):
    """Carries the error that stopped a :class:`_LimitedDecoder` out of urllib3.

    urllib3 turns ``OSError`` raised by a decoder (``TimeoutError`` and
    :class:`ResponseTooLargeError` are both ``OSError``) into ``DecodeError``,
    so the real error travels inside this one and the reader unwraps it.
    """

    def __init__(self, error: BaseException) -> None:
        super().__init__(str(error))
        self.error = error


def _too_large_message(limit: int) -> str:
    return (
        f"Response body passed the {limit} byte limit "
        f"(set {MAX_RESPONSE_BYTES_ENV} to change it)"
    )


class _LimitedDecoder:
    """Decode a ``Content-Encoding`` chain holding little memory at each step.

    It replaces urllib3's decoder for one response. Each step is pulled for
    at most ``_DECODE_STEP`` bytes at a time, so no step is handed more input
    than it can use (urllib3's chain pushes every step's output into the next
    and lets it pile up). Unless the response is a streamed download, it
    decodes at most one byte past ``limit`` in total.

    It stops by raising :class:`_DecodeStoppedError` out of urllib3's read at
    once, so urllib3 reads no more of the body: when the output passes the
    limit, and when the call budget of the thread it was made in is aborted
    or past its deadline. That budget is checked on every call and between
    step pulls, so a few bytes that expand to gigabytes of inner data and
    decode to nothing take no longer than the call is allowed to.
    """

    def __init__(self, response: Any, steps: list[_DecodingStep], limit: int) -> None:
        self._response = response
        self._steps = steps  # in decoding order: the wire bytes go to [0]
        self._wire = b""
        self._limit = limit
        self._decoded = 0
        self._budget = current_call_budget()
        self._stopped: _DecodeStoppedError | None = None

    def _room(self) -> int | None:
        if getattr(self._response, _UNLIMITED_ATTR, False):
            return None
        return self._limit + 1 - self._decoded

    def _check_budget(self) -> None:
        if self._budget is not None:
            # Raises once the call is aborted or past its deadline.
            self._budget.remaining()

    def _take(self, index: int) -> bytes:
        if index == 0:
            chunk = self._wire[:_DECODE_STEP]
            self._wire = self._wire[_DECODE_STEP:]
            return chunk
        return self._pull(index - 1, _DECODE_STEP)

    def _pull(self, index: int, want: int | None) -> bytes:
        step = self._steps[index]
        parts: list[bytes] = []
        got = 0
        while want is None or got < want:
            size = _DECODE_STEP if want is None else want - got
            tail = step.has_unconsumed_tail
            feed = b"" if tail else self._take(index)
            if not tail and not feed:
                break
            part = step.decompress(feed, max_length=size)
            if not part and tail:
                feed = self._take(index)
                if not feed:
                    break
                part = step.decompress(feed, max_length=size)
            if part:
                parts.append(part)
                got += len(part)
            self._check_budget()
        return b"".join(parts)

    def _stop(self, error: BaseException) -> None:
        self._stopped = _DecodeStoppedError(error)
        self._wire = b""
        raise self._stopped

    def _counted(self, out: bytes) -> bytes:
        self._decoded += len(out)
        room = self._room()
        if room is not None and room <= 0:
            self._stop(ResponseTooLargeError(_too_large_message(self._limit)))
        return out

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        if self._stopped is not None:
            raise self._stopped
        self._wire += data
        room = self._room()
        want = max_length if max_length > 0 else None
        if room is not None:
            want = room if want is None else min(want, room)
        try:
            self._check_budget()
            out = self._pull(len(self._steps) - 1, want)
        except (UpstreamCallAborted, TimeoutError) as exc:
            self._stop(exc)
        return self._counted(out)

    @property
    def has_unconsumed_tail(self) -> bool:
        if self._stopped is not None:
            return False
        return bool(self._wire) or any(s.has_unconsumed_tail for s in self._steps)

    def flush(self) -> bytes:
        if self._stopped is not None:
            raise self._stopped
        last = self._steps[-1]
        if last.has_unconsumed_tail:
            return b""
        return self._counted(last.flush())


def _without_unbounded_codings(headers: Any) -> Any:
    """Drop ``br`` from ``Accept-Encoding`` when Brotli cannot limit its output.

    urllib3 offers ``br`` whenever Brotli imports, but a br body is refused
    when the installed Brotli is older than 1.2.0, so a server that honours
    the request would get every response refused. Not offering it keeps those
    responses in a coding that can be decoded within the limit.
    """
    if not headers or getattr(_urllib3_response, "brotli", None) is None:
        return headers
    if _brotli_output_is_bounded():
        return headers
    found = None
    for name in headers:
        if name.lower() == "accept-encoding":
            found = name
            break
    if found is None:
        return headers
    codings = [
        coding
        for coding in str(headers[found]).split(",")
        if coding.split(";")[0].strip().lower() != "br"
    ]
    copy = dict(headers)
    copy[found] = ",".join(codings).strip() or "identity"
    return copy


def _install_limited_decoder(response: Any, limit: int) -> str | None:
    """Give ``response`` a :class:`_LimitedDecoder` where urllib3 would decode.

    Returns why the body cannot be decoded within the limit, or ``None``.
    """
    known = getattr(response, "CONTENT_DECODERS", ())
    encoding = response.headers.get("content-encoding", "").lower()
    if encoding in known:
        modes = [encoding]
    elif "," in encoding and any(e.strip() in known for e in encoding.split(",")):
        modes = [e.strip() for e in encoding.split(",")]
        if len(modes) > getattr(MultiDecoder, "max_decode_links", 5):
            return None  # urllib3 refuses the chain on the first read
    else:
        return None
    found = [_decoding_step(mode) for mode in reversed(modes)]
    steps = [step for step in found if step is not None]
    if len(steps) != len(found):
        return (
            f"Response content-encoding {encoding!r} cannot be decoded within "
            "the size limit (Brotli >= 1.2.0 is needed for br)"
        )
    response._decoder = _LimitedDecoder(response, steps, limit)  # type: ignore[arg-type]
    return None


def _limit_body(response: Any, limit: int) -> None:
    """Make every read of ``response`` stop once its body passes ``limit``.

    This wraps the urllib3 response itself, below urllib3's retry and
    redirect handling and below requests, so each reader is bounded: requests
    building ``.content``, requests reading a redirect body, and urllib3
    draining the body of a response it retries. The count is of decoded
    bytes. Reads go in bounded chunks and the decoder holds little at each
    step (see :class:`_LimitedDecoder`), so a small compressed body cannot
    expand past the limit in memory. A refused response is closed and its
    connection handed back to the pool, which opens a new one next time.
    A streamed download is exempted after the adapter returns it (see
    ``_wrap_adapter_default_timeout``); its caller applies its own limit.
    """
    read = response.read
    read_chunked = response.read_chunked
    read1 = response.read1
    refusal = _install_limited_decoder(response, limit)
    seen = 0

    def release() -> None:
        response.close()
        response.release_conn()

    def refuse(message: str) -> None:
        release()
        raise ResponseTooLargeError(message)

    @contextmanager
    def unwrap_stop() -> Iterator[None]:
        """Close and hand back a response whose decoder stopped, and raise
        the error that stopped it."""
        try:
            yield
        except _DecodeStoppedError as stop:
            release()
            raise stop.error from None

    def count(data: bytes) -> bytes:
        nonlocal seen
        if getattr(response, _UNLIMITED_ATTR, False):
            return data
        seen += len(data)
        if seen > limit:
            refuse(_too_large_message(limit))
        return data

    def limited_read(
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,  # noqa: FBT001, FBT002 - urllib3 signature
    ) -> bytes:
        with unwrap_stop():
            if getattr(response, _UNLIMITED_ATTR, False):
                return read(amt, decode_content, cache_content)  # type: ignore[no-any-return]
            if refusal is not None:
                refuse(refusal)
            if amt is not None and amt >= 0:
                return count(read(min(amt, limit + 1 - seen), decode_content))
            parts = []
            while chunk := read(_READ_CHUNK, decode_content):
                parts.append(count(chunk))
            data = b"".join(parts)
            if cache_content:
                response._body = data
            return data

    def limited_read_chunked(
        amt: int | None = None, decode_content: bool | None = None
    ) -> Iterator[bytes]:
        with unwrap_stop():
            if getattr(response, _UNLIMITED_ATTR, False):
                yield from read_chunked(amt, decode_content)
                return
            if refusal is not None:
                refuse(refusal)
            for chunk in read_chunked(amt or _READ_CHUNK, decode_content):
                yield count(chunk)

    def limited_read1(
        amt: int | None = None, decode_content: bool | None = None
    ) -> bytes:
        with unwrap_stop():
            if refusal is not None and not getattr(response, _UNLIMITED_ATTR, False):
                refuse(refusal)
            return count(read1(amt, decode_content))

    response.read = limited_read
    response.read_chunked = limited_read_chunked
    response.read1 = limited_read1


def _track_pool_connections(pool: Any) -> Any:
    """Record which call budget holds each connection checked out of ``pool``.

    urllib3 takes a connection for every attempt, retries included, so this is
    also where an aborted call stops before its next attempt.
    """
    if getattr(pool, _BUDGET_TRACKED_ATTR, False):
        return pool
    get_conn = pool._get_conn
    put_conn = pool._put_conn
    make_request = pool._make_request

    def tracked_get_conn(*args: Any, **kwargs: Any) -> Any:
        budget = current_call_budget()
        if budget is not None:
            budget.check()
        conn = get_conn(*args, **kwargs)
        if budget is not None:
            _remember_response_socket(conn)
            _check_budget_after_connect(conn)
            budget.track(conn)
        return conn

    def tracked_put_conn(conn: Any) -> Any:
        budget = current_call_budget()
        if budget is not None:
            budget.untrack(conn)
        return put_conn(conn)

    def limited_make_request(*args: Any, **kwargs: Any) -> Any:
        limit = max_response_bytes()
        if limit:
            if "headers" in kwargs:
                kwargs["headers"] = _without_unbounded_codings(kwargs["headers"])
            elif len(args) > 4:  # conn, method, url, body, headers
                args = (*args[:4], _without_unbounded_codings(args[4]), *args[5:])
        response = make_request(*args, **kwargs)
        if limit:
            _limit_body(response, limit)
        return response

    pool._get_conn = tracked_get_conn
    pool._put_conn = tracked_put_conn
    pool._make_request = limited_make_request
    setattr(pool, _BUDGET_TRACKED_ATTR, True)
    return pool


def _wrap_adapter_default_timeout(adapter: BaseAdapter, timeout: float) -> None:
    if getattr(adapter, _DEFAULT_TIMEOUT_ATTR, False):
        return
    original_send = adapter.send

    def send_with_default_timeout(*args: Any, **kwargs: Any) -> Any:
        budget = current_call_budget()
        if budget is not None:
            budget.check()
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = timeout
        response = original_send(*args, **kwargs)
        # A streamed final response is a download its caller reads and
        # limits; redirect bodies are read by requests and stay limited.
        if kwargs.get("stream") and not getattr(response, "is_redirect", False):
            raw = getattr(response, "raw", None)
            if raw is not None:
                setattr(raw, _UNLIMITED_ATTR, True)
        return response

    adapter.send = send_with_default_timeout  # type: ignore[method-assign, assignment]
    get_pool = getattr(adapter, "get_connection_with_tls_context", None)
    if callable(get_pool):

        def get_tracked_pool(*args: Any, **kwargs: Any) -> Any:
            return _track_pool_connections(get_pool(*args, **kwargs))

        adapter.get_connection_with_tls_context = get_tracked_pool  # type: ignore[attr-defined]
    setattr(adapter, _DEFAULT_TIMEOUT_ATTR, True)


def configure_default_timeout(
    session: Session, timeout: float, *, service: str = "atlassian"
) -> None:
    """Apply the service timeout to requests sent without an explicit timeout.

    ``requests`` waits forever when no timeout is given. atlassian-python-api
    passes its configured timeout on its own calls, but direct
    ``client._session.get/post/put`` calls (attachments, permissions,
    analytics, ...) bypass it, so a stalled connect or read blocks the caller
    indefinitely — and, from an async tool handler, the whole event loop.
    Explicit per-call timeouts are kept.
    """
    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_default_timeout(adapter, timeout)
    logger.debug("%s: default request timeout=%ss", service, timeout)


def format_rate_limit_error(http_err: object, *, service: str) -> str:
    """Build a 429 error string that includes Retry-After when the server set it.

    Per RFC 9110 the Retry-After header may be either a delta-seconds integer
    or an HTTP-date. We prefer to label the value as seconds when it parses
    cleanly as an int, and otherwise surface the raw header value without
    making a units claim.

    Surfaces the structured backoff hint to the LLM so the agent can pause
    instead of immediately retrying.
    """
    response = getattr(http_err, "response", None)
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        try:
            seconds = int(str(retry_after).strip())
        except (TypeError, ValueError):
            return (
                f"{service} API rate limit hit (429). "
                f"Server requested Retry-After: {retry_after}. "
                "Pause before retrying."
            )
        return (
            f"{service} API rate limit hit (429). "
            f"Server requested Retry-After: {seconds} seconds. "
            "Pause before retrying."
        )
    return (
        f"{service} API rate limit hit (429). "
        "No Retry-After header provided; back off and retry."
    )
