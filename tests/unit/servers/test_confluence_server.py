"""Unit tests for the Confluence FastMCP server."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport

from src.mcp_atlassian.confluence import ConfluenceFetcher
from src.mcp_atlassian.models.confluence.page import ConfluencePage
from src.mcp_atlassian.servers.context import MainAppContext


# Fixtures for testing
@pytest.fixture
def mock_confluence_fetcher():
    """Create a mocked ConfluenceFetcher instance for testing."""
    mock_fetcher = MagicMock(spec=ConfluenceFetcher)

    # Mock search method
    mock_page = MagicMock(spec=ConfluencePage)
    mock_page.to_simplified_dict.return_value = {
        "id": "123456",
        "title": "Test Page Mock Title",
        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page",
        "content": {
            "value": "This is a test page content in Markdown",
            "format": "markdown",
        },
    }
    mock_page.content = "This is a test page content in Markdown"
    mock_fetcher.search.return_value = [mock_page]

    # Mock get_page_content method
    mock_fetcher.get_page_content.return_value = mock_page

    # Mock get_page_children method
    mock_fetcher.get_page_children.return_value = [mock_page]

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
    # mock_fetcher.get_page_by_title.return_value = mock_page # Not directly tested via tool

    # Mock get_space_pages method
    # mock_fetcher.get_space_pages.return_value = [mock_page] # Not directly tested via tool

    # Mock get_page_labels method
    mock_label = MagicMock()
    mock_label.to_simplified_dict.return_value = {"id": "lbl1", "name": "test-label"}
    mock_fetcher.get_page_labels.return_value = [mock_label]

    # Mock add_page_label method
    mock_fetcher.add_page_label.return_value = [mock_label]

    return mock_fetcher


@pytest.fixture
def test_confluence_mcp(mock_confluence_fetcher):
    """Create a test FastMCP instance with our mock fetcher."""

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[MainAppContext, None]:
        """Test lifespan that provides our mock fetcher."""
        try:
            yield MainAppContext(confluence=mock_confluence_fetcher, read_only=False)
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
        add_label,
        create_page,
        delete_page,
        get_comments,
        get_labels,
        get_page,  # Renamed from get_page_content
        get_page_children,
        search,
        update_page,
    )

    # Register the tool functions with our test MCP instance
    test_mcp.tool()(search)
    test_mcp.tool(name="get_page")(get_page)  # Explicitly name the tool
    test_mcp.tool()(get_page_children)
    test_mcp.tool()(get_comments)
    test_mcp.tool()(get_labels)
    test_mcp.tool()(add_label)
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
    ) -> AsyncGenerator[MainAppContext, None]:
        """Test lifespan that provides our mock fetcher with read_only=True."""
        try:
            yield MainAppContext(confluence=mock_confluence_fetcher, read_only=True)
        finally:
            pass

    # Create a new FastMCP instance with our read-only test lifespan
    test_mcp = FastMCP(
        "ReadOnlyTestConfluence",
        description="Read-Only Test Confluence MCP Server",
        lifespan=read_only_test_lifespan,
    )

    # Import and register tools as before
    from src.mcp_atlassian.servers.confluence import (
        add_label,
        create_page,
        delete_page,
        get_comments,
        get_labels,
        get_page,
        get_page_children,
        search,
        update_page,
    )

    test_mcp.tool()(search)
    test_mcp.tool(name="get_page")(get_page)
    test_mcp.tool()(get_page_children)
    test_mcp.tool()(get_comments)
    test_mcp.tool()(get_labels)
    test_mcp.tool()(add_label)
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
    ) -> AsyncGenerator[MainAppContext, None]:
        """Test lifespan that provides a context without a fetcher."""
        try:
            yield MainAppContext(confluence=None, read_only=False)
        finally:
            pass

    test_mcp = FastMCP(
        "NoFetcherTestConfluence",
        description="No Fetcher Test Confluence MCP Server",
        lifespan=no_fetcher_test_lifespan,
    )
    # Import and register tools
    from src.mcp_atlassian.servers.confluence import (
        add_label,
        create_page,
        delete_page,
        get_comments,
        get_labels,
        get_page,
        get_page_children,
        search,
        update_page,
    )

    test_mcp.tool()(search)
    test_mcp.tool(name="get_page")(get_page)
    test_mcp.tool()(get_page_children)
    test_mcp.tool()(get_comments)
    test_mcp.tool()(get_labels)
    test_mcp.tool()(add_label)
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
    response = await client.call_tool("search", {"query": "test search"})

    mock_confluence_fetcher.search.assert_called_once()
    args, kwargs = mock_confluence_fetcher.search.call_args
    assert 'siteSearch ~ "test search"' in args[0]

    result_data = json.loads(response[0].text)
    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert result_data[0]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_get_page(client, mock_confluence_fetcher):
    """Test the get_page tool."""
    response = await client.call_tool("get_page", {"page_id": "123456"})

    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=True
    )

    result_data = json.loads(response[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page Mock Title"
    assert "content" in result_data["metadata"]
    assert "value" in result_data["metadata"]["content"]
    assert "This is a test page content" in result_data["metadata"]["content"]["value"]


@pytest.mark.anyio
async def test_get_page_no_metadata(client, mock_confluence_fetcher):
    """Test get_page with include_metadata=False."""
    response = await client.call_tool(
        "get_page", {"page_id": "123456", "include_metadata": False}
    )

    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=True
    )

    result_data = json.loads(response[0].text)
    assert "metadata" not in result_data
    assert "content" in result_data
    assert "This is a test page content" in result_data["content"]


@pytest.mark.anyio
async def test_get_page_no_markdown(client, mock_confluence_fetcher):
    """Test get_page with convert_to_markdown=False."""
    mock_page_html = MagicMock(spec=ConfluencePage)
    mock_page_html.to_simplified_dict.return_value = {
        "id": "123456",
        "title": "Test Page HTML",
        "url": "https://example.com/html",
        "content": "<p>HTML Content</p>",
        "content_format": "storage",
    }
    mock_page_html.content = "<p>HTML Content</p>"
    mock_page_html.content_format = "storage"  # Ensure format is correct

    mock_confluence_fetcher.get_page_content.return_value = mock_page_html

    response = await client.call_tool(
        "get_page", {"page_id": "123456", "convert_to_markdown": False}
    )

    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=False
    )

    result_data = json.loads(response[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page HTML"
    assert result_data["metadata"]["content"] == "<p>HTML Content</p>"
    assert result_data["metadata"]["content_format"] == "storage"


@pytest.mark.anyio
async def test_get_page_children(client, mock_confluence_fetcher):
    """Test the get_page_children tool."""
    response = await client.call_tool("get_page_children", {"parent_id": "123456"})

    mock_confluence_fetcher.get_page_children.assert_called_once()
    call_args = mock_confluence_fetcher.get_page_children.call_args[1]
    assert call_args["page_id"] == "123456"

    result_data = json.loads(response[0].text)
    assert "parent_id" in result_data
    assert "results" in result_data
    assert len(result_data["results"]) > 0
    assert result_data["results"][0]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_get_comments(client, mock_confluence_fetcher):
    """Test the get_comments tool."""
    response = await client.call_tool("get_comments", {"page_id": "123456"})

    mock_confluence_fetcher.get_page_comments.assert_called_once_with("123456")

    result_data = json.loads(response[0].text)
    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert result_data[0]["author"] == "Test User"


@pytest.mark.anyio
async def test_get_labels(client, mock_confluence_fetcher):
    """Test the get_labels tool."""
    response = await client.call_tool("get_labels", {"page_id": "123456"})
    mock_confluence_fetcher.get_page_labels.assert_called_once_with("123456")
    result_data = json.loads(response[0].text)
    assert isinstance(result_data, list)
    assert result_data[0]["name"] == "test-label"


@pytest.mark.anyio
async def test_add_label(client, mock_confluence_fetcher):
    """Test the add_label tool."""
    response = await client.call_tool(
        "add_label", {"page_id": "123456", "name": "new-label"}
    )
    mock_confluence_fetcher.add_page_label.assert_called_once_with(
        "123456", "new-label"
    )
    result_data = json.loads(response[0].text)
    assert isinstance(result_data, list)
    assert result_data[0]["name"] == "test-label"  # Mock returns the same label


@pytest.mark.anyio
async def test_create_page(client, mock_confluence_fetcher):
    """Test the create_page tool."""
    response = await client.call_tool(
        "create_page",
        {
            "space_key": "TEST",
            "title": "New Test Page",
            "content": "# New Page\nContent here.",
        },
    )

    mock_confluence_fetcher.create_page.assert_called_once_with(
        space_key="TEST",
        title="New Test Page",
        body="# New Page\nContent here.",
        parent_id=None,
        is_markdown=True,
    )

    result_data = json.loads(response[0].text)
    assert result_data["message"] == "Page created successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"  # Corrected assertion


@pytest.mark.anyio
async def test_update_page(client, mock_confluence_fetcher):
    """Test the update_page tool."""
    response = await client.call_tool(
        "update_page",
        {
            "page_id": "123456",
            "title": "Updated Page",
            "content": "## Updated Content",
        },
    )

    mock_confluence_fetcher.update_page.assert_called_once_with(
        page_id="123456",
        title="Updated Page",
        body="## Updated Content",
        is_minor_edit=False,
        version_comment="",
        is_markdown=True,
        parent_id=None,
    )

    result_data = json.loads(response[0].text)
    assert result_data["message"] == "Page updated successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"  # Corrected assertion


@pytest.mark.anyio
async def test_delete_page(client, mock_confluence_fetcher):
    """Test the delete_page tool."""
    response = await client.call_tool("delete_page", {"page_id": "123456"})

    mock_confluence_fetcher.delete_page.assert_called_once_with(page_id="123456")

    result_data = json.loads(response[0].text)
    assert result_data["success"] is True


@pytest.mark.anyio
async def test_read_only_mode_create_page(read_only_client, mock_confluence_fetcher):
    """Test create_page is blocked in read-only mode."""
    with pytest.raises(Exception) as excinfo:
        await read_only_client.call_tool(
            "create_page",
            {
                "space_key": "TEST",
                "title": "New Test Page",
                "content": "# New Page",
            },
        )
    assert "read-only mode" in str(excinfo.value)
    mock_confluence_fetcher.create_page.assert_not_called()


@pytest.mark.anyio
async def test_read_only_mode_update_page(read_only_client, mock_confluence_fetcher):
    """Test update_page is blocked in read-only mode."""
    with pytest.raises(Exception) as excinfo:
        await read_only_client.call_tool(
            "update_page",
            {
                "page_id": "123",
                "title": "Updated",
                "content": "Updated content",
            },
        )
    assert "read-only mode" in str(excinfo.value)
    mock_confluence_fetcher.update_page.assert_not_called()


@pytest.mark.anyio
async def test_read_only_mode_delete_page(read_only_client, mock_confluence_fetcher):
    """Test delete_page is blocked in read-only mode."""
    with pytest.raises(Exception) as excinfo:
        await read_only_client.call_tool("delete_page", {"page_id": "123"})
    assert "read-only mode" in str(excinfo.value)
    mock_confluence_fetcher.delete_page.assert_not_called()


@pytest.mark.anyio
async def test_missing_credentials_error(no_fetcher_client):
    """Test error handling when Confluence fetcher is not available."""
    with pytest.raises(Exception) as excinfo:
        await no_fetcher_client.call_tool("search", {"query": "test"})
    assert "Confluence client is not configured or available" in str(excinfo.value)


@pytest.mark.anyio
async def test_invalid_arguments(client):
    """Test error handling with invalid arguments."""
    with pytest.raises(Exception) as excinfo:
        await client.call_tool("get_page", {})  # Missing page_id
    error_msg = str(excinfo.value).lower()
    assert "validation error" in error_msg or "missing" in error_msg


@pytest.mark.anyio
async def test_api_error_handling_delete(client, mock_confluence_fetcher):
    """Test error handling when the fetcher method raises an API error."""
    api_error_msg = "Confluence API Error: 500 Internal Server Error"
    mock_confluence_fetcher.delete_page.side_effect = Exception(api_error_msg)

    response = await client.call_tool("delete_page", {"page_id": "123"})

    result_data = json.loads(response[0].text)
    assert result_data["success"] is False
    assert "Error deleting page" in result_data["message"]
    assert api_error_msg in result_data["error"]
