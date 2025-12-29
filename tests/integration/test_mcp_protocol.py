"""Comprehensive MCP protocol integration tests for AtlassianMCP server."""

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Context
from fastmcp.tools import Tool as FastMCPTool
from mcp.types import Tool as MCPTool
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.main import (
    AtlassianMCP,
    UserTokenMiddleware,
    health_check,
    main_lifespan,
)
from tests.utils.factories import (
    ConfluencePageFactory,
    JiraIssueFactory,
)
from tests.utils.mocks import MockEnvironment, MockFastMCP

logger = logging.getLogger(__name__)


@pytest.mark.integration
@pytest.mark.anyio
class TestMCPProtocolIntegration:
    """Test suite for MCP protocol integration with AtlassianMCP server."""

    @pytest.fixture
    async def mock_jira_config(self):
        """Create a mock Jira configuration."""
        config = MagicMock(spec=JiraConfig)
        config.is_auth_configured.return_value = True
        config.url = "https://test.atlassian.net"
        config.auth_type = "oauth"
        return config

    @pytest.fixture
    async def mock_confluence_config(self):
        """Create a mock Confluence configuration."""
        config = MagicMock(spec=ConfluenceConfig)
        config.is_auth_configured.return_value = True
        config.url = "https://test.atlassian.net/wiki"
        config.auth_type = "oauth"
        return config

    @pytest.fixture
    async def mock_jira_fetcher(self):
        """Create a mock Jira fetcher."""
        fetcher = MagicMock(spec=JiraFetcher)
        fetcher.get_issue.return_value = JiraIssueFactory.create()
        fetcher.search_issues.return_value = {
            "issues": [
                JiraIssueFactory.create("TEST-1"),
                JiraIssueFactory.create("TEST-2"),
            ],
            "total": 2,
        }
        return fetcher

    @pytest.fixture
    async def mock_confluence_fetcher(self):
        """Create a mock Confluence fetcher."""
        fetcher = MagicMock(spec=ConfluenceFetcher)
        fetcher.get_page.return_value = ConfluencePageFactory.create()
        fetcher.search_pages.return_value = {
            "results": [
                ConfluencePageFactory.create("123"),
                ConfluencePageFactory.create("456"),
            ],
            "size": 2,
        }
        return fetcher

    @pytest.fixture
    async def atlassian_mcp_server(self):
        """Create an AtlassianMCP server instance for testing."""
        server = AtlassianMCP(name="Test Atlassian MCP", lifespan=main_lifespan)
        # Mount sub-servers (they're already mounted in the actual server)
        return server

    async def test_tool_discovery_with_full_configuration(
        self, atlassian_mcp_server, mock_jira_config, mock_confluence_config
    ):
        """Test tool discovery when both Jira and Confluence are fully configured."""
        with MockEnvironment.basic_auth_env():
            # Mock the configuration loading
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env",
                    return_value=mock_jira_config,
                ),
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env",
                    return_value=mock_confluence_config,
                ),
            ):
                # Create app context
                app_context = MainAppContext(
                    full_jira_config=mock_jira_config,
                    full_confluence_config=mock_confluence_config,
                    read_only=False,
                    enabled_tools=None,
                )

                # Mock request context
                request_context = MagicMock()
                request_context.lifespan_context = {"app_lifespan_context": app_context}

                # Set up server context
                atlassian_mcp_server._mcp_server = MagicMock()
                atlassian_mcp_server._mcp_server.request_context = request_context

                # Mock get_tools to return sample tools
                async def mock_get_tools():
                    tools = {}
                    # Add sample Jira tools
                    for tool_name in [
                        "jira_get_issue",
                        "jira_create_issue",
                        "jira_search_issues",
                    ]:
                        tool = MagicMock(spec=FastMCPTool)
                        tool.tags = (
                            {"jira", "read"}
                            if "get" in tool_name or "search" in tool_name
                            else {"jira", "write"}
                        )
                        tool.to_mcp_tool.return_value = MCPTool(
                            name=tool_name,
                            description=f"Tool {tool_name}",
                            inputSchema={"type": "object", "properties": {}},
                        )
                        tools[tool_name] = tool

                    # Add sample Confluence tools
                    for tool_name in ["confluence_get_page", "confluence_create_page"]:
                        tool = MagicMock(spec=FastMCPTool)
                        tool.tags = (
                            {"confluence", "read"}
                            if "get" in tool_name
                            else {"confluence", "write"}
                        )
                        tool.to_mcp_tool.return_value = MCPTool(
                            name=tool_name,
                            description=f"Tool {tool_name}",
                            inputSchema={"type": "object", "properties": {}},
                        )
                        tools[tool_name] = tool

                    return tools

                atlassian_mcp_server.get_tools = mock_get_tools

                # Get filtered tools
                tools = await atlassian_mcp_server._list_tools_mcp()

                # Assert all tools are available
                tool_names = [tool.name for tool in tools]
                assert "jira_get_issue" in tool_names
                assert "jira_create_issue" in tool_names
                assert "jira_search_issues" in tool_names
                assert "confluence_get_page" in tool_names
                assert "confluence_create_page" in tool_names
                assert len(tools) == 5

    async def test_tool_filtering_read_only_mode(
        self, atlassian_mcp_server, mock_jira_config, mock_confluence_config
    ):
        """Test tool filtering when read-only mode is enabled."""
        with MockEnvironment.basic_auth_env():
            # Create app context with read-only mode
            app_context = MainAppContext(
                full_jira_config=mock_jira_config,
                full_confluence_config=mock_confluence_config,
                read_only=True,  # Enable read-only mode
                enabled_tools=None,
            )

            # Mock request context
            request_context = MagicMock()
            request_context.lifespan_context = {"app_lifespan_context": app_context}

            # Set up server context
            atlassian_mcp_server._mcp_server = MagicMock()
            atlassian_mcp_server._mcp_server.request_context = request_context

            # Mock get_tools
            async def mock_get_tools():
                tools = {}
                # Add mix of read and write tools
                read_tools = [
                    "jira_get_issue",
                    "jira_search_issues",
                    "confluence_get_page",
                ]
                write_tools = [
                    "jira_create_issue",
                    "jira_update_issue",
                    "confluence_create_page",
                ]

                for tool_name in read_tools:
                    tool = MagicMock(spec=FastMCPTool)
                    tool.tags = (
                        {"jira", "read"}
                        if "jira" in tool_name
                        else {"confluence", "read"}
                    )
                    tool.to_mcp_tool.return_value = MCPTool(
                        name=tool_name,
                        description=f"Tool {tool_name}",
                        inputSchema={"type": "object", "properties": {}},
                    )
                    tools[tool_name] = tool

                for tool_name in write_tools:
                    tool = MagicMock(spec=FastMCPTool)
                    tool.tags = (
                        {"jira", "write"}
                        if "jira" in tool_name
                        else {"confluence", "write"}
                    )
                    tool.to_mcp_tool.return_value = MCPTool(
                        name=tool_name,
                        description=f"Tool {tool_name}",
                        inputSchema={"type": "object", "properties": {}},
                    )
                    tools[tool_name] = tool

                return tools

            atlassian_mcp_server.get_tools = mock_get_tools

            # Get filtered tools
            tools = await atlassian_mcp_server._list_tools_mcp()

            # Assert only read tools are available
            tool_names = [tool.name for tool in tools]
            assert "jira_get_issue" in tool_names
            assert "jira_search_issues" in tool_names
            assert "confluence_get_page" in tool_names
            assert "jira_create_issue" not in tool_names
            assert "jira_update_issue" not in tool_names
            assert "confluence_create_page" not in tool_names
            assert len(tools) == 3

    async def test_tool_filtering_with_enabled_tools(
        self, atlassian_mcp_server, mock_jira_config, mock_confluence_config
    ):
        """Test tool filtering with specific enabled tools list."""
        with MockEnvironment.basic_auth_env():
            # Create app context with specific enabled tools
            enabled_tools = ["jira_get_issue", "jira_search_issues"]
            app_context = MainAppContext(
                full_jira_config=mock_jira_config,
                full_confluence_config=mock_confluence_config,
                read_only=False,
                enabled_tools=enabled_tools,
            )

            # Mock request context
            request_context = MagicMock()
            request_context.lifespan_context = {"app_lifespan_context": app_context}

            # Set up server context
            atlassian_mcp_server._mcp_server = MagicMock()
            atlassian_mcp_server._mcp_server.request_context = request_context

            # Mock get_tools
            async def mock_get_tools():
                tools = {}
                all_tools = [
                    "jira_get_issue",
                    "jira_create_issue",
                    "jira_search_issues",
                    "confluence_get_page",
                    "confluence_create_page",
                ]

                for tool_name in all_tools:
                    tool = MagicMock(spec=FastMCPTool)
                    if "jira" in tool_name:
                        tool.tags = (
                            {"jira", "read"}
                            if "get" in tool_name or "search" in tool_name
                            else {"jira", "write"}
                        )
                    else:
                        tool.tags = (
                            {"confluence", "read"}
                            if "get" in tool_name
                            else {"confluence", "write"}
                        )
                    tool.to_mcp_tool.return_value = MCPTool(
                        name=tool_name,
                        description=f"Tool {tool_name}",
                        inputSchema={"type": "object", "properties": {}},
                    )
                    tools[tool_name] = tool

                return tools

            atlassian_mcp_server.get_tools = mock_get_tools

            # Get filtered tools
            tools = await atlassian_mcp_server._list_tools_mcp()

            # Assert only enabled tools are available
            tool_names = [tool.name for tool in tools]
            assert "jira_get_issue" in tool_names
            assert "jira_search_issues" in tool_names
            assert "jira_create_issue" not in tool_names
            assert "confluence_get_page" not in tool_names
            assert "confluence_create_page" not in tool_names
            assert len(tools) == 2

    async def test_tool_filtering_service_not_configured(self, atlassian_mcp_server):
        """Test tool filtering when services are not configured."""
        with MockEnvironment.clean_env():
            # Create app context with no configurations
            app_context = MainAppContext(
                full_jira_config=None,  # Jira not configured
                full_confluence_config=None,  # Confluence not configured
                read_only=False,
                enabled_tools=None,
            )

            # Mock request context
            request_context = MagicMock()
            request_context.lifespan_context = {"app_lifespan_context": app_context}

            # Set up server context
            atlassian_mcp_server._mcp_server = MagicMock()
            atlassian_mcp_server._mcp_server.request_context = request_context

            # Mock get_tools
            async def mock_get_tools():
                tools = {}
                all_tools = [
                    "jira_get_issue",
                    "jira_create_issue",
                    "confluence_get_page",
                    "confluence_create_page",
                ]

                for tool_name in all_tools:
                    tool = MagicMock(spec=FastMCPTool)
                    if "jira" in tool_name:
                        tool.tags = (
                            {"jira", "read"}
                            if "get" in tool_name
                            else {"jira", "write"}
                        )
                    else:
                        tool.tags = (
                            {"confluence", "read"}
                            if "get" in tool_name
                            else {"confluence", "write"}
                        )
                    tool.to_mcp_tool.return_value = MCPTool(
                        name=tool_name,
                        description=f"Tool {tool_name}",
                        inputSchema={"type": "object", "properties": {}},
                    )
                    tools[tool_name] = tool

                return tools

            atlassian_mcp_server.get_tools = mock_get_tools

            # Get filtered tools
            tools = await atlassian_mcp_server._list_tools_mcp()

            # Assert no tools are available when services not configured
            assert len(tools) == 0

    async def test_middleware_oauth_token_processing(self):
        """Test UserTokenMiddleware OAuth token extraction and processing."""
        # Create middleware instance
        app = MagicMock()
        mcp_server = MagicMock()
        # Mock the settings attribute with proper structure
        settings_mock = MagicMock()
        settings_mock.streamable_http_path = "/mcp"
        mcp_server.settings = settings_mock
        middleware = UserTokenMiddleware(app, mcp_server_ref=mcp_server)

        # Create mock request with OAuth Bearer token
        request = MockFastMCP.create_request()
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {"Authorization": "Bearer test-oauth-token-12345"}

        # Mock call_next
        async def mock_call_next(req):
            # Verify request state was set
            assert hasattr(req.state, "user_atlassian_token")
            assert req.state.user_atlassian_token == "test-oauth-token-12345"
            assert req.state.user_atlassian_auth_type == "oauth"
            assert req.state.user_atlassian_email is None
            return JSONResponse({"status": "ok"})

        # Process request
        response = await middleware.dispatch(request, mock_call_next)

        # Verify response
        assert response.status_code == 200

    async def test_middleware_pat_token_processing(self):
        """Test UserTokenMiddleware PAT token extraction and processing."""
        # Create middleware instance
        app = MagicMock()
        mcp_server = MagicMock()
        # Mock the settings attribute with proper structure
        settings_mock = MagicMock()
        settings_mock.streamable_http_path = "/mcp"
        mcp_server.settings = settings_mock
        middleware = UserTokenMiddleware(app, mcp_server_ref=mcp_server)

        # Create mock request with PAT token
        request = MockFastMCP.create_request()
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {"Authorization": "Token test-pat-token-67890"}

        # Mock call_next
        async def mock_call_next(req):
            # Verify request state was set
            assert hasattr(req.state, "user_atlassian_token")
            assert req.state.user_atlassian_token == "test-pat-token-67890"
            assert req.state.user_atlassian_auth_type == "pat"
            assert req.state.user_atlassian_email is None
            return JSONResponse({"status": "ok"})

        # Process request
        response = await middleware.dispatch(request, mock_call_next)

        # Verify response
        assert response.status_code == 200

    async def test_middleware_invalid_auth_header(self):
        """Test UserTokenMiddleware with invalid authorization header."""
        # Create middleware instance
        app = MagicMock()
        mcp_server = MagicMock()
        # Mock the settings attribute with proper structure
        settings_mock = MagicMock()
        settings_mock.streamable_http_path = "/mcp"
        mcp_server.settings = settings_mock
        middleware = UserTokenMiddleware(app, mcp_server_ref=mcp_server)

        # Create mock request with invalid auth header
        request = MockFastMCP.create_request()
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {
            "Authorization": "Basic dXNlcjpwYXNz"
        }  # Basic auth not supported

        # Mock call_next (shouldn't be called)
        async def mock_call_next(req):
            pytest.fail("call_next should not be called for invalid auth")

        # Process request
        response = await middleware.dispatch(request, mock_call_next)

        # Verify error response
        assert response.status_code == 401
        body = json.loads(response.body)
        assert "error" in body
        assert (
            "Only 'Bearer <OAuthToken>' or 'Token <PAT>' types are supported"
            in body["error"]
        )

    async def test_middleware_empty_token(self):
        """Test UserTokenMiddleware with empty token."""
        # Create middleware instance
        app = MagicMock()
        mcp_server = MagicMock()
        # Mock the settings attribute with proper structure
        settings_mock = MagicMock()
        settings_mock.streamable_http_path = "/mcp"
        mcp_server.settings = settings_mock
        middleware = UserTokenMiddleware(app, mcp_server_ref=mcp_server)

        # Create mock request with empty Bearer token
        request = MockFastMCP.create_request()
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {"Authorization": "Bearer "}

        # Mock call_next (shouldn't be called)
        async def mock_call_next(req):
            pytest.fail("call_next should not be called for empty token")

        # Process request
        response = await middleware.dispatch(request, mock_call_next)

        # Verify error response
        assert response.status_code == 401
        body = json.loads(response.body)
        assert "error" in body
        assert "Empty Bearer token" in body["error"]

    async def test_middleware_non_mcp_path(self):
        """Test UserTokenMiddleware bypasses non-MCP paths."""
        # Create middleware instance
        app = MagicMock()
        mcp_server = MagicMock()
        # Mock the settings attribute with proper structure
        settings_mock = MagicMock()
        settings_mock.streamable_http_path = "/mcp"
        mcp_server.settings = settings_mock
        middleware = UserTokenMiddleware(app, mcp_server_ref=mcp_server)

        # Create mock request for different path
        request = MockFastMCP.create_request()
        request.url.path = "/healthz"
        request.method = "GET"
        request.headers = {}

        # Ensure state doesn't have user_atlassian_token initially
        if hasattr(request.state, "user_atlassian_token"):
            delattr(request.state, "user_atlassian_token")

        # Mock call_next
        async def mock_call_next(req):
            # Should be called without modification
            # Check that user_atlassian_token was not added
            token_added = False
            try:
                _ = req.state.user_atlassian_token
                token_added = True
            except AttributeError:
                token_added = False
            assert not token_added, (
                "user_atlassian_token should not be set for non-MCP paths"
            )
            return JSONResponse({"status": "ok"})

        # Process request
        response = await middleware.dispatch(request, mock_call_next)

        # Verify response
        assert response.status_code == 200

    async def test_concurrent_tool_execution(
        self, atlassian_mcp_server, mock_jira_config, mock_confluence_config
    ):
        """Test concurrent execution of multiple tools."""
        with MockEnvironment.basic_auth_env():
            # Create app context
            app_context = MainAppContext(
                full_jira_config=mock_jira_config,
                full_confluence_config=mock_confluence_config,
                read_only=False,
                enabled_tools=None,
            )

            # Track execution order
            execution_order = []

            # Mock tool implementations
            import anyio

            async def mock_jira_get_issue(ctx: Context, issue_key: str):
                execution_order.append(f"jira_get_issue_{issue_key}_start")
                await anyio.sleep(0.1)  # Simulate API call
                execution_order.append(f"jira_get_issue_{issue_key}_end")
                return json.dumps({"key": issue_key, "summary": f"Issue {issue_key}"})

            async def mock_confluence_get_page(ctx: Context, page_id: str):
                execution_order.append(f"confluence_get_page_{page_id}_start")
                await anyio.sleep(0.05)  # Simulate API call (faster)
                execution_order.append(f"confluence_get_page_{page_id}_end")
                return json.dumps({"id": page_id, "title": f"Page {page_id}"})

            # Mock request context
            request_context = MagicMock()
            request_context.lifespan_context = {"app_lifespan_context": app_context}

            # Create context for tool execution
            mock_fastmcp = MagicMock()
            mock_fastmcp.request_context = request_context
            ctx = Context(fastmcp=mock_fastmcp)

            # Execute tools concurrently using anyio for backend compatibility

            # Execute tools concurrently
            async def run_all_tools():
                results = []
                async with anyio.create_task_group() as tg:
                    result_futures = []

                    async def run_and_store(coro, index):
                        result = await coro
                        result_futures.append((index, result))

                    tg.start_soon(run_and_store, mock_jira_get_issue(ctx, "TEST-1"), 0)
                    tg.start_soon(run_and_store, mock_jira_get_issue(ctx, "TEST-2"), 1)
                    tg.start_soon(
                        run_and_store, mock_confluence_get_page(ctx, "123"), 2
                    )
                    tg.start_soon(
                        run_and_store, mock_confluence_get_page(ctx, "456"), 3
                    )

                # Sort results by original index
                result_futures.sort(key=lambda x: x[0])
                return [r[1] for r in result_futures]

            results = await run_all_tools()

            # Verify results
            assert len(results) == 4
            assert json.loads(results[0])["key"] == "TEST-1"
            assert json.loads(results[1])["key"] == "TEST-2"
            assert json.loads(results[2])["id"] == "123"
            assert json.loads(results[3])["id"] == "456"

            # Verify concurrent execution (Confluence tasks should complete before Jira)
            assert execution_order.index(
                "confluence_get_page_123_end"
            ) < execution_order.index("jira_get_issue_TEST-1_end")
            assert execution_order.index(
                "confluence_get_page_456_end"
            ) < execution_order.index("jira_get_issue_TEST-2_end")

    async def test_error_propagation_through_middleware(self):
        """Test error propagation through the middleware chain."""
        # Create middleware instance
        app = MagicMock()
        mcp_server = MagicMock()
        # Mock the settings attribute with proper structure
        settings_mock = MagicMock()
        settings_mock.streamable_http_path = "/mcp"
        mcp_server.settings = settings_mock
        middleware = UserTokenMiddleware(app, mcp_server_ref=mcp_server)

        # Create mock request
        request = MockFastMCP.create_request()
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {"Authorization": "Bearer valid-token"}

        # Mock call_next to raise an exception
        async def mock_call_next(req):
            raise ValueError("Test error from downstream")

        # Process request
        with pytest.raises(ValueError) as exc_info:
            await middleware.dispatch(request, mock_call_next)

        # Verify error propagated
        assert str(exc_info.value) == "Test error from downstream"

    async def test_lifespan_context_initialization(self):
        """Test lifespan context initialization with various configurations."""
        # Test with full configuration
        with MockEnvironment.basic_auth_env():
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_config,
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
                ) as mock_conf_config,
            ):
                # Configure mocks
                jira_config = MagicMock()
                jira_config.is_auth_configured.return_value = True
                mock_jira_config.return_value = jira_config

                conf_config = MagicMock()
                conf_config.is_auth_configured.return_value = True
                mock_conf_config.return_value = conf_config

                # Run lifespan
                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config == jira_config
                    assert app_context.full_confluence_config == conf_config
                    assert app_context.read_only is False
                    assert app_context.enabled_tools is None

    async def test_lifespan_with_partial_configuration(self):
        """Test lifespan with only Jira configured."""
        env_vars = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_config,
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
                ) as mock_conf_config,
            ):
                # Configure mocks
                jira_config = MagicMock()
                jira_config.is_auth_configured.return_value = True
                mock_jira_config.return_value = jira_config

                # Confluence not configured
                mock_conf_config.side_effect = Exception("No Confluence config")

                # Run lifespan
                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config == jira_config
                    assert app_context.full_confluence_config is None

    async def test_lifespan_with_read_only_mode(self):
        """Test lifespan with read-only mode enabled."""
        with MockEnvironment.basic_auth_env():
            with patch.dict(os.environ, {"READ_ONLY_MODE": "true"}):
                with patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_config:
                    # Configure mock
                    jira_config = MagicMock()
                    jira_config.is_auth_configured.return_value = True
                    mock_jira_config.return_value = jira_config

                    # Run lifespan
                    app = MagicMock()
                    async with main_lifespan(app) as context:
                        app_context = context["app_lifespan_context"]
                        assert app_context.read_only is True

    async def test_lifespan_with_enabled_tools(self):
        """Test lifespan with specific enabled tools."""
        with MockEnvironment.basic_auth_env():
            with patch.dict(
                os.environ,
                {
                    "ENABLED_TOOLS": "jira_get_issue,jira_search_issues,confluence_get_page"
                },
            ):
                with patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_config:
                    # Configure mock
                    jira_config = MagicMock()
                    jira_config.is_auth_configured.return_value = True
                    mock_jira_config.return_value = jira_config

                    # Run lifespan
                    app = MagicMock()
                    async with main_lifespan(app) as context:
                        app_context = context["app_lifespan_context"]
                        assert app_context.enabled_tools == [
                            "jira_get_issue",
                            "jira_search_issues",
                            "confluence_get_page",
                        ]

    async def test_health_check_endpoint(self, atlassian_mcp_server):
        """Test the health check endpoint."""
        # Mock the http_app method to return a test app
        test_app = Starlette()
        test_app.add_route("/healthz", health_check, methods=["GET"])

        # Mock the method
        atlassian_mcp_server.http_app = MagicMock(return_value=test_app)

        # Create test client
        app = atlassian_mcp_server.http_app()

        # Use TestClient for synchronous testing of the Starlette app
        with TestClient(app) as client:
            response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_combined_filtering_scenarios(
        self, atlassian_mcp_server, mock_jira_config
    ):
        """Test combined filtering: read-only mode + enabled tools + service availability."""
        with MockEnvironment.basic_auth_env():
            # Create app context with multiple constraints
            app_context = MainAppContext(
                full_jira_config=mock_jira_config,
                full_confluence_config=None,  # Confluence not configured
                read_only=True,  # Read-only mode
                enabled_tools=[
                    "jira_get_issue",
                    "jira_create_issue",
                    "confluence_get_page",
                ],  # Mix of tools
            )

            # Mock request context
            request_context = MagicMock()
            request_context.lifespan_context = {"app_lifespan_context": app_context}

            # Set up server context
            atlassian_mcp_server._mcp_server = MagicMock()
            atlassian_mcp_server._mcp_server.request_context = request_context

            # Mock get_tools
            async def mock_get_tools():
                tools = {}
                tool_configs = [
                    ("jira_get_issue", {"jira", "read"}),  # Should be included
                    ("jira_create_issue", {"jira", "write"}),  # Excluded by read-only
                    (
                        "jira_search_issues",
                        {"jira", "read"},
                    ),  # Excluded by enabled_tools
                    (
                        "confluence_get_page",
                        {"confluence", "read"},
                    ),  # Excluded by service not configured
                ]

                for tool_name, tags in tool_configs:
                    tool = MagicMock(spec=FastMCPTool)
                    tool.tags = tags
                    tool.to_mcp_tool.return_value = MCPTool(
                        name=tool_name,
                        description=f"Tool {tool_name}",
                        inputSchema={"type": "object", "properties": {}},
                    )
                    tools[tool_name] = tool

                return tools

            atlassian_mcp_server.get_tools = mock_get_tools

            # Get filtered tools
            tools = await atlassian_mcp_server._list_tools_mcp()

            # Only jira_get_issue should pass all filters
            tool_names = [tool.name for tool in tools]
            assert tool_names == ["jira_get_issue"]

    async def test_request_context_missing(self, atlassian_mcp_server):
        """Test handling when request context is missing."""
        # Set up server without request context
        atlassian_mcp_server._mcp_server = MagicMock()
        atlassian_mcp_server._mcp_server.request_context = None

        # Mock get_tools (shouldn't be called)
        async def mock_get_tools():
            pytest.fail("get_tools should not be called when context is missing")

        atlassian_mcp_server.get_tools = mock_get_tools

        # Get filtered tools
        tools = await atlassian_mcp_server._list_tools_mcp()

        # Should return empty list
        assert tools == []

    async def test_http_app_middleware_integration(self, atlassian_mcp_server):
        """Test HTTP app creation with custom middleware."""
        # Create a mock app with middleware
        mock_app = MagicMock(spec=Starlette)
        mock_app.middleware = [
            Middleware(UserTokenMiddleware, mcp_server_ref=atlassian_mcp_server)
        ]

        # Mock the http_app method
        atlassian_mcp_server.http_app = MagicMock(return_value=mock_app)

        # Create HTTP app with custom middleware
        custom_middleware = []
        app = atlassian_mcp_server.http_app(
            path="/custom", middleware=custom_middleware, transport="sse"
        )

        # Verify app is created
        assert app is not None
        # UserTokenMiddleware should be added automatically
        assert any("UserTokenMiddleware" in str(m) for m in app.middleware)

    async def test_tool_execution_with_authentication_error(self, atlassian_mcp_server):
        """Test tool execution when authentication fails."""
        from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

        # Mock a tool that raises authentication error
        async def mock_failing_tool(ctx: Context):
            raise MCPAtlassianAuthenticationError("Invalid credentials")

        # Create context
        mock_fastmcp = MagicMock()
        ctx = Context(fastmcp=mock_fastmcp)

        # Execute tool and verify error handling
        with pytest.raises(MCPAtlassianAuthenticationError):
            await mock_failing_tool(ctx)
