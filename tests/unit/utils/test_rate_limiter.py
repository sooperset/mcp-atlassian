"""Tests for per-user rate limiting."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from mcp_atlassian.utils.rate_limiter import (
    InMemoryBackend,
    RateLimiter,
    RedisBackend,
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


class TestRedisBackend:
    def _make_backend(self) -> RedisBackend:
        server = fakeredis.FakeServer()
        client = fakeredis.FakeRedis(
            server=server,
            decode_responses=True,
        )
        return RedisBackend(client=client)

    def test_allows_under_limit(self) -> None:
        backend = self._make_backend()
        for _ in range(10):
            assert backend.is_allowed("user:alice", rpm=10, burst=0)

    def test_blocks_over_limit(self) -> None:
        backend = self._make_backend()
        for _ in range(10):
            assert backend.is_allowed("user:alice", rpm=10, burst=0)
        assert not backend.is_allowed("user:alice", rpm=10, burst=0)

    def test_burst_extends_limit(self) -> None:
        backend = self._make_backend()
        for _ in range(15):
            assert backend.is_allowed("user:alice", rpm=10, burst=5)
        assert not backend.is_allowed("user:alice", rpm=10, burst=5)

    def test_separate_keys(self) -> None:
        backend = self._make_backend()
        for _ in range(10):
            backend.is_allowed("user:alice", rpm=10, burst=0)
        assert not backend.is_allowed("user:alice", rpm=10, burst=0)
        assert backend.is_allowed("user:bob", rpm=10, burst=0)

    def test_get_usage(self) -> None:
        backend = self._make_backend()
        assert backend.get_usage("user:alice") == 0
        backend.is_allowed("user:alice", rpm=10, burst=0)
        backend.is_allowed("user:alice", rpm=10, burst=0)
        assert backend.get_usage("user:alice") == 2

    def test_multiple_tokens_same_user(self) -> None:
        backend = self._make_backend()
        rl = RateLimiter(backend=backend, rpm=5, burst=0)
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


class TestRedisBackendFailOpen:
    """Redis connection failures should fail open (allow requests)."""

    def _make_failing_backend(self):
        backend = RedisBackend.__new__(RedisBackend)
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe
        mock_pipe.execute.side_effect = ConnectionError("redis down")
        backend._redis = mock_redis
        return backend

    def test_is_allowed_returns_true_on_connection_error(self) -> None:
        backend = self._make_failing_backend()
        assert backend.is_allowed("user:alice", rpm=10, burst=0) is True

    def test_get_usage_returns_zero_on_connection_error(self) -> None:
        backend = self._make_failing_backend()
        assert backend.get_usage("user:alice") == 0


class TestRegisterRateLimitUser:
    """Tests for _register_rate_limit_user in dependencies.py."""

    def setup_method(self) -> None:
        reset_rate_limiter()

    def teardown_method(self) -> None:
        reset_rate_limiter()

    def test_noop_when_disabled(self) -> None:
        from mcp_atlassian.servers.dependencies import _register_rate_limit_user

        request = MagicMock()
        request.state = SimpleNamespace(user_atlassian_token="tok123")
        with patch.dict(os.environ, {}, clear=True):
            _register_rate_limit_user(request, "admin")
        # No rate limiter → nothing registered, no error

    def test_registers_token_user_when_enabled(self) -> None:
        from mcp_atlassian.servers.dependencies import _register_rate_limit_user

        with patch.dict(
            os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False
        ):
            rl = get_rate_limiter()
            assert rl is not None
            request = MagicMock()
            request.state = SimpleNamespace(user_atlassian_token="my-token")
            _register_rate_limit_user(request, "JIRAUSER10100")
            assert rl.get_user_for_token("my-token") == "JIRAUSER10100"

    def test_skips_when_no_token_on_request(self) -> None:
        from mcp_atlassian.servers.dependencies import _register_rate_limit_user

        with patch.dict(
            os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False
        ):
            rl = get_rate_limiter()
            assert rl is not None
            request = MagicMock()
            request.state = SimpleNamespace()
            _register_rate_limit_user(request, "admin")
            assert rl.get_user_for_token("anything") is None

    def test_skips_when_empty_user_id(self) -> None:
        from mcp_atlassian.servers.dependencies import _register_rate_limit_user

        with patch.dict(
            os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False
        ):
            rl = get_rate_limiter()
            assert rl is not None
            request = MagicMock()
            request.state = SimpleNamespace(user_atlassian_token="tok")
            _register_rate_limit_user(request, "")
            assert rl.get_user_for_token("tok") is None


class TestRateLimitMiddleware:
    """Tests for the ASGI RateLimitMiddleware."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        reset_rate_limiter()
        yield
        reset_rate_limiter()

    @staticmethod
    async def _dummy_app(scope, receive, send):
        body = b'{"ok": true}'
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _make_scope(token=None, scope_type="http"):
        scope = {"type": scope_type, "state": {}}
        if token:
            scope["state"]["user_atlassian_token"] = token
        return scope

    @staticmethod
    async def _collect_response(middleware, scope):
        messages = []

        async def send(msg):
            messages.append(msg)

        async def receive():
            return {"type": "http.request", "body": b""}

        await middleware(scope, receive, send)
        return messages

    @pytest.mark.anyio
    async def test_passthrough_when_disabled(self) -> None:
        from mcp_atlassian.servers.main import RateLimitMiddleware

        with patch.dict(os.environ, {}, clear=True):
            mw = RateLimitMiddleware(self._dummy_app)
            msgs = await self._collect_response(
                mw, self._make_scope(token="tok")
            )
            assert msgs[0]["status"] == 200

    @pytest.mark.anyio
    async def test_passthrough_when_no_token(self) -> None:
        from mcp_atlassian.servers.main import RateLimitMiddleware

        with patch.dict(
            os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False
        ):
            mw = RateLimitMiddleware(self._dummy_app)
            msgs = await self._collect_response(
                mw, self._make_scope(token=None)
            )
            assert msgs[0]["status"] == 200

    @pytest.mark.anyio
    async def test_passthrough_for_non_http_scope(self) -> None:
        from mcp_atlassian.servers.main import RateLimitMiddleware

        with patch.dict(
            os.environ, {"RATE_LIMIT_ENABLED": "true"}, clear=False
        ):
            mw = RateLimitMiddleware(self._dummy_app)
            msgs = await self._collect_response(
                mw, self._make_scope(token="tok", scope_type="websocket")
            )
            assert msgs[0]["status"] == 200

    @pytest.mark.anyio
    async def test_allows_under_limit(self) -> None:
        from mcp_atlassian.servers.main import RateLimitMiddleware

        with patch.dict(
            os.environ,
            {"RATE_LIMIT_ENABLED": "true", "RATE_LIMIT_RPM": "5",
             "RATE_LIMIT_BURST": "0"},
            clear=False,
        ):
            mw = RateLimitMiddleware(self._dummy_app)
            for _ in range(5):
                msgs = await self._collect_response(
                    mw, self._make_scope(token="tok")
                )
                assert msgs[0]["status"] == 200

    @pytest.mark.anyio
    async def test_returns_429_when_exceeded(self) -> None:
        from mcp_atlassian.servers.main import RateLimitMiddleware

        with patch.dict(
            os.environ,
            {"RATE_LIMIT_ENABLED": "true", "RATE_LIMIT_RPM": "2",
             "RATE_LIMIT_BURST": "0"},
            clear=False,
        ):
            mw = RateLimitMiddleware(self._dummy_app)
            for _ in range(2):
                await self._collect_response(
                    mw, self._make_scope(token="tok")
                )
            msgs = await self._collect_response(
                mw, self._make_scope(token="tok")
            )
            assert msgs[0]["status"] == 429
            headers = dict(msgs[0]["headers"])
            assert headers[b"content-type"] == b"application/json"
            assert headers[b"retry-after"] == b"60"
            body = json.loads(msgs[1]["body"])
            assert body["error"] == "rate_limit_exceeded"
            assert body["retry_after_seconds"] == 60
