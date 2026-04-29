"""Shared HTTP layer hardening: retry + Retry-After respect.

Patches max_retries on every adapter currently mounted on a Session so that
both the default HTTPAdapter and any service-specific adapters (e.g.
SSLIgnoreAdapter mounted by configure_ssl_verification) get the same retry
behavior. Call AFTER configure_ssl_verification.
"""

import logging
import os

from requests import Session
from urllib3.util.retry import Retry

logger = logging.getLogger("mcp-atlassian.http")

DEFAULT_RETRY_TOTAL = 5
DEFAULT_RETRY_BACKOFF = 1.0
DEFAULT_RETRY_STATUSES = (429, 502, 503, 504)
_READ_METHODS = frozenset(["GET", "HEAD", "OPTIONS"])
_ALL_METHODS = frozenset(
    ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
)


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
        logger.warning(
            "Invalid float for %s=%r; using default %s", name, raw, default
        )
        return default


def _bool_env(name: str, default: bool) -> bool:
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
    include_writes = _bool_env("ATLASSIAN_RETRY_INCLUDE_WRITES", False)
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
        adapter.max_retries = retry

    logger.debug(
        "%s: retry configured total=%d backoff=%.2fs statuses=%s writes=%s",
        service,
        total,
        backoff,
        DEFAULT_RETRY_STATUSES,
        include_writes,
    )
