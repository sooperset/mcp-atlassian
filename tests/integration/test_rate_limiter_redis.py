"""Integration tests for RedisBackend against a real Redis instance.

Requires: redis-server accessible at RATE_LIMIT_REDIS_URL or localhost:6379.
Run with: uv run pytest tests/integration/test_rate_limiter_redis.py --integration
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

redis_lib = pytest.importorskip("redis", reason="redis package not installed")

from mcp_atlassian.utils.rate_limiter import (  # noqa: E402
    RateLimiter,
    RedisBackend,
)

REDIS_URL = os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/15")
TEST_KEY_PREFIX = "mcp_ratelimit:test:"


def _redis_available() -> bool:
    try:
        client = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        client.close()
        return True
    except (OSError, redis_lib.ConnectionError):
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason=f"Redis not reachable at {REDIS_URL}",
)


@pytest.fixture()
def redis_client():
    client = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
    yield client
    for key in client.keys("mcp_ratelimit:*"):
        client.delete(key)
    client.close()


@pytest.fixture()
def backend(redis_client):
    return RedisBackend(client=redis_client)


@pytest.mark.integration
@requires_redis
class TestRedisBackendIntegration:
    """Tests that hit a real Redis instance."""

    def test_basic_allow_and_deny(self, backend: RedisBackend) -> None:
        key = "test:basic"
        rpm, burst = 3, 0
        for _ in range(3):
            assert backend.is_allowed(key, rpm, burst) is True
        assert backend.is_allowed(key, rpm, burst) is False

    def test_burst_allowance(self, backend: RedisBackend) -> None:
        key = "test:burst"
        rpm, burst = 2, 1
        for _ in range(3):
            assert backend.is_allowed(key, rpm, burst) is True
        assert backend.is_allowed(key, rpm, burst) is False

    def test_get_usage_tracks_requests(self, backend: RedisBackend) -> None:
        key = "test:usage"
        assert backend.get_usage(key) == 0
        backend.is_allowed(key, 10, 0)
        backend.is_allowed(key, 10, 0)
        assert backend.get_usage(key) == 2

    def test_keys_have_ttl(self, backend: RedisBackend, redis_client) -> None:
        key = "test:ttl"
        backend.is_allowed(key, 10, 0)
        redis_key = f"mcp_ratelimit:{key}"
        ttl = redis_client.ttl(redis_key)
        assert 0 < ttl <= 61

    def test_different_keys_are_independent(self, backend: RedisBackend) -> None:
        backend.is_allowed("test:a", 1, 0)
        backend.is_allowed("test:a", 1, 0)
        assert backend.is_allowed("test:b", 1, 0) is True

    def test_sorted_set_members_are_unique(
        self, backend: RedisBackend, redis_client
    ) -> None:
        key = "test:unique"
        for _ in range(5):
            backend.is_allowed(key, 10, 0)
        redis_key = f"mcp_ratelimit:{key}"
        members = redis_client.zcard(redis_key)
        assert members == 5


@pytest.mark.integration
@requires_redis
class TestRateLimiterRedisIntegration:
    """End-to-end RateLimiter with real Redis."""

    def test_rate_limiter_with_redis_backend(self, backend: RedisBackend) -> None:
        limiter = RateLimiter(backend=backend, rpm=3, burst=0)
        token = "integration-test-token"
        limiter.register_token_user(token, "testuser")

        for _ in range(3):
            allowed, key = limiter.check(token)
            assert allowed is True
            assert key == "user:testuser"

        allowed, _ = limiter.check(token)
        assert allowed is False

    def test_usage_tracking(self, backend: RedisBackend) -> None:
        limiter = RateLimiter(backend=backend, rpm=10, burst=0)
        token = "usage-token"
        limiter.register_token_user(token, "usageuser")

        assert limiter.get_usage_for_token(token) == 0
        limiter.check(token)
        limiter.check(token)
        assert limiter.get_usage_for_token(token) == 2

    def test_unknown_token_falls_back_to_hash(self, backend: RedisBackend) -> None:
        limiter = RateLimiter(backend=backend, rpm=5, burst=0)
        token = "unknown-token"
        allowed, key = limiter.check(token)
        assert allowed is True
        assert key.startswith("token:")

    def test_concurrent_requests_respect_limit(
        self, backend: RedisBackend
    ) -> None:
        """Race condition repro: concurrent is_allowed calls must not
        exceed the limit. The check-then-act gap in the current
        implementation lets multiple requests slip through."""
        key = "test:concurrent"
        rpm, burst = 5, 0
        num_concurrent = 30

        def try_request(_: int) -> bool:
            return backend.is_allowed(key, rpm, burst)

        with ThreadPoolExecutor(max_workers=num_concurrent) as pool:
            results = list(pool.map(try_request, range(num_concurrent)))

        allowed_count = sum(results)
        assert allowed_count <= rpm + burst, (
            f"Race condition: {allowed_count} requests allowed, "
            f"expected <= {rpm + burst}"
        )
