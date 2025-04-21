"""Unit tests for the Confluence FastMCP server."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport

from src.mcp_atlassian.confluence import ConfluenceFetcher
from src.mcp_atlassian.models.confluence.page import ConfluencePage


# Fixtures for testing
@pytest.fixture
def mock_confluence_fetcher():
    """Create a mocked ConfluenceFetcher instance for testing."""
    mock_fetcher = MagicMock(spec=ConfluenceFetcher)

    # Mock search method
    mock_page = MagicMock(spec=ConfluencePage)
    mock_page.to_simplified_dict.return_value = {
        "id": "123456",
        "title": "Test Page",
        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page",
        "content": "This is a test page",
    }
    mock_page.content = "This is a test page content"
    mock_fetcher.search.return_value = [mock_page]

    # Mock get_page_content method
    mock_fetcher.get_page_content.return_value = mock_page

    # Mock get_page_children method
    mock_fetcher.get_page_children.return_value = [mock_page]

    # Mock get_page_ancestors method
    mock_fetcher.get_page_ancestors.return_value = [mock_page]

    # Mock get_page_comments method
    mock_comment = MagicMock()
    mock_comment.to_simplified_dict.return_value = {
        "id": "789",
        "author": "Test User",
        "created": "2023-08-01T12:00:00.000Z",
        "body": "This is a test comment",
    }
    mock_fetcher.get_page_comments.return_value = [mock_comment]

    # Mock create_page method
    mock_fetcher.create_page.return_value = mock_page

    # Mock update_page method
    mock_fetcher.update_page.return_value = mock_page

    # Mock delete_page method
    mock_fetcher.delete_page.return_value = True

    # Mock get_page_by_title method
    mock_fetcher.get_page_by_title.return_value = mock_page

    # Mock get_space_pages method
    mock_fetcher.get_space_pages.return_value = [mock_page]

    return mock_fetcher


@pytest.fixture
def test_confluence_mcp(mock_confluence_fetcher):
    """Create a test FastMCP instance with our mock fetcher."""

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
        """Test lifespan that provides our mock fetcher."""
        try:
            yield {"confluence_fetcher": mock_confluence_fetcher, "read_only": False}
        finally:
            pass

    # Create a new FastMCP instance with our test lifespan
    test_mcp = FastMCP(
        "TestConfluence",
        description="Test Confluence MCP Server",
        lifespan=test_lifespan,
    )

    # Import the tool functions we want to test
    from src.mcp_atlassian.servers.confluence import (
        create_page,
        delete_page,
        get_comments,
        get_page,
        get_page_ancestors,
        get_page_children,
        search,
        update_page,
    )

    # Register the tool functions with our test MCP instance
    test_mcp.tool()(search)
    test_mcp.tool()(get_page)
    test_mcp.tool()(get_page_children)
    test_mcp.tool()(get_page_ancestors)
    test_mcp.tool()(get_comments)
    test_mcp.tool()(create_page)
    test_mcp.tool()(update_page)
    test_mcp.tool()(delete_page)

    return test_mcp


@pytest.fixture
def read_only_test_confluence_mcp(mock_confluence_fetcher):
    """Create a test FastMCP instance with read_only=True."""

    @asynccontextmanager
    async def read_only_test_lifespan(
        app: FastMCP,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Test lifespan that provides our mock fetcher with read_only=True."""
        try:
            yield {"confluence_fetcher": mock_confluence_fetcher, "read_only": True}
        finally:
            pass

    # Create a new FastMCP instance with our read-only test lifespan
    test_mcp = FastMCP(
        "ReadOnlyTestConfluence",
        description="Read-Only Test Confluence MCP Server",
        lifespan=read_only_test_lifespan,
    )

    # Import the tool functions we want to test
    from src.mcp_atlassian.servers.confluence import (
        create_page,
        delete_page,
        get_comments,
        get_page,
        get_page_ancestors,
        get_page_children,
        search,
        update_page,
    )

    # Register the tool functions with our test MCP instance
    test_mcp.tool()(search)
    test_mcp.tool()(get_page)
    test_mcp.tool()(get_page_children)
    test_mcp.tool()(get_page_ancestors)
    test_mcp.tool()(get_comments)
    test_mcp.tool()(create_page)
    test_mcp.tool()(update_page)
    test_mcp.tool()(delete_page)

    return test_mcp


@pytest.fixture
def no_fetcher_test_confluence_mcp():
    """Create a test FastMCP instance with no confluence_fetcher in context."""

    @asynccontextmanager
    async def no_fetcher_test_lifespan(
        app: FastMCP,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Test lifespan that provides a context without a fetcher."""
        try:
            yield {"confluence_fetcher": None, "read_only": False}
        finally:
            pass

    # Create a new FastMCP instance with our no-fetcher test lifespan
    test_mcp = FastMCP(
        "NoFetcherTestConfluence",
        description="No Fetcher Test Confluence MCP Server",
        lifespan=no_fetcher_test_lifespan,
    )

    # Import the tool functions we want to test
    from src.mcp_atlassian.servers.confluence import (
        create_page,
        delete_page,
        get_comments,
        get_page,
        get_page_ancestors,
        get_page_children,
        search,
        update_page,
    )

    # Register the tool functions with our test MCP instance
    test_mcp.tool()(search)
    test_mcp.tool()(get_page)
    test_mcp.tool()(get_page_children)
    test_mcp.tool()(get_page_ancestors)
    test_mcp.tool()(get_comments)
    test_mcp.tool()(create_page)
    test_mcp.tool()(update_page)
    test_mcp.tool()(delete_page)

    return test_mcp


@pytest.fixture
async def client(test_confluence_mcp):
    """Create a FastMCP client for testing."""
    client = Client(transport=FastMCPTransport(test_confluence_mcp))
    async with client as connected_client:
        yield connected_client


@pytest.fixture
async def read_only_client(read_only_test_confluence_mcp):
    """Create a FastMCP client in read-only mode for testing."""
    client = Client(transport=FastMCPTransport(read_only_test_confluence_mcp))
    async with client as connected_client:
        yield connected_client


@pytest.fixture
async def no_fetcher_client(no_fetcher_test_confluence_mcp):
    """Create a client with no confluence_fetcher in context."""
    client = Client(transport=FastMCPTransport(no_fetcher_test_confluence_mcp))
    async with client as connected_client:
        yield connected_client


@pytest.mark.anyio
async def test_search(client, mock_confluence_fetcher):
    """Test the search tool."""
    # Call the tool
    result = await client.call_tool("search", {"query": "test search"})

    # Verify the mock was called correctly
    mock_confluence_fetcher.search.assert_called_once()

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert "title" in result_data[0]
    assert result_data[0]["title"] == "Test Page"


@pytest.mark.anyio
async def test_get_page(client, mock_confluence_fetcher):
    """Test the get_page tool."""
    # Call the tool
    result = await client.call_tool("get_page", {"page_id": "123456"})

    # Verify the mock was called correctly
    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=True
    )

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page"


@pytest.mark.anyio
async def test_get_page_children(client, mock_confluence_fetcher):
    """Test the get_page_children tool."""
    # Call the tool
    result = await client.call_tool("get_page_children", {"parent_id": "123456"})

    # Verify the mock was called correctly
    mock_confluence_fetcher.get_page_children.assert_called_once()

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert "parent_id" in result_data
    assert "results" in result_data
    assert len(result_data["results"]) > 0
    assert result_data["results"][0]["title"] == "Test Page"


@pytest.mark.anyio
async def test_get_page_ancestors(client, mock_confluence_fetcher):
    """Test the get_page_ancestors tool."""
    # Call the tool
    result = await client.call_tool("get_page_ancestors", {"page_id": "123456"})

    # Verify the mock was called correctly
    mock_confluence_fetcher.get_page_ancestors.assert_called_once_with("123456")

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert result_data[0]["title"] == "Test Page"


@pytest.mark.anyio
async def test_get_comments(client, mock_confluence_fetcher):
    """Test the get_comments tool."""
    # Call the tool
    result = await client.call_tool("get_comments", {"page_id": "123456"})

    # Verify the mock was called correctly
    mock_confluence_fetcher.get_page_comments.assert_called_once_with("123456")

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert "author" in result_data[0]
    assert result_data[0]["author"] == "Test User"


@pytest.mark.anyio
async def test_create_page(client, mock_confluence_fetcher):
    """Test the create_page tool."""
    # Call the tool
    result = await client.call_tool(
        "create_page",
        {
            "space_key": "TEST",
            "title": "New Test Page",
            "content": "# New Test Page\n\nThis is a test page content.",
        },
    )

    # Verify the mock was called correctly
    mock_confluence_fetcher.create_page.assert_called_once_with(
        space_key="TEST",
        title="New Test Page",
        body="# New Test Page\n\nThis is a test page content.",
        parent_id=None,
        is_markdown=True,
    )

    # Check the result
    assert "Page created successfully" in result[0].text


@pytest.mark.anyio
async def test_update_page(client, mock_confluence_fetcher):
    """Test the update_page tool."""
    # Call the tool
    result = await client.call_tool(
        "update_page",
        {
            "page_id": "123456",
            "title": "Updated Test Page",
            "content": "# Updated Test Page\n\nThis is updated content.",
        },
    )

    # Verify the mock was called correctly
    mock_confluence_fetcher.update_page.assert_called_once_with(
        page_id="123456",
        title="Updated Test Page",
        body="# Updated Test Page\n\nThis is updated content.",
        is_minor_edit=False,
        version_comment="",
        is_markdown=True,
        parent_id=None,
    )

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert "page" in result_data


@pytest.mark.anyio
async def test_delete_page(client, mock_confluence_fetcher):
    """Test the delete_page tool."""
    # Call the tool
    result = await client.call_tool("delete_page", {"page_id": "123456"})

    # Verify the mock was called correctly
    mock_confluence_fetcher.delete_page.assert_called_once_with(page_id="123456")

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert result_data["success"] is True
    assert "Page 123456 deleted successfully" in result_data["message"]


@pytest.mark.anyio
async def test_search_simple_term_uses_sitesearch(client, mock_confluence_fetcher):
    """Test that a simple search term is converted to a siteSearch CQL query."""
    # Reset the mock to clear call history
    mock_confluence_fetcher.search.reset_mock()

    # Call the tool
    await client.call_tool("search", {"query": "simple term"})

    # Verify the call to search used siteSearch
    mock_confluence_fetcher.search.assert_called_once()
    args, kwargs = mock_confluence_fetcher.search.call_args
    assert args[0] == 'siteSearch ~ "simple term"'


@pytest.mark.anyio
async def test_search_fallback_to_text_search(client, mock_confluence_fetcher):
    """Test fallback to text search when siteSearch fails."""
    # Reset the mock to clear call history
    mock_confluence_fetcher.search.reset_mock()

    # Create a proper mock page that can be serialized
    mock_page = MagicMock(spec=ConfluencePage)
    mock_page.to_simplified_dict.return_value = {
        "id": "123456",
        "title": "Fallback Search Result",
        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page",
        "content": "This is a fallback search result",
    }

    # Configure the mock to fail on first call, then succeed on second call
    mock_confluence_fetcher.search.side_effect = [
        Exception("siteSearch not available"),  # First call fails
        [mock_page],  # Second call succeeds with a proper mock
    ]

    # Call the tool
    result = await client.call_tool("search", {"query": "simple term"})

    # Verify the mock was called twice
    assert mock_confluence_fetcher.search.call_count == 2

    # Check first call was with siteSearch CQL
    first_call_args, _ = mock_confluence_fetcher.search.call_args_list[0]
    assert "siteSearch ~" in first_call_args[0]

    # Check second call was with text CQL
    second_call_args, _ = mock_confluence_fetcher.search.call_args_list[1]
    assert "text ~" in second_call_args[0]

    # Parse the result and check it
    result_text = result[0].text
    result_data = json.loads(result_text)

    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert result_data[0]["title"] == "Fallback Search Result"


@pytest.mark.anyio
async def test_search_direct_cql_not_modified(client, mock_confluence_fetcher):
    """Test that a CQL query is not modified."""
    # Reset the mock to clear call history
    mock_confluence_fetcher.search.reset_mock()

    # Define a CQL query
    cql_query = 'space = DEV AND title ~ "Meeting"'

    # Call the tool
    await client.call_tool("search", {"query": cql_query})

    # Verify the query was passed unmodified
    mock_confluence_fetcher.search.assert_called_once()
    args, kwargs = mock_confluence_fetcher.search.call_args
    assert args[0] == cql_query


@pytest.mark.anyio
async def test_read_only_mode_create_page(read_only_client, mock_confluence_fetcher):
    """Test that write operations are not allowed in read-only mode."""
    # Call the create page tool which should be blocked in read-only mode
    result = await read_only_client.call_tool(
        "create_page",
        {
            "space_key": "TEST",
            "title": "New Test Page",
            "content": "# New Test Page\n\nThis is a test page content.",
        },
    )

    # Verify create_page was not called
    mock_confluence_fetcher.create_page.assert_not_called()

    # Verify the response indicates the operation is not available
    assert "not available in read-only mode" in result[0].text


@pytest.mark.anyio
async def test_read_only_mode_update_page(read_only_client, mock_confluence_fetcher):
    """Test that update operations are not allowed in read-only mode."""
    # Call the update page tool which should be blocked in read-only mode
    result = await read_only_client.call_tool(
        "update_page",
        {
            "page_id": "123456",
            "title": "Updated Test Page",
            "content": "# Updated Test Page\n\nThis is updated content.",
        },
    )

    # Verify update_page was not called
    mock_confluence_fetcher.update_page.assert_not_called()

    # Verify the response indicates the operation is not available
    assert "not available in read-only mode" in result[0].text


@pytest.mark.anyio
async def test_read_only_mode_delete_page(read_only_client, mock_confluence_fetcher):
    """Test that delete operations are not allowed in read-only mode."""
    # Call the delete page tool which should be blocked in read-only mode
    result = await read_only_client.call_tool("delete_page", {"page_id": "123456"})

    # Verify delete_page was not called
    mock_confluence_fetcher.delete_page.assert_not_called()

    # Verify the response indicates the operation is not available
    assert "not available in read-only mode" in result[0].text


@pytest.mark.anyio
async def test_missing_credentials_error(no_fetcher_client):
    """Test error handling when Confluence fetcher is not available."""
    # Try to call a tool
    with pytest.raises(Exception) as excinfo:
        await no_fetcher_client.call_tool("search", {"query": "test"})

    # Should raise an error with message about Confluence not being configured
    assert "Confluence is not configured" in str(excinfo.value)


@pytest.mark.anyio
async def test_invalid_arguments(client):
    """Test error handling with invalid arguments."""
    # Try to call get_page without the required page_id parameter
    with pytest.raises(Exception) as excinfo:
        await client.call_tool("get_page", {})

    # Check error message contains expected text
    error_msg = str(excinfo.value).lower()
    assert (
        "field required" in error_msg
        or "missing" in error_msg
        or "required parameter" in error_msg
    )


@pytest.mark.anyio
async def test_api_error_handling(client, mock_confluence_fetcher):
    """Test error handling for API errors in tool calls."""
    # Reset the mock to clear call history
    mock_confluence_fetcher.delete_page.reset_mock()

    # Configure the mock to raise an Exception for delete_page
    error_msg = "API Error: Internal Server Error"
    mock_confluence_fetcher.delete_page.side_effect = Exception(error_msg)

    # Call the delete_page tool which should handle the error
    result = await client.call_tool("delete_page", {"page_id": "123456"})

    # Parse the result
    result_text = result[0].text
    result_data = json.loads(result_text)

    # Should return a formatted error response
    assert result_data["success"] is False
    assert "Error deleting page" in result_data["message"]
    assert error_msg in result_data["error"]
