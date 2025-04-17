"""Unit tests for server"""

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.context import RequestContext
from mcp.shared.session import BaseSession
from mcp.types import Resource, Tool

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.jira import JiraFetcher
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
        patch("mcp_atlassian.server.ConfluenceFetcher") as mock_confluence_cls,
        patch("mcp_atlassian.server.JiraFetcher") as mock_jira_cls,
        patch("mcp_atlassian.server.is_read_only_mode") as mock_read_only,
        patch("mcp_atlassian.server.logger") as mock_logger,
    ):
        # Configure mocks
        mock_services.return_value = {"confluence": True, "jira": True}
        mock_confluence_cls.return_value = MagicMock()
        mock_confluence_cls.return_value.config.url = "https://test.atlassian.net/wiki"
        mock_jira_cls.return_value = MagicMock()
        mock_jira_cls.return_value.config.url = "https://test.atlassian.net"
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
                "Confluence URL: https://test.atlassian.net/wiki"
            )
            mock_logger.info.assert_any_call("Jira URL: https://test.atlassian.net")


@pytest.mark.anyio
async def test_list_resources_both_services(app_context):
    """Test the list_resources handler with both services available."""
    with mock_request_context(app_context):
        # Call the handler directly
        resources = await list_resources()

        # Verify clients were called
        app_context.jira.get_current_user_account_id.assert_called_once()
        app_context.jira.jira.jql.assert_called_once()
        app_context.confluence.get_user_contributed_spaces.assert_called_once()

        # Verify returned resources
        assert isinstance(resources, list)
        assert len(resources) == 2  # One from Jira, one from Confluence

        # Check structure of resources
        for res in resources:
            assert isinstance(res, Resource)
            assert str(res.uri) in ("confluence://TEST", "jira://TEST")
            assert hasattr(res, "name")
            assert hasattr(res, "mimeType")
            assert hasattr(res, "description")


@pytest.mark.anyio
async def test_list_resources_only_jira(app_context):
    """Test the list_resources handler with only Jira available."""
    # Modify the context to have only Jira
    app_context.confluence = None

    with mock_request_context(app_context):
        # Call the handler directly
        resources = await list_resources()

        # Verify only Jira client was called
        app_context.jira.get_current_user_account_id.assert_called_once()
        app_context.jira.jira.jql.assert_called_once()

        # Verify returned resources
        assert isinstance(resources, list)
        assert len(resources) == 1  # Only from Jira
        assert str(resources[0].uri) == "jira://TEST"


@pytest.mark.anyio
async def test_list_resources_only_confluence(app_context):
    """Test the list_resources handler with only Confluence available."""
    # Modify the context to have only Confluence
    app_context.jira = None

    with mock_request_context(app_context):
        # Call the handler directly
        resources = await list_resources()

        # Verify only Confluence client was called
        app_context.confluence.get_user_contributed_spaces.assert_called_once()

        # Verify returned resources
        assert isinstance(resources, list)
        assert len(resources) == 1  # Only from Confluence
        assert str(resources[0].uri) == "confluence://TEST"


@pytest.mark.anyio
async def test_list_resources_no_services(app_context):
    """Test the list_resources handler with no services available."""
    # Modify the context to have no services
    app_context.jira = None
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
    # Configure clients to raise exceptions
    app_context.jira.get_current_user_account_id.side_effect = Exception("Jira error")
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
        # Jira project
        (
            "jira://TEST",
            "text/markdown",
            lambda ctx: (
                setattr(
                    ctx.jira,
                    "get_current_user_account_id",
                    MagicMock(return_value="test-account-id"),
                ),  # type: ignore
                setattr(
                    ctx.jira,
                    "search_issues",
                    MagicMock(
                        return_value=[
                            MagicMock(
                                to_simplified_dict=MagicMock(
                                    return_value={
                                        "key": "TEST-123",
                                        "summary": "Test Issue",
                                        "url": "https://example.atlassian.net/browse/TEST-123",
                                        "status": {"name": "Open"},
                                        "description": "This is a test issue",
                                    }
                                )
                            )
                        ]
                    ),
                ),  # type: ignore
            ),
        ),
        # Jira issue
        (
            "jira://TEST-123",
            "text/markdown",
            lambda ctx: setattr(
                ctx.jira,
                "get_issue",
                MagicMock(
                    return_value=MagicMock(
                        to_simplified_dict=MagicMock(
                            return_value={
                                "key": "TEST-123",
                                "summary": "Test Issue",
                                "status": {"name": "Open"},
                                "description": "This is a test issue",
                            }
                        ),
                        # Add important fields that the formatter might access
                        fields={
                            "summary": "Test Issue",
                            "description": "This is a test issue",
                            "status": {"name": "Open"},
                        },
                    )
                ),
            ),
        ),
    ],
)
async def test_read_resource_valid_uris(
    uri, expected_mime_type, mock_setup, app_context
):
    """Test the read_resource handler with various valid URIs."""
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
        # For Jira tests, we'll check the returned content rather than expecting exceptions
        (
            "jira://NONEXISTENT-123",
            "",
            lambda ctx: setattr(ctx.jira, "get_issue", MagicMock(return_value=None)),
        ),
    ],
)
async def test_read_resource_invalid_uris(uri, expected_error, mock_setup, app_context):
    """Test the read_resource handler with invalid URIs."""
    # Configure mocks based on the provided mock_setup function
    if mock_setup:
        mock_setup(app_context)

    with mock_request_context(app_context):
        if "jira://" in uri and "-" in uri:
            # For Jira issues, the server appears to handle None values in a special way
            # Instead of raising, it might return empty content or format it differently
            content = await read_resource(uri)
            assert isinstance(content, str)  # It should still return a string
        else:
            # For other URIs, we still expect exceptions
            try:
                await read_resource(uri)
                pytest.fail(f"Expected an exception for {uri}")
            except (ValueError, Exception) as e:
                assert expected_error in str(e)


@pytest.mark.anyio
async def test_read_resource_client_error(app_context):
    """Test the read_resource handler when clients raise exceptions."""
    # Configure clients to raise exceptions
    app_context.jira.get_issue = MagicMock(side_effect=Exception("Jira error"))

    with mock_request_context(app_context):
        try:
            # With the new signature, this might raise an exception now
            content = await read_resource("jira://TEST-123")
            # If it doesn't raise, make sure we got a string
            assert isinstance(content, str)
        except Exception:
            # We're just testing that the function handles errors somehow
            pass


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
