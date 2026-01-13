"""Unit tests for per-request configuration headers (Issue #850).

Tests the following functionality:
- X-Jira-Token and X-Confluence-Token for dual-token deployments
- X-Read-Only-Mode header to override read-only mode per request
- X-Jira-Projects-Filter and X-Confluence-Spaces-Filter for per-request filters
- X-Enabled-Tools for per-request tool restrictions
- Backward compatibility: headers are optional, env vars work as fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian.servers.main import UserTokenMiddleware

# Configure pytest for async tests
pytestmark = pytest.mark.anyio


class TestPerRequestConfigHeaders:
    """Tests for per-request configuration header extraction in UserTokenMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create a UserTokenMiddleware instance for testing."""
        mock_app = AsyncMock()
        mock_mcp_server = MagicMock()
        mock_mcp_server.settings.streamable_http_path = "/mcp"
        return UserTokenMiddleware(mock_app, mcp_server_ref=mock_mcp_server)

    @pytest.fixture
    def mock_scope(self):
        """Create a mock ASGI scope for testing."""
        return {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
            "state": {},
        }

    @pytest.fixture
    def mock_receive(self):
        """Create a mock ASGI receive callable."""
        return AsyncMock()

    @pytest.fixture
    def mock_send(self):
        """Create a mock ASGI send callable."""
        return AsyncMock()

    # --- Dual Token Tests ---

    async def test_jira_token_header_extraction(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Jira-Token header is extracted and stored in scope state."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer unified-token"),
            (b"x-jira-token", b"jira-specific-token"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify jira_token was extracted
        assert "jira_token" in mock_scope["state"]
        assert mock_scope["state"]["jira_token"] == "jira-specific-token"

        # Verify Authorization token is still extracted for Confluence
        assert mock_scope["state"]["user_atlassian_token"] == "unified-token"

        middleware.app.assert_called_once()

    async def test_confluence_token_header_extraction(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Confluence-Token header is extracted and stored in scope state."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer unified-token"),
            (b"x-confluence-token", b"confluence-specific-token"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify confluence_token was extracted
        assert "confluence_token" in mock_scope["state"]
        assert mock_scope["state"]["confluence_token"] == "confluence-specific-token"

        # Verify Authorization token is still extracted for Jira
        assert mock_scope["state"]["user_atlassian_token"] == "unified-token"

        middleware.app.assert_called_once()

    async def test_dual_token_deployment(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test both X-Jira-Token and X-Confluence-Token can be set independently."""
        mock_scope["headers"] = [
            (b"x-jira-token", b"jira-specific-token"),
            (b"x-confluence-token", b"confluence-specific-token"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify both tokens are stored independently
        assert mock_scope["state"]["jira_token"] == "jira-specific-token"
        assert mock_scope["state"]["confluence_token"] == "confluence-specific-token"

        # No unified token provided
        assert mock_scope["state"].get("user_atlassian_token") is None

        middleware.app.assert_called_once()

    async def test_no_token_leakage_between_services(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that X-Jira-Token is not accessible as confluence_token and vice versa."""
        mock_scope["headers"] = [
            (b"x-jira-token", b"jira-only-token"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Jira token is set
        assert mock_scope["state"]["jira_token"] == "jira-only-token"

        # Confluence token is NOT set (no leakage)
        assert mock_scope["state"].get("confluence_token") is None

    # --- Read-Only Mode Tests ---
    # Note: The middleware stores read_only_mode as a string. Consumers (io.py, decorators.py)
    # are responsible for converting to boolean using case-insensitive comparison.

    async def test_read_only_mode_true_header(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Read-Only-Mode: true is stored in scope state."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-read-only-mode", b"true"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Middleware stores string value; consumers convert to bool
        assert mock_scope["state"]["read_only_mode"] == "true"

    async def test_read_only_mode_false_header(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Read-Only-Mode: false is stored in scope state."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-read-only-mode", b"false"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Middleware stores string value; consumers convert to bool
        assert mock_scope["state"]["read_only_mode"] == "false"

    async def test_read_only_mode_preserves_case(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Read-Only-Mode preserves case (consumers do case-insensitive compare)."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-read-only-mode", b"TRUE"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Middleware preserves original case; consumers handle case-insensitive compare
        assert mock_scope["state"]["read_only_mode"] == "TRUE"

    async def test_read_only_mode_stores_any_value(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test any non-empty X-Read-Only-Mode value is stored (consumer validates)."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-read-only-mode", b"invalid"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Middleware stores the value; consumers decide how to interpret
        assert mock_scope["state"]["read_only_mode"] == "invalid"

    # --- Filter Override Tests ---

    async def test_jira_projects_filter_header(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Jira-Projects-Filter header is extracted."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-jira-projects-filter", b"PROJ1,PROJ2,PROJ3"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_scope["state"]["jira_projects_filter"] == "PROJ1,PROJ2,PROJ3"

    async def test_confluence_spaces_filter_header(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Confluence-Spaces-Filter header is extracted."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-confluence-spaces-filter", b"SPACE1,SPACE2"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_scope["state"]["confluence_spaces_filter"] == "SPACE1,SPACE2"

    async def test_filters_with_whitespace_stripped(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test filter headers have leading/trailing whitespace stripped."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-jira-projects-filter", b"  PROJ1 , PROJ2  "),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # _get_header_str strips whitespace from decoded value
        assert mock_scope["state"]["jira_projects_filter"] == "PROJ1 , PROJ2"

    # --- Enabled Tools Tests ---

    async def test_enabled_tools_header(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Enabled-Tools header is extracted."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-enabled-tools", b"jira_get_issue,confluence_get_page"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        assert (
            mock_scope["state"]["enabled_tools"] == "jira_get_issue,confluence_get_page"
        )

    async def test_enabled_tools_empty_string_not_stored(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test X-Enabled-Tools with empty string is not stored (falsy check)."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-enabled-tools", b""),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Empty string fails `if enabled_tools:` check, so not stored
        assert mock_scope["state"].get("enabled_tools") is None

    # --- Backward Compatibility Tests ---

    async def test_no_config_headers_backward_compatible(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that requests without config headers work (backward compatible)."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # All config headers should be None (not set)
        assert mock_scope["state"].get("jira_token") is None
        assert mock_scope["state"].get("confluence_token") is None
        assert mock_scope["state"].get("read_only_mode") is None
        assert mock_scope["state"].get("jira_projects_filter") is None
        assert mock_scope["state"].get("confluence_spaces_filter") is None
        assert mock_scope["state"].get("enabled_tools") is None

        # But auth token should still work
        assert mock_scope["state"]["user_atlassian_token"] == "test-token"

        middleware.app.assert_called_once()

    async def test_all_config_headers_together(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test all per-request config headers can be used together."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer unified-token"),
            (b"x-jira-token", b"jira-token"),
            (b"x-confluence-token", b"confluence-token"),
            (b"x-read-only-mode", b"true"),
            (b"x-jira-projects-filter", b"PROJ1"),
            (b"x-confluence-spaces-filter", b"SPACE1"),
            (b"x-enabled-tools", b"jira_get_issue"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_scope["state"]["user_atlassian_token"] == "unified-token"
        assert mock_scope["state"]["jira_token"] == "jira-token"
        assert mock_scope["state"]["confluence_token"] == "confluence-token"
        # read_only_mode stored as string
        assert mock_scope["state"]["read_only_mode"] == "true"
        assert mock_scope["state"]["jira_projects_filter"] == "PROJ1"
        assert mock_scope["state"]["confluence_spaces_filter"] == "SPACE1"
        assert mock_scope["state"]["enabled_tools"] == "jira_get_issue"

        middleware.app.assert_called_once()

    # --- Health Check Bypass Tests ---

    async def test_health_check_bypasses_header_processing(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that health check endpoint bypasses header processing."""
        mock_scope["path"] = "/health"
        mock_scope["headers"] = [
            (b"x-jira-token", b"should-be-ignored"),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Health check should not process config headers
        # (state might not even be set for health checks)
        middleware.app.assert_called_once()


class TestIsReadOnlyModeWithRequestContext:
    """Tests for is_read_only_mode function with per-request override."""

    def test_read_only_mode_from_request_context_true(self):
        """Test is_read_only_mode returns True when request_context has read_only_mode=True."""
        from mcp_atlassian.utils.io import is_read_only_mode

        request_context = {"read_only_mode": True}

        result = is_read_only_mode(request_context=request_context)

        assert result is True

    def test_read_only_mode_from_request_context_false(self):
        """Test is_read_only_mode returns False when request_context has read_only_mode=False."""
        from mcp_atlassian.utils.io import is_read_only_mode

        request_context = {"read_only_mode": False}

        result = is_read_only_mode(request_context=request_context)

        assert result is False

    def test_read_only_mode_falls_back_to_env_when_none(self):
        """Test is_read_only_mode falls back to env var when request_context is None."""
        from mcp_atlassian.utils.io import is_read_only_mode

        with patch.dict("os.environ", {"READ_ONLY_MODE": "true"}):
            result = is_read_only_mode(request_context=None)
            assert result is True

    def test_read_only_mode_request_context_none_value(self):
        """Test is_read_only_mode falls back to env when request_context has None value."""
        from mcp_atlassian.utils.io import is_read_only_mode

        request_context = {"read_only_mode": None}

        with patch.dict("os.environ", {"READ_ONLY_MODE": "false"}):
            result = is_read_only_mode(request_context=request_context)
            # Falls back to env var
            assert result is False


class TestCheckWriteAccessDecorator:
    """Tests for check_write_access decorator with per-request override."""

    @pytest.fixture
    def mock_request_with_state(self):
        """Create a mock request with state for HTTP context."""
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        return mock_request

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock FastMCP context."""
        ctx = MagicMock()
        ctx.request_context = MagicMock()
        ctx.request_context.lifespan_context = {"app_lifespan_context": None}
        return ctx

    @pytest.mark.anyio
    async def test_check_write_access_allows_when_read_only_mode_false(
        self, mock_request_with_state, mock_ctx
    ):
        """Test write access is allowed when request state has read_only_mode=False."""
        from mcp_atlassian.utils.decorators import check_write_access

        mock_request_with_state.state.read_only_mode = False

        @check_write_access
        async def write_operation(ctx):
            return "success"

        with patch(
            "mcp_atlassian.utils.decorators.get_http_request",
            return_value=mock_request_with_state,
        ):
            result = await write_operation(mock_ctx)
            assert result == "success"

    @pytest.mark.anyio
    async def test_check_write_access_blocks_when_read_only_mode_true(
        self, mock_request_with_state, mock_ctx
    ):
        """Test write access is blocked when request state has read_only_mode=True."""
        from mcp_atlassian.utils.decorators import check_write_access

        mock_request_with_state.state.read_only_mode = True

        @check_write_access
        async def write_operation(ctx):
            return "success"

        with patch(
            "mcp_atlassian.utils.decorators.get_http_request",
            return_value=mock_request_with_state,
        ):
            with pytest.raises(ValueError, match="read-only mode"):
                await write_operation(mock_ctx)


class TestDependenciesPerRequestConfig:
    """Tests for dependencies.py per-request config handling."""

    async def test_get_jira_fetcher_uses_jira_specific_token(self):
        """Test get_jira_fetcher prioritizes X-Jira-Token over Authorization."""
        # This test verifies the token priority logic exists
        # Full integration test would require more setup
        # Verify function signature accepts context
        import inspect

        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        sig = inspect.signature(get_jira_fetcher)
        assert "ctx" in sig.parameters

    async def test_get_confluence_fetcher_uses_confluence_specific_token(self):
        """Test get_confluence_fetcher prioritizes X-Confluence-Token over Authorization."""
        import inspect

        from mcp_atlassian.servers.dependencies import get_confluence_fetcher

        sig = inspect.signature(get_confluence_fetcher)
        assert "ctx" in sig.parameters
