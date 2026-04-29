"""Shared HTTP layer hardening: retry, Retry-After respect, optional
concurrency cap and outbound rate limit.

Patches max_retries on every adapter currently mounted on a Session so that
both the default HTTPAdapter and any service-specific adapters (e.g.
SSLIgnoreAdapter mounted by configure_ssl_verification) get the same retry
behavior. Call AFTER configure_ssl_verification.

The optional concurrency cap and rate limiter wrap adapter.send in place
(rather than replacing the adapter), so they compose with whatever adapter
is mounted. Both are disabled by default and gated behind env vars.
"""

import logging
import os
import threading
import time

from requests import Session
from requests.adapters import BaseAdapter, HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("mcp-atlassian.http")

DEFAULT_RETRY_TOTAL = 5
DEFAULT_RETRY_BACKOFF = 1.0
DEFAULT_RETRY_STATUSES = (429, 502, 503, 504)
_READ_METHODS = frozenset(["GET", "HEAD", "OPTIONS"])
_ALL_METHODS = frozenset(["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
_THROTTLED_ATTR = "_mcp_atlassian_throttled"
_RATE_LIMITED_ATTR = "_mcp_atlassian_rate_limited"
_CIRCUIT_BREAKER_ATTR = "_mcp_atlassian_circuit_breaker"


class CircuitBreakerOpenError(Exception):
    """Raised by the circuit breaker when in the open state."""


_concurrency_semaphore: threading.BoundedSemaphore | None = None
_concurrency_semaphore_cap: int | None = None
_concurrency_init_lock = threading.Lock()


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
            time.sleep(wait)


_rate_limit_bucket: _TokenBucket | None = None
_rate_limit_bucket_rate: float | None = None
_rate_limit_init_lock = threading.Lock()


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
        self.lock = threading.Lock()

    def before_send(self) -> None:
        with self.lock:
            if self.opened_at is None:
                return
            if time.monotonic() - self.opened_at >= self.cooldown:
                self.opened_at = None
                self.failures = 0
                return
            remaining = self.cooldown - (time.monotonic() - self.opened_at)
            raise CircuitBreakerOpenError(
                f"Atlassian circuit breaker open after {self.threshold} consecutive "
                f"429/503 responses. Cooling down for ~{remaining:.1f}s before "
                "allowing another request. The upstream server appears overloaded; "
                "back off and retry later."
            )

    def on_response(self, status_code: int) -> None:
        with self.lock:
            if status_code in (429, 503):
                self.failures += 1
                if self.failures >= self.threshold and self.opened_at is None:
                    self.opened_at = time.monotonic()
                    logger.warning(
                        "Circuit breaker tripped after %d consecutive 429/503; "
                        "cooling down %.1fs",
                        self.failures,
                        self.cooldown,
                    )
            else:
                self.failures = 0


_circuit_breaker: _CircuitBreaker | None = None
_circuit_breaker_init_lock = threading.Lock()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid int for %s=%r; using default %d", name, raw, default)
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def configure_retry(session: Session, *, service: str = "atlassian") -> None:
    """Apply a urllib3 Retry policy to all adapters on the session.

    Env knobs:
      ATLASSIAN_RETRY_TOTAL          (int,   default 5; <=0 disables)
      ATLASSIAN_RETRY_BACKOFF        (float, default 1.0 seconds — exponential factor)
      ATLASSIAN_RETRY_INCLUDE_WRITES (bool,  default false; if true also retries
                                     POST/PUT/PATCH/DELETE — only safe when the
                                     server is known to be idempotent for them)

    Retries fire on 429, 502, 503, 504 and on connection errors. Retry-After
    header is respected when present.
    """
    total = _int_env("ATLASSIAN_RETRY_TOTAL", DEFAULT_RETRY_TOTAL)
    if total <= 0:
        logger.info("%s: retry disabled (ATLASSIAN_RETRY_TOTAL=%d)", service, total)
        return

    backoff = _float_env("ATLASSIAN_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF)
    include_writes = _bool_env("ATLASSIAN_RETRY_INCLUDE_WRITES", default=False)
    methods = _ALL_METHODS if include_writes else _READ_METHODS

    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=list(DEFAULT_RETRY_STATUSES),
        allowed_methods=methods,
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    if not session.adapters:
        return

    for adapter in session.adapters.values():
        # session.adapters always contains HTTPAdapter instances; the abstract
        # BaseAdapter doesn't expose max_retries so we narrow the type here.
        if isinstance(adapter, HTTPAdapter):
            adapter.max_retries = retry

    logger.debug(
        "%s: retry configured total=%d backoff=%.2fs statuses=%s writes=%s",
        service,
        total,
        backoff,
        DEFAULT_RETRY_STATUSES,
        include_writes,
    )


def _get_concurrency_semaphore(cap: int) -> threading.BoundedSemaphore:
    """Process-wide BoundedSemaphore keyed off the first observed cap."""
    global _concurrency_semaphore, _concurrency_semaphore_cap
    if _concurrency_semaphore is not None:
        if _concurrency_semaphore_cap != cap:
            logger.warning(
                "Concurrency cap already initialized at %d; ignoring request for %d",
                _concurrency_semaphore_cap,
                cap,
            )
        return _concurrency_semaphore
    with _concurrency_init_lock:
        if _concurrency_semaphore is None:
            _concurrency_semaphore = threading.BoundedSemaphore(cap)
            _concurrency_semaphore_cap = cap
    return _concurrency_semaphore


def _reset_concurrency_semaphore_for_tests() -> None:
    global _concurrency_semaphore, _concurrency_semaphore_cap
    with _concurrency_init_lock:
        _concurrency_semaphore = None
        _concurrency_semaphore_cap = None


def _wrap_adapter_send(adapter: BaseAdapter, sem: threading.BoundedSemaphore) -> None:
    if getattr(adapter, _THROTTLED_ATTR, False):
        return
    original_send = adapter.send

    def throttled_send(*args: object, **kwargs: object) -> object:
        with sem:
            return original_send(*args, **kwargs)

    adapter.send = throttled_send  # type: ignore[method-assign]
    setattr(adapter, _THROTTLED_ATTR, True)


def configure_concurrency(session: Session, *, service: str = "atlassian") -> None:
    """Cap concurrent outbound requests across the whole process.

    Disabled by default. Set ATLASSIAN_MAX_CONCURRENT_REQUESTS to a positive
    integer to enable. The semaphore is process-wide, so the cap applies to
    ALL sessions combined (Jira + Confluence) — the right scope for protecting
    a single self-hosted Atlassian instance.

    Recommended starting value for self-hosted: 2-4.
    """
    cap = _int_env("ATLASSIAN_MAX_CONCURRENT_REQUESTS", 0)
    if cap <= 0:
        logger.debug("%s: concurrency cap disabled", service)
        return

    sem = _get_concurrency_semaphore(cap)
    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_send(adapter, sem)
    logger.info(
        "%s: concurrency cap=%d applied to %d adapter(s)",
        service,
        cap,
        len(session.adapters),
    )


def _get_rate_limit_bucket(rate: float) -> _TokenBucket:
    """Process-wide token bucket. First-caller wins on rate."""
    global _rate_limit_bucket, _rate_limit_bucket_rate
    if _rate_limit_bucket is not None:
        if _rate_limit_bucket_rate != rate:
            logger.warning(
                "Rate limit already initialized at %.2f rps; ignoring request for %.2f",
                _rate_limit_bucket_rate,
                rate,
            )
        return _rate_limit_bucket
    with _rate_limit_init_lock:
        if _rate_limit_bucket is None:
            _rate_limit_bucket = _TokenBucket(rate)
            _rate_limit_bucket_rate = rate
    return _rate_limit_bucket


def _reset_rate_limit_bucket_for_tests() -> None:
    global _rate_limit_bucket, _rate_limit_bucket_rate
    with _rate_limit_init_lock:
        _rate_limit_bucket = None
        _rate_limit_bucket_rate = None


def _wrap_adapter_rate_limit(adapter: BaseAdapter, bucket: _TokenBucket) -> None:
    if getattr(adapter, _RATE_LIMITED_ATTR, False):
        return
    original_send = adapter.send

    def rate_limited_send(*args: object, **kwargs: object) -> object:
        bucket.acquire()
        return original_send(*args, **kwargs)

    adapter.send = rate_limited_send  # type: ignore[method-assign]
    setattr(adapter, _RATE_LIMITED_ATTR, True)


def configure_rate_limit(session: Session, *, service: str = "atlassian") -> None:
    """Cap outbound request rate (tokens/second) across the whole process.

    Disabled by default. Set ATLASSIAN_REQUESTS_PER_SECOND to a positive
    float to enable. The bucket is shared across all sessions in the process
    so the cap protects the upstream Atlassian instance, not each client
    independently.

    Recommended starting value for self-hosted: 2-5 rps.
    """
    rate = _float_env("ATLASSIAN_REQUESTS_PER_SECOND", 0.0)
    if rate <= 0:
        logger.debug("%s: rate limit disabled", service)
        return

    bucket = _get_rate_limit_bucket(rate)
    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_rate_limit(adapter, bucket)
    logger.info("%s: rate limit %.2f rps applied", service, rate)


def _get_circuit_breaker(threshold: int, cooldown: float) -> _CircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is not None:
        return _circuit_breaker
    with _circuit_breaker_init_lock:
        if _circuit_breaker is None:
            _circuit_breaker = _CircuitBreaker(threshold, cooldown)
    return _circuit_breaker


def _reset_circuit_breaker_for_tests() -> None:
    global _circuit_breaker
    with _circuit_breaker_init_lock:
        _circuit_breaker = None


def _wrap_adapter_circuit_breaker(
    adapter: BaseAdapter, breaker: _CircuitBreaker
) -> None:
    if getattr(adapter, _CIRCUIT_BREAKER_ATTR, False):
        return
    original_send = adapter.send

    def breaker_send(*args: object, **kwargs: object) -> object:
        breaker.before_send()
        response = original_send(*args, **kwargs)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            breaker.on_response(status)
        return response

    adapter.send = breaker_send  # type: ignore[method-assign]
    setattr(adapter, _CIRCUIT_BREAKER_ATTR, True)


def configure_circuit_breaker(session: Session, *, service: str = "atlassian") -> None:
    """Trip a process-wide circuit breaker after N consecutive 429/503 responses.

    Disabled by default. When tripped, in-flight Sessions raise
    CircuitBreakerOpenError immediately instead of waiting on the per-request
    timeout (default 75s) for each additional doomed request.

    Env knobs:
      ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD (int,   default 0 = disabled)
      ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN  (float, default 30.0 seconds)

    Recommended starting value for self-hosted: threshold=5, cooldown=30s.
    """
    threshold = _int_env("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", 0)
    if threshold <= 0:
        logger.debug("%s: circuit breaker disabled", service)
        return
    cooldown = _float_env("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", 30.0)
    breaker = _get_circuit_breaker(threshold, cooldown)
    if not session.adapters:
        return
    for adapter in session.adapters.values():
        _wrap_adapter_circuit_breaker(adapter, breaker)
    logger.info(
        "%s: circuit breaker armed threshold=%d cooldown=%.1fs",
        service,
        threshold,
        cooldown,
    )


def format_rate_limit_error(http_err: object, *, service: str) -> str:
    """Build a 429 error string that includes Retry-After when the server set it.

    Surfaces the structured backoff hint to the LLM so the agent can pause
    instead of immediately retrying.
    """
    response = getattr(http_err, "response", None)
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        return (
            f"{service} API rate limit hit (429). "
            f"Server requested Retry-After: {retry_after} seconds. "
            "Pause before retrying."
        )
    return (
        f"{service} API rate limit hit (429). "
        "No Retry-After header provided; back off and retry."
    )
