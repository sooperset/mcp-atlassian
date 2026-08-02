"""Tests for per-user rate limiting."""

from __future__ import annotations

import os
from unittest.mock import patch

from mcp_atlassian.utils.rate_limiter import (
    InMemoryBackend,
    RateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestInMemoryBackend:
    def test_allows_under_limit(self) -> None:
        backend = InMemoryBackend()
        for _ in range(10):
            assert backend.is_allowed("user:alice", rpm=10, burst=0)

    def test_blocks_over_limit(self) -> None:
        backend = InMemoryBackend()
        for _ in range(10):
            assert backend.is_allowed("user:alice", rpm=10, burst=0)
        assert not backend.is_allowed("user:alice", rpm=10, burst=0)

    def test_burst_extends_limit(self) -> None:
        backend = InMemoryBackend()
        for _ in range(15):
            assert backend.is_allowed("user:alice", rpm=10, burst=5)
        assert not backend.is_allowed("user:alice", rpm=10, burst=5)

    def test_separate_keys(self) -> None:
        backend = InMemoryBackend()
        for _ in range(10):
            backend.is_allowed("user:alice", rpm=10, burst=0)
        assert not backend.is_allowed("user:alice", rpm=10, burst=0)
        assert backend.is_allowed("user:bob", rpm=10, burst=0)

    def test_get_usage(self) -> None:
        backend = InMemoryBackend()
        assert backend.get_usage("user:alice") == 0
        backend.is_allowed("user:alice", rpm=10, burst=0)
        backend.is_allowed("user:alice", rpm=10, burst=0)
        assert backend.get_usage("user:alice") == 2


class TestRateLimiter:
    def test_check_without_user_mapping(self) -> None:
        rl = RateLimiter(backend=InMemoryBackend(), rpm=5, burst=0)
        allowed, key = rl.check("some-token")
        assert allowed
        assert key.startswith("token:")

    def test_check_with_user_mapping(self) -> None:
        rl = RateLimiter(backend=InMemoryBackend(), rpm=5, burst=0)
        rl.register_token_user("some-token", "admin")
        allowed, key = rl.check("some-token")
        assert allowed
        assert key == "user:admin"

    def test_multiple_tokens_same_user_share_limit(self) -> None:
        rl = RateLimiter(backend=InMemoryBackend(), rpm=5, burst=0)
        rl.register_token_user("token-a", "admin")
        rl.register_token_user("token-b", "admin")
        for _ in range(3):
            rl.check("token-a")
        for _ in range(2):
            rl.check("token-b")
        allowed, _ = rl.check("token-a")
        assert not allowed
        allowed, _ = rl.check("token-b")
        assert not allowed

    def test_rate_limit_blocks_after_exhaustion(self) -> None:
        rl = RateLimiter(backend=InMemoryBackend(), rpm=3, burst=0)
        rl.register_token_user("tok", "writer")
        for _ in range(3):
            allowed, _ = rl.check("tok")
            assert allowed
        allowed, key = rl.check("tok")
        assert not allowed
        assert key == "user:writer"

    def test_get_usage_for_token(self) -> None:
        rl = RateLimiter(backend=InMemoryBackend(), rpm=10, burst=0)
        rl.register_token_user("tok", "admin")
        assert rl.get_usage_for_token("tok") == 0
        rl.check("tok")
        rl.check("tok")
        assert rl.get_usage_for_token("tok") == 2


class TestGetRateLimiter:
    def setup_method(self) -> None:
        reset_rate_limiter()

    def teardown_method(self) -> None:
        reset_rate_limiter()

    def test_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert get_rate_limiter() is None

    def test_enabled_with_defaults(self) -> None:
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False):
            rl = get_rate_limiter()
            assert rl is not None
            assert rl.rpm == 60
            assert rl.burst == 20

    def test_custom_rpm_and_burst(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RATE_LIMIT_ENABLED": "true",
                "RATE_LIMIT_RPM": "30",
                "RATE_LIMIT_BURST": "10",
            },
            clear=False,
        ):
            rl = get_rate_limiter()
            assert rl is not None
            assert rl.rpm == 30
            assert rl.burst == 10

    def test_singleton(self) -> None:
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False):
            rl1 = get_rate_limiter()
            rl2 = get_rate_limiter()
            assert rl1 is rl2
