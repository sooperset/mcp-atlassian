"""Per-user rate limiting with in-memory (default) and optional Redis backends."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import deque
from threading import Lock
from typing import Any, Protocol

from cachetools import TTLCache

logger = logging.getLogger("mcp-atlassian.utils.rate_limiter")


class RateLimiterBackend(Protocol):
    """Backend interface for rate limiting."""

    def is_allowed(self, key: str, rpm: int, burst: int) -> bool:
        """Check if request is allowed under the rate limit.

        Args:
            key: Rate limit key (e.g. "user:admin").
            rpm: Maximum requests per minute.
            burst: Extra burst allowance on top of rpm.

        Returns:
            True if allowed, False if rate-limited.
        """
        ...

    def get_usage(self, key: str) -> int:
        """Return current request count in the window for a key."""
        ...


class InMemoryBackend:
    """Sliding-window rate limiter using in-memory deques."""

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = Lock()

    def is_allowed(self, key: str, rpm: int, burst: int) -> bool:
        now = time.monotonic()
        limit = rpm + burst
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                window = deque()
                self._windows[key] = window
            # Prune entries older than 60 seconds
            cutoff = now - 60.0
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    def get_usage(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                return 0
            cutoff = now - 60.0
            while window and window[0] < cutoff:
                window.popleft()
            return len(window)


class RedisBackend:
    """Sliding-window rate limiter using Redis sorted sets."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._redis = client
        elif redis_url:
            try:
                import redis as redis_lib  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ImportError(
                    "redis package is required for Redis rate limiting. "
                    "Install with: uv add redis"
                ) from exc
            self._redis = redis_lib.Redis.from_url(
                redis_url,
                decode_responses=True,
            )
        else:
            msg = "Either redis_url or client must be provided"
            raise ValueError(msg)

    def _prune_and_count(self, redis_key: str) -> int:
        now = time.time()
        cutoff = now - 60.0
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zcard(redis_key)
        results = pipe.execute()
        return int(results[1])

    def is_allowed(self, key: str, rpm: int, burst: int) -> bool:
        limit = rpm + burst
        redis_key = f"mcp_ratelimit:{key}"
        try:
            count = self._prune_and_count(redis_key)
            if count >= limit:
                return False
            now = time.time()
            member = f"{now}-{id(self)}"
            pipe = self._redis.pipeline()
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, 61)
            pipe.execute()
            return True
        except (OSError, ConnectionError, TimeoutError):
            logger.warning(
                "Redis rate limit check failed, allowing request",
                exc_info=True,
            )
            return True

    def get_usage(self, key: str) -> int:
        redis_key = f"mcp_ratelimit:{key}"
        try:
            return self._prune_and_count(redis_key)
        except (OSError, ConnectionError, TimeoutError):
            logger.warning(
                "Redis rate limit count failed",
                exc_info=True,
            )
            return 0


class RateLimiter:
    """Per-user rate limiter with token-to-user mapping cache."""

    def __init__(
        self,
        backend: RateLimiterBackend,
        rpm: int = 60,
        burst: int = 20,
    ) -> None:
        self.backend = backend
        self.rpm = rpm
        self.burst = burst
        # token_hash -> username, TTL 5 minutes
        self._token_user_cache: TTLCache[str, str, int] = TTLCache(
            maxsize=1000, ttl=300
        )

    @staticmethod
    def token_hash(token: str) -> str:
        """Hash a token for use as a cache key."""
        return hashlib.sha256(token.encode()).hexdigest()[:16]

    def register_token_user(self, token: str, username: str) -> None:
        """Associate a token with a username for rate limiting."""
        self._token_user_cache[self.token_hash(token)] = username

    def get_user_for_token(self, token: str) -> str | None:
        """Look up the username for a token."""
        return self._token_user_cache.get(self.token_hash(token))

    def check(self, token: str) -> tuple[bool, str]:
        """Check rate limit for a request.

        Args:
            token: The Bearer token from the request.

        Returns:
            Tuple of (allowed, rate_limit_key).
            rate_limit_key is "user:<username>" if known, else "token:<hash>".
        """
        t_hash = self.token_hash(token)
        username = self._token_user_cache.get(t_hash)
        if username:
            key = f"user:{username}"
        else:
            key = f"token:{t_hash}"
        allowed = self.backend.is_allowed(key, self.rpm, self.burst)
        return allowed, key

    def get_usage_for_token(self, token: str) -> int:
        """Get current usage count for the user behind a token."""
        t_hash = self.token_hash(token)
        username = self._token_user_cache.get(t_hash)
        key = f"user:{username}" if username else f"token:{t_hash}"
        return self.backend.get_usage(key)


# Module-level singleton, initialized lazily
_rate_limiter: RateLimiter | None = None
_init_lock = Lock()


def _create_rate_limiter() -> RateLimiter | None:
    """Create a rate limiter from environment config.

    Environment variables:
        RATE_LIMIT_ENABLED: Enable rate limiting (default: false).
        RATE_LIMIT_RPM: Requests per minute per user (default: 60).
        RATE_LIMIT_BURST: Burst allowance on top of RPM (default: 20).
        RATE_LIMIT_REDIS_URL: Redis URL for distributed rate limiting.
            If not set, uses in-memory backend.
    """
    enabled = os.getenv("RATE_LIMIT_ENABLED", "").lower() in (
        "true",
        "1",
        "yes",
    )
    if not enabled:
        return None

    rpm = int(os.getenv("RATE_LIMIT_RPM", "60"))
    burst = int(os.getenv("RATE_LIMIT_BURST", "20"))
    redis_url = os.getenv("RATE_LIMIT_REDIS_URL", "")

    if redis_url:
        logger.info(
            "Rate limiting enabled (Redis backend, %d rpm, %d burst)",
            rpm,
            burst,
        )
        backend: RateLimiterBackend = RedisBackend(redis_url)
    else:
        logger.info(
            "Rate limiting enabled (in-memory backend, %d rpm, %d burst)",
            rpm,
            burst,
        )
        backend = InMemoryBackend()

    return RateLimiter(backend=backend, rpm=rpm, burst=burst)


_initialized = False


def get_rate_limiter() -> RateLimiter | None:
    """Get or create the global rate limiter. Returns None if disabled."""
    global _rate_limiter, _initialized
    if _initialized:
        return _rate_limiter

    with _init_lock:
        if not _initialized:
            _rate_limiter = _create_rate_limiter()
            _initialized = True
        return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (for testing)."""
    global _rate_limiter, _initialized
    _rate_limiter = None
    _initialized = False
