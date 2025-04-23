"""Unit tests for server"""

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.context import RequestContext
from mcp.shared.session import BaseSession
from mcp.types import Tool

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.server import (
    AppContext,
    call_tool,
    get_available_services,
    list_tools,
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
        assert not av["jira"]
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
        assert not av["jira"]
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
        assert not av["jira"]
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
        assert not av["jira"]
        assert av["confluence"]


def test_available_services_jira():
    """Test available services"""
    # Cloud jira with username/api token authentication
    with env_vars(
        {
            "JIRA_URL": "https://my-company.atlassian.net",
            "JIRA_USERNAME": "john.doe@example.com",
            "JIRA_API_TOKEN": "my_api_token",
            "JIRA_PERSONAL_TOKEN": None,
            "CONFLUENCE_URL": None,
        }
    ):
        av = get_available_services()
        assert av["jira"]
        assert not av["confluence"]

    # On-prem/DC jira with just token authentication
    with env_vars(
        {
            "JIRA_URL": "https://jira.localnetwork.local",
            "JIRA_USERNAME": None,
            "JIRA_API_TOKEN": None,
            "JIRA_PERSONAL_TOKEN": "my_personal_token",
            "CONFLUENCE_URL": None,
        }
    ):
        av = get_available_services()
        assert av["jira"]
        assert not av["confluence"]


# Phase 1: Setup & Fixtures
@pytest.fixture
def mock_jira_client():
    """Create a mock JiraFetcher with pre-configured return values."""
    mock_jira = MagicMock(spec=JiraFetcher)
    mock_jira.config = MagicMock()
    mock_jira.config.url = "https://test.atlassian.net"

    # Configure common methods
    mock_jira.get_current_user_account_id.return_value = "test-account-id"

    # Configure jira instance
    mock_jira.jira = MagicMock()
    mock_jira.jira.jql.return_value = {
        "issues": [
            {
                "fields": {
                    "project": {
                        "key": "TEST",
                        "name": "Test Project",
                        "description": "Project for testing",
                    }
                }
            }
        ]
    }

    return mock_jira


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
def app_context(mock_jira_client, mock_confluence_client):
    """Create an AppContext with mock clients."""
    return AppContext(
        jira=mock_jira_client,
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


# Phase 2: Test Core Handler Functions
@pytest.mark.anyio
async def test_server_lifespan():
    """Test the server_lifespan context manager."""
    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.ConfluenceConfig") as mock_confluence_config_cls,
        patch("mcp_atlassian.server.JiraConfig") as mock_jira_config_cls,
        patch("mcp_atlassian.server.ConfluenceFetcher") as mock_confluence_cls,
        patch("mcp_atlassian.server.JiraFetcher") as mock_jira_cls,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        patch("mcp_atlassian.server.logger") as mock_logger,
        patch("mcp_atlassian.server.log_config_param") as mock_log_config_param,
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True, "jira": True}

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

        mock_jira_config = MagicMock()
        mock_jira_config.url = "https://test.atlassian.net"
        mock_jira_config.auth_type = "basic"
        mock_jira_config.username = "jira-user"
        mock_jira_config.api_token = "jira-token"
        mock_jira_config.personal_token = None
        mock_jira_config.ssl_verify = True
        mock_jira_config.projects_filter = "PROJ,TEST"
        mock_jira_config_cls.from_env.return_value = mock_jira_config

        # Mock fetchers
        mock_confluence = MagicMock()
        mock_confluence_cls.return_value = mock_confluence

        mock_jira = MagicMock()
        mock_jira_cls.return_value = mock_jira

        mock_read_only.return_value = False

        # Mock the Server instance
        mock_server = MagicMock()

        # Call the lifespan context manager
        async with server_lifespan(mock_server) as ctx:
            # Verify context contains expected clients
            assert isinstance(ctx, AppContext)
            assert ctx.confluence is not None
            assert ctx.jira is not None

            # Verify logging calls
            mock_logger.info.assert_any_call("Starting MCP Atlassian server")
            mock_logger.info.assert_any_call("Read-only mode: DISABLED")
            mock_logger.info.assert_any_call(
                "Attempting to initialize Confluence client..."
            )
            mock_logger.info.assert_any_call(
                "Confluence client initialized successfully."
            )
            mock_logger.info.assert_any_call("Attempting to initialize Jira client...")
            mock_logger.info.assert_any_call("Jira client initialized successfully.")

            # Verify config logging calls
            assert (
                mock_log_config_param.call_count >= 10
            )  # At least 5 params for each service
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

            mock_log_config_param.assert_any_call(
                mock_logger, "Jira", "URL", mock_jira_config.url
            )
            mock_log_config_param.assert_any_call(
                mock_logger, "Jira", "Auth Type", mock_jira_config.auth_type
            )
            mock_log_config_param.assert_any_call(
                mock_logger, "Jira", "Username", mock_jira_config.username
            )
            mock_log_config_param.assert_any_call(
                mock_logger,
                "Jira",
                "API Token",
                mock_jira_config.api_token,
                sensitive=True,
            )
            mock_log_config_param.assert_any_call(
                mock_logger, "Jira", "SSL Verify", str(mock_jira_config.ssl_verify)
            )
            mock_log_config_param.assert_any_call(
                mock_logger, "Jira", "Projects Filter", mock_jira_config.projects_filter
            )

            # Verify the fetchers were initialized with configs
            mock_confluence_cls.assert_called_once_with(config=mock_confluence_config)
            mock_jira_cls.assert_called_once_with(config=mock_jira_config)


@pytest.mark.anyio
async def test_server_lifespan_with_errors():
    """Test the server_lifespan context manager with initialization errors."""
    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.ConfluenceConfig") as mock_confluence_config_cls,
        patch("mcp_atlassian.server.JiraConfig") as mock_jira_config_cls,
        patch("mcp_atlassian.server.ConfluenceFetcher") as mock_confluence_cls,
        patch("mcp_atlassian.server.JiraFetcher") as mock_jira_cls,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        patch("mcp_atlassian.server.logger") as mock_logger,
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True, "jira": True}

        # Mock errors
        mock_confluence_config_cls.from_env.side_effect = ValueError(
            "Missing CONFLUENCE_URL"
        )
        mock_jira_config_cls.from_env.side_effect = ValueError("Missing JIRA_URL")

        mock_read_only.return_value = False

        # Mock the Server instance
        mock_server = MagicMock()

        # Call the lifespan context manager
        async with server_lifespan(mock_server) as ctx:
            # Verify context contains no clients due to errors
            assert isinstance(ctx, AppContext)
            assert ctx.confluence is None
            assert ctx.jira is None

            # Verify logging calls
            mock_logger.info.assert_any_call("Starting MCP Atlassian server")
            mock_logger.info.assert_any_call("Read-only mode: DISABLED")
            mock_logger.info.assert_any_call(
                "Attempting to initialize Confluence client..."
            )
            mock_logger.info.assert_any_call("Attempting to initialize Jira client...")

            # Verify error logging
            mock_logger.error.assert_any_call(
                "Failed to initialize Confluence client: Missing CONFLUENCE_URL",
                exc_info=True,
            )
            mock_logger.error.assert_any_call(
                "Failed to initialize Jira client: Missing JIRA_URL", exc_info=True
            )


@pytest.mark.anyio
async def test_list_tools_both_services():
    """Test the list_tools handler with both services available."""
    # Create a mock context
    mock_context = AppContext(
        jira=MagicMock(spec=JiraFetcher), confluence=MagicMock(spec=ConfluenceFetcher)
    )

    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        mock_request_context(mock_context),
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True, "jira": True}
        mock_read_only.return_value = False

        # Call the handler directly
        tools = await list_tools()

        # Verify returned tools
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check structure of tools
        for tool in tools:
            assert isinstance(tool, Tool)
            assert tool.name.startswith(
                ("jira_", "confluence_")
            ) or tool.name.startswith(("mcp__jira_", "mcp__confluence_"))
            assert hasattr(tool, "description")
            assert hasattr(tool, "inputSchema")


@pytest.mark.anyio
async def test_list_tools_read_only_mode():
    """Test the list_tools handler in read-only mode."""
    # Create a mock context
    mock_context = AppContext(
        jira=MagicMock(spec=JiraFetcher), confluence=MagicMock(spec=ConfluenceFetcher)
    )

    with (
        patch("mcp_atlassian.server.get_available_services") as mock_services,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        mock_request_context(mock_context),
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True, "jira": True}
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
                tool.name.startswith(f"mcp__{service}_{action}")
                for service in ["jira", "confluence"]
                for action in ["create", "update", "delete", "add"]
            )
        ]
        assert len(write_tools) == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name,arguments,mock_setup",
    [
        # Jira search tool test
        (
            "jira_search",
            {"jql": "project = TEST"},
            lambda ctx: setattr(
                ctx.jira,
                "search_issues",
                MagicMock(
                    return_value=[
                        {
                            "key": "TEST-123",
                            "fields": {
                                "summary": "Test Issue",
                            },
                        }
                    ]
                ),
            ),
        ),
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
            "jira_create_issue",
            {
                "project_key": "TEST",
                "summary": "Test Issue",
                "issue_type": "Bug",
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
            "jira_search",
            {},  # Missing required 'jql' argument
        )

        # Just verify we got a result
        assert isinstance(result, list)


@pytest.mark.anyio
async def test_call_tool_jira_create_issue_with_components(app_context):
    """Test calling jira_create_issue with components works correctly."""
    # Setup mock
    mock_issue = MagicMock()
    mock_issue.key = "TEST-123"
    mock_issue.to_simplified_dict.return_value = {
        "key": "TEST-123",
        "summary": "Test Issue with Components",
    }
    app_context.jira.create_issue.return_value = mock_issue

    with (
        patch("mcp_atlassian.server.is_read_only_mode", return_value=False),
        mock_request_context(app_context),
    ):
        # Call the tool with components parameter
        result = await call_tool(
            "jira_create_issue",
            {
                "project_key": "TEST",
                "summary": "Test Issue with Components",
                "issue_type": "Bug",
                "components": "UI,API",
            },
        )

        # Verify the create_issue method was called with correct parameters
        app_context.jira.create_issue.assert_called_once_with(
            project_key="TEST",
            summary="Test Issue with Components",
            issue_type="Bug",
            description="",
            assignee=None,
            components=["UI", "API"],
        )

        # Verify we got a result
        assert isinstance(result, list)

        # Reset the mock
        app_context.jira.create_issue.reset_mock()

        # Call the tool without components parameter
        result = await call_tool(
            "jira_create_issue",
            {
                "project_key": "TEST",
                "summary": "Test Issue without Components",
                "issue_type": "Bug",
            },
        )

        # Verify the create_issue method was called with components=None
        app_context.jira.create_issue.assert_called_once()
        call_kwargs = app_context.jira.create_issue.call_args[1]
        assert call_kwargs["components"] is None


@pytest.mark.anyio
async def test_call_tool_jira_batch_create_issues(app_context: AppContext) -> None:
    """Test successful batch creation of Jira issues.

    Args:
        app_context: The application context fixture with mocked Jira client.
    """
    # Mock data for testing
    test_issues = [
        {
            "project_key": "TEST",
            "summary": "Test Issue 1",
            "issue_type": "Task",
            "description": "Test description 1",
            "assignee": "test.user@example.com",
            "components": ["Frontend", "API"],
        },
        {
            "project_key": "TEST",
            "summary": "Test Issue 2",
            "issue_type": "Bug",
            "description": "Test description 2",
        },
    ]

    # Configure mock response for batch_create_issues
    mock_created_issues = [
        MagicMock(
            to_simplified_dict=MagicMock(
                return_value={
                    "key": "TEST-1",
                    "summary": "Test Issue 1",
                    "type": "Task",
                    "status": "To Do",
                }
            )
        ),
        MagicMock(
            to_simplified_dict=MagicMock(
                return_value={
                    "key": "TEST-2",
                    "summary": "Test Issue 2",
                    "type": "Bug",
                    "status": "To Do",
                }
            )
        ),
    ]
    app_context.jira.batch_create_issues.return_value = mock_created_issues

    # Test with JSON string input
    with mock_request_context(app_context):
        result = await call_tool(
            "jira_batch_create_issues",
            {"issues": json.dumps(test_issues), "validate_only": False},
        )

    # Verify the result
    assert len(result) == 1
    assert result[0].type == "text"

    # Parse the response JSON
    response = json.loads(result[0].text)
    assert response["message"] == "Issues created successfully"
    assert len(response["issues"]) == 2
    assert response["issues"][0]["key"] == "TEST-1"
    assert response["issues"][1]["key"] == "TEST-2"

    # Verify the mock was called correctly
    app_context.jira.batch_create_issues.assert_called_once_with(
        test_issues, validate_only=False
    )


@pytest.mark.anyio
async def test_call_tool_jira_batch_create_issues_invalid_json(
    app_context: AppContext,
) -> None:
    """Test error handling for invalid JSON input in batch issue creation.

    Args:
        app_context: The application context fixture with mocked Jira client.
    """
    with mock_request_context(app_context):
        result = await call_tool(
            "jira_batch_create_issues",
            {"issues": "{invalid json", "validate_only": False},
        )

        # Verify we got an error response
        assert len(result) == 1
        assert result[0].type == "text"
        assert "Invalid JSON in issues" in result[0].text


@pytest.mark.anyio
async def test_call_tool_jira_get_epic_issues(app_context: AppContext) -> None:
    """Test the jira_get_epic_issues tool correctly processes a list return value.

    Args:
        app_context: The application context fixture with mocked Jira client.
    """
    # Create mock issues to return
    mock_issues = [
        MagicMock(
            to_simplified_dict=MagicMock(
                return_value={
                    "key": "TEST-1",
                    "summary": "Epic Issue 1",
                    "type": "Task",
                    "status": "To Do",
                }
            )
        ),
        MagicMock(
            to_simplified_dict=MagicMock(
                return_value={
                    "key": "TEST-2",
                    "summary": "Epic Issue 2",
                    "type": "Bug",
                    "status": "In Progress",
                }
            )
        ),
    ]

    # Configure mock for get_epic_issues to return a list of issues (not an object with .issues attribute)
    app_context.jira.get_epic_issues.return_value = mock_issues

    # Call the tool
    with mock_request_context(app_context):
        result = await call_tool(
            "jira_get_epic_issues",
            {"epic_key": "TEST-100", "limit": 10, "startAt": 0},
        )

    # Verify the result
    assert len(result) == 1
    assert result[0].type == "text"

    # Parse the response JSON
    response = json.loads(result[0].text)
    assert response["total"] == 2  # Should be the length of the list
    assert response["start_at"] == 0
    assert response["max_results"] == 10
    assert len(response["issues"]) == 2
    assert response["issues"][0]["key"] == "TEST-1"
    assert response["issues"][1]["key"] == "TEST-2"

    # Verify the mock was called correctly
    app_context.jira.get_epic_issues.assert_called_once_with(
        "TEST-100", start=0, limit=10
    )
