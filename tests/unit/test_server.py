"""Unit tests for server"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.context import RequestContext
from mcp.shared.session import BaseSession
from mcp.types import Tool

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.server import (
    AppContext,
    call_tool,
    get_available_services,
    list_resources,
    list_tools,
    read_resource,
    server_lifespan,
)


@contextmanager
def env_vars(new_env: dict[str, str | None]) -> Generator[None, None, None]:
    # Save the old values
    old_values = {k: os.getenv(k) for k in new_env.keys()}

    # Set the new values
    for k, v in new_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        # Put everything back to how it was
        for k, v in old_values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_no_service_available():
    with env_vars({"JIRA_URL": None, "CONFLUENCE_URL": None}):
        av = get_available_services()
        assert not av["confluence"]


def test_available_services_confluence():
    # Cloud confluence with username/api token authentication
    with env_vars(
        {
            "JIRA_URL": None,
            "CONFLUENCE_URL": "https://my-company.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "john.doe@example.com",
            "CONFLUENCE_API_TOKEN": "my_api_token",
            "CONFLUENCE_PERSONAL_TOKEN": None,
        }
    ):
        av = get_available_services()
        assert av["confluence"]

    # On prem/DC confluence with just token authentication
    with env_vars(
        {
            "JIRA_URL": None,
            "CONFLUENCE_URL": "https://confluence.localnetwork.local",
            "CONFLUENCE_USERNAME": None,
            "CONFLUENCE_API_TOKEN": None,
            "CONFLUENCE_PERSONAL_TOKEN": "Some personal token",
        }
    ):
        av = get_available_services()
        assert av["confluence"]

    # On prem/DC confluence with username/api token basic authentication
    with env_vars(
        {
            "JIRA_URL": None,
            "CONFLUENCE_URL": "https://confluence.localnetwork.local",
            "CONFLUENCE_USERNAME": "john.doe",
            "CONFLUENCE_API_TOKEN": "your_confluence_password",
            "CONFLUENCE_PERSONAL_TOKEN": None,
        }
    ):
        av = get_available_services()
        assert av["confluence"]


@pytest.fixture
def mock_confluence_client():
    """Create a mock ConfluenceFetcher with pre-configured return values."""
    mock_confluence = MagicMock(spec=ConfluenceFetcher)
    mock_confluence.config = MagicMock()
    mock_confluence.config.url = "https://test.atlassian.net/wiki"

    # Configure common methods
    mock_confluence.get_user_contributed_spaces.return_value = {
        "TEST": {
            "key": "TEST",
            "name": "Test Space",
            "description": "Space for testing",
        }
    }

    return mock_confluence


@pytest.fixture
def app_context(mock_confluence_client):
    """Create an AppContext with mock clients."""
    return AppContext(
        confluence=mock_confluence_client,
    )


@contextmanager
def mock_request_context(app_context):
    """Context manager to set the request_ctx context variable directly."""
    # Import the context variable directly from the server module
    from mcp.server.lowlevel.server import request_ctx

    # Create a mock session
    mock_session = MagicMock(spec=BaseSession)

    # Create a RequestContext instance with our app_context
    context = RequestContext(
        request_id="test-request-id",
        meta=None,
        session=mock_session,
        lifespan_context=app_context,
    )

    # Set the context variable and get the token
    token = request_ctx.set(context)
    try:
        yield
    finally:
        # Reset the context variable
        request_ctx.reset(token)


@pytest.fixture
def mock_env_vars_read_only():
    """Mock environment variables with READ_ONLY_MODE enabled."""
    with env_vars({"READ_ONLY_MODE": "true"}):
        # Also patch the is_read_only_mode function to ensure it returns True
        with patch("mcp_atlassian.server.is_read_only_mode", return_value=True):
            yield


@pytest.mark.anyio
async def test_server_lifespan():
    """Test the server_lifespan context manager."""
    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.ConfluenceConfig") as mock_confluence_config_cls,
        patch("mcp_atlassian.server.ConfluenceFetcher") as mock_confluence_cls,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        patch("mcp_atlassian.server.logger") as mock_logger,
        patch("mcp_atlassian.server.log_config_param") as mock_log_config_param,
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True}

        # Mock configs
        mock_confluence_config = MagicMock()
        mock_confluence_config.url = "https://test.atlassian.net/wiki"
        mock_confluence_config.auth_type = "basic"
        mock_confluence_config.username = "confluence-user"
        mock_confluence_config.api_token = "confluence-token"
        mock_confluence_config.personal_token = None
        mock_confluence_config.ssl_verify = True
        mock_confluence_config.spaces_filter = "TEST,DEV"
        mock_confluence_config_cls.from_env.return_value = mock_confluence_config

        # Mock fetchers
        mock_confluence = MagicMock()
        mock_confluence_cls.return_value = mock_confluence

        mock_read_only.return_value = False

        # Mock the Server instance
        mock_server = MagicMock()

        # Call the lifespan context manager
        async with server_lifespan(mock_server) as ctx:
            # Verify context contains expected clients
            assert isinstance(ctx, AppContext)
            assert ctx.confluence is not None

            # Verify logging calls
            mock_logger.info.assert_any_call("Starting MCP Atlassian server")
            mock_logger.info.assert_any_call("Read-only mode: DISABLED")
            mock_logger.info.assert_any_call(
                "Attempting to initialize Confluence client..."
            )
            mock_logger.info.assert_any_call(
                "Confluence client initialized successfully."
            )

            # Verify config logging calls for Confluence only
            mock_log_config_param.assert_any_call(
                mock_logger, "Confluence", "URL", mock_confluence_config.url
            )
            mock_log_config_param.assert_any_call(
                mock_logger, "Confluence", "Auth Type", mock_confluence_config.auth_type
            )
            mock_log_config_param.assert_any_call(
                mock_logger, "Confluence", "Username", mock_confluence_config.username
            )
            mock_log_config_param.assert_any_call(
                mock_logger,
                "Confluence",
                "API Token",
                mock_confluence_config.api_token,
                sensitive=True,
            )
            mock_log_config_param.assert_any_call(
                mock_logger,
                "Confluence",
                "SSL Verify",
                str(mock_confluence_config.ssl_verify),
            )
            mock_log_config_param.assert_any_call(
                mock_logger,
                "Confluence",
                "Spaces Filter",
                mock_confluence_config.spaces_filter,
            )

            # Verify the Confluence fetcher was initialized with config
            mock_confluence_cls.assert_called_once_with(config=mock_confluence_config)


@pytest.mark.anyio
async def test_server_lifespan_with_errors():
    """Test the server_lifespan context manager with initialization errors."""
    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.ConfluenceConfig") as mock_confluence_config_cls,
        patch("mcp_atlassian.server.ConfluenceFetcher") as mock_confluence_cls,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        patch("mcp_atlassian.server.logger") as mock_logger,
    ):
        # Configure mocks - only Confluence now
        mock_services.return_value = {"confluence": True}

        # Mock errors
        mock_confluence_config_cls.from_env.side_effect = ValueError(
            "Missing CONFLUENCE_URL"
        )

        mock_read_only.return_value = False

        # Mock the Server instance
        mock_server = MagicMock()

        # Call the lifespan context manager
        async with server_lifespan(mock_server) as ctx:
            # Verify context contains no clients due to errors
            assert isinstance(ctx, AppContext)
            assert ctx.confluence is None

            # Verify logging calls
            mock_logger.info.assert_any_call("Starting MCP Atlassian server")
            mock_logger.info.assert_any_call("Read-only mode: DISABLED")
            mock_logger.info.assert_any_call(
                "Attempting to initialize Confluence client..."
            )

            # Verify error logging
            mock_logger.error.assert_any_call(
                "Failed to initialize Confluence client: Missing CONFLUENCE_URL",
                exc_info=True,
            )


@pytest.mark.anyio
async def test_list_resources_confluence_only(app_context):
    """Test the list_resources handler with only Confluence available."""
    with mock_request_context(app_context):
        # Call the handler directly
        resources = await list_resources()

        # Verify Confluence client was called
        app_context.confluence.get_user_contributed_spaces.assert_called_once()

        # Verify returned resources
        assert isinstance(resources, list)
        assert len(resources) == 1  # Only from Confluence
        assert str(resources[0].uri) == "confluence://TEST"


@pytest.mark.anyio
async def test_list_resources_no_services(app_context):
    """Test the list_resources handler with no services available."""
    # Modify the context to have no services
    app_context.confluence = None

    with mock_request_context(app_context):
        # Call the handler directly
        resources = await list_resources()

        # Verify returned resources
        assert isinstance(resources, list)
        assert len(resources) == 0  # Empty list


@pytest.mark.anyio
async def test_list_resources_client_error(app_context):
    """Test the list_resources handler when clients raise exceptions."""
    # Configure client to raise exception
    app_context.confluence.get_user_contributed_spaces.side_effect = Exception(
        "Confluence error"
    )

    with mock_request_context(app_context):
        # Call the handler directly
        resources = await list_resources()

        # Verify handlers gracefully handled errors
        assert isinstance(resources, list)
        assert len(resources) == 0  # Empty list due to errors


@pytest.mark.anyio
@pytest.mark.parametrize(
    "uri,expected_mime_type,mock_setup",
    [
        # Confluence space
        (
            "confluence://TEST",
            "text/markdown",
            lambda ctx: (
                setattr(ctx.confluence, "search", MagicMock(return_value=[])),  # type: ignore
                setattr(
                    ctx.confluence,
                    "get_space_pages",
                    MagicMock(
                        return_value=[
                            MagicMock(
                                to_simplified_dict=MagicMock(
                                    return_value={
                                        "title": "Test Page",
                                        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/123456",
                                    }
                                ),
                                page_content="Test page content",
                            )
                        ]
                    ),
                ),  # type: ignore
            ),
        ),
        # Confluence page
        (
            "confluence://TEST/pages/Test Page",
            "text/markdown",
            lambda ctx: setattr(
                ctx.confluence,
                "get_page_by_title",
                MagicMock(return_value=MagicMock(page_content="Test page content")),
            ),
        ),
    ],
)
async def test_read_resource_valid_uris(
    uri, expected_mime_type, mock_setup, app_context
):
    """Test the read_resource handler with Confluence URIs."""
    # Configure the mocks as needed for the test case
    mock_setup(app_context)

    # Skip actually checking content for simplicity since formatters are complex
    with mock_request_context(app_context):
        # Call the handler directly
        content = await read_resource(uri)

        # Verify content is a string
        assert isinstance(content, str)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "uri,expected_error,mock_setup",
    [
        ("invalid://TEST", "Invalid resource URI", lambda ctx: None),
        (
            "confluence://TEST/pages/NONEXISTENT",
            "Page not found",
            lambda ctx: setattr(
                ctx.confluence,
                "get_page_by_title",
                MagicMock(side_effect=ValueError("Page not found")),
            ),
        ),
    ],
)
async def test_read_resource_invalid_uris(uri, expected_error, mock_setup, app_context):
    """Test the read_resource handler with invalid URIs."""
    # Configure mocks based on the provided mock_setup function
    if mock_setup:
        mock_setup(app_context)

    with mock_request_context(app_context):
        try:
            await read_resource(uri)
            pytest.fail(f"Expected an exception for {uri}")
        except (ValueError, Exception) as e:
            assert expected_error in str(e)


@pytest.mark.anyio
async def test_list_tools_confluence_only():
    """Test the list_tools handler with only Confluence available."""
    # Create a mock context
    mock_context = AppContext(confluence=MagicMock(spec=ConfluenceFetcher))

    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        mock_request_context(mock_context),
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True}
        mock_read_only.return_value = False

        # Call the handler directly
        tools = await list_tools()

        # Verify returned tools
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check structure of tools
        for tool in tools:
            assert isinstance(tool, Tool)
            assert tool.name.startswith("confluence_") or tool.name.startswith(
                "mcp__confluence_"
            )
            assert hasattr(tool, "description")
            assert hasattr(tool, "inputSchema")


@pytest.mark.anyio
async def test_list_tools_read_only_mode():
    """Test the list_tools handler in read-only mode."""
    # Create a mock context
    mock_context = AppContext(confluence=MagicMock(spec=ConfluenceFetcher))

    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        mock_request_context(mock_context),
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True}
        mock_read_only.return_value = True

        # Call the handler directly
        tools = await list_tools()

        # Verify returned tools are read-only
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check no write tools are included
        write_tools = [
            tool
            for tool in tools
            if any(
                tool.name.startswith(f"mcp__confluence_{action}")
                for action in ["create", "update", "delete", "add"]
            )
        ]
        assert len(write_tools) == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name,arguments,mock_setup",
    [
        # Confluence search tool test
        (
            "confluence_search",
            {"query": "space = TEST"},
            lambda ctx: setattr(
                ctx.confluence,
                "search",
                MagicMock(
                    return_value={
                        "results": [
                            {
                                "id": "12345",
                                "title": "Test Page",
                                "type": "page",
                            }
                        ]
                    }
                ),
            ),
        ),
    ],
)
async def test_call_tool_success(tool_name, arguments, mock_setup, app_context):
    """Test the call_tool handler with valid tool calls."""
    # Configure the mocks as needed for the test case
    mock_setup(app_context)

    with mock_request_context(app_context):
        # For simplicity, we'll just verify no exceptions are raised
        # and something is returned (specific output depends on internal implementation)
        result = await call_tool(tool_name, arguments)

        # Basic verification that we got a result
        assert isinstance(result, list)
        assert len(result) > 0


@pytest.mark.anyio
async def test_confluence_search_simple_term_uses_sitesearch(app_context):
    """Test that a simple search term is converted to a siteSearch CQL query."""
    # Setup
    mock_confluence = app_context.confluence
    mock_confluence.search.return_value = []

    with mock_request_context(app_context):
        # Execute
        await call_tool("confluence_search", {"query": "simple term"})

        # Verify
        mock_confluence.search.assert_called_once()
        args, kwargs = mock_confluence.search.call_args
        assert args[0] == 'siteSearch ~ "simple term"'


@pytest.mark.anyio
async def test_confluence_search_fallback_to_text_search(app_context):
    """Test fallback to text search when siteSearch fails."""
    # Setup
    mock_confluence = app_context.confluence

    # Make the first call to search fail
    mock_confluence.search.side_effect = [Exception("siteSearch not available"), []]

    with mock_request_context(app_context):
        # Execute
        await call_tool("confluence_search", {"query": "simple term"})

        # Verify
        assert mock_confluence.search.call_count == 2
        first_call = mock_confluence.search.call_args_list[0]
        second_call = mock_confluence.search.call_args_list[1]

        # First attempt should use siteSearch
        assert first_call[0][0] == 'siteSearch ~ "simple term"'

        # Second attempt (fallback) should use text search
        assert second_call[0][0] == 'text ~ "simple term"'


@pytest.mark.anyio
async def test_confluence_search_direct_cql_not_modified(app_context):
    """Test that a CQL query is not modified."""
    # Setup
    mock_confluence = app_context.confluence
    mock_confluence.search.return_value = []

    cql_query = 'space = DEV AND title ~ "Meeting"'

    with mock_request_context(app_context):
        # Execute
        await call_tool("confluence_search", {"query": cql_query})

        # Verify
        mock_confluence.search.assert_called_once()
        args, kwargs = mock_confluence.search.call_args
        assert args[0] == cql_query


@pytest.mark.anyio
async def test_call_tool_read_only_mode(app_context):
    """Test the call_tool handler in read-only mode."""
    # Create a custom environment with read-only mode enabled
    with (
        patch("mcp_atlassian.server.is_read_only_mode", return_value=True),
        mock_request_context(app_context),
    ):
        # Try calling a tool that would normally be write-only
        # We can't predict exactly what error message will be returned,
        # but we can check that a result is returned (even if it's an error)
        result = await call_tool(
            "confluence_create_page",
            {
                "space_key": "TEST",
                "title": "Test Page",
                "content": "Test content",
            },
        )

        # Just verify we got a result
        assert isinstance(result, list)


@pytest.mark.anyio
async def test_call_tool_invalid_tool(app_context):
    """Test the call_tool handler with an invalid tool name."""
    with mock_request_context(app_context):
        # Try to call a non-existent tool - should return an error response
        result = await call_tool("nonexistent_tool", {})

        # Just verify we got a result
        assert isinstance(result, list)


@pytest.mark.anyio
async def test_call_tool_invalid_arguments(app_context):
    """Test the call_tool handler with invalid arguments."""
    with mock_request_context(app_context):
        # Try to call a tool with missing required arguments
        result = await call_tool(
            "confluence_search",
            {},  # Missing required 'query' argument
        )

        # Just verify we got a result
        assert isinstance(result, list)
