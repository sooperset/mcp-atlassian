"""Unit tests for the Confluence FastMCP server."""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport
from starlette.requests import Request

from src.mcp_atlassian.confluence import ConfluenceFetcher
from src.mcp_atlassian.confluence.config import ConfluenceConfig
from src.mcp_atlassian.models.confluence.page import ConfluencePage
from src.mcp_atlassian.servers.context import MainAppContext
from src.mcp_atlassian.servers.main import AtlassianMCP
from src.mcp_atlassian.utils.oauth import OAuthConfig

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_confluence_fetcher():
    """Create a mocked ConfluenceFetcher instance for testing."""
    mock_fetcher = MagicMock(spec=ConfluenceFetcher)

    # Mock page for various methods
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

    # Set up mock responses for each method
    mock_fetcher.search.return_value = [mock_page]
    mock_fetcher.get_page_content.return_value = mock_page
    mock_fetcher.get_page_children.return_value = [mock_page]
    mock_fetcher.create_page.return_value = mock_page
    mock_fetcher.update_page.return_value = mock_page
    mock_fetcher.delete_page.return_value = True

    # Mock comment
    mock_comment = MagicMock()
    mock_comment.to_simplified_dict.return_value = {
        "id": "789",
        "author": "Test User",
        "created": "2023-08-01T12:00:00.000Z",
        "body": "This is a test comment",
    }
    mock_fetcher.get_page_comments.return_value = [mock_comment]

    # Mock label
    mock_label = MagicMock()
    mock_label.to_simplified_dict.return_value = {"id": "lbl1", "name": "test-label"}
    mock_fetcher.get_page_labels.return_value = [mock_label]
    mock_fetcher.add_page_label.return_value = [mock_label]

    # Mock add_comment method
    mock_comment = MagicMock()
    mock_comment.to_simplified_dict.return_value = {
        "id": "987",
        "author": "Test User",
        "created": "2023-08-01T13:00:00.000Z",
        "body": "This is a test comment added via API",
    }
    mock_fetcher.add_comment.return_value = mock_comment

    # Mock search_user method
    mock_user_search_result = MagicMock()
    mock_user_search_result.to_simplified_dict.return_value = {
        "entity_type": "user",
        "title": "First Last",
        "score": 0.0,
        "user": {
            "account_id": "a031248587011jasoidf9832jd8j1",
            "display_name": "First Last",
            "email": "first.last@foo.com",
            "profile_picture": "/wiki/aa-avatar/a031248587011jasoidf9832jd8j1",
            "is_active": True,
        },
        "url": "/people/a031248587011jasoidf9832jd8j1",
        "last_modified": "2025-06-02T13:35:59.680Z",
        "excerpt": "",
    }
    mock_fetcher.search_user.return_value = [mock_user_search_result]

    return mock_fetcher


@pytest.fixture
def mock_base_confluence_config():
    """Create a mock base ConfluenceConfig for MainAppContext using OAuth for multi-user scenario."""
    mock_oauth_config = OAuthConfig(
        client_id="server_client_id",
        client_secret="server_client_secret",
        redirect_uri="http://localhost",
        scope="read:confluence",
        cloud_id="mock_cloud_id",
    )
    return ConfluenceConfig(
        url="https://mock.atlassian.net/wiki",
        auth_type="oauth",
        oauth_config=mock_oauth_config,
    )


@pytest.fixture
def test_confluence_mcp(mock_confluence_fetcher, mock_base_confluence_config):
    """Create a test FastMCP instance with standard configuration."""

    # Import and register tool functions (as they are in confluence.py)
    from src.mcp_atlassian.servers.confluence import (
        add_comment,
        add_label,
        create_page,
        delete_page,
        get_comments,
        get_labels,
        get_page,
        get_page_children,
        search,
        search_user,
        update_page,
    )

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[MainAppContext, None]:
        try:
            yield MainAppContext(
                full_confluence_config=mock_base_confluence_config, read_only=False
            )
        finally:
            pass

    test_mcp = AtlassianMCP(
        "TestConfluence",
        instructions="Test Confluence MCP Server",
        lifespan=test_lifespan,
    )

    # Create and configure the sub-MCP for Confluence tools
    confluence_sub_mcp = FastMCP(name="TestConfluenceSubMCP")
    confluence_sub_mcp.add_tool(search)
    confluence_sub_mcp.add_tool(get_page)
    confluence_sub_mcp.add_tool(get_page_children)
    confluence_sub_mcp.add_tool(get_comments)
    confluence_sub_mcp.add_tool(add_comment)
    confluence_sub_mcp.add_tool(get_labels)
    confluence_sub_mcp.add_tool(add_label)
    confluence_sub_mcp.add_tool(create_page)
    confluence_sub_mcp.add_tool(update_page)
    confluence_sub_mcp.add_tool(delete_page)
    confluence_sub_mcp.add_tool(search_user)

    test_mcp.mount(confluence_sub_mcp, prefix="confluence")

    return test_mcp


@pytest.fixture
def no_fetcher_test_confluence_mcp(mock_base_confluence_config):
    """Create a test FastMCP instance that simulates missing Confluence fetcher."""

    # Import and register tool functions (as they are in confluence.py)
    from src.mcp_atlassian.servers.confluence import (
        add_comment,
        add_label,
        create_page,
        delete_page,
        get_comments,
        get_labels,
        get_page,
        get_page_children,
        search,
        search_user,
        update_page,
    )

    @asynccontextmanager
    async def no_fetcher_test_lifespan(
        app: FastMCP,
    ) -> AsyncGenerator[MainAppContext, None]:
        try:
            yield MainAppContext(
                full_confluence_config=mock_base_confluence_config, read_only=False
            )
        finally:
            pass

    test_mcp = AtlassianMCP(
        "NoFetcherTestConfluence",
        instructions="No Fetcher Test Confluence MCP Server",
        lifespan=no_fetcher_test_lifespan,
    )

    # Create and configure the sub-MCP for Confluence tools
    confluence_sub_mcp = FastMCP(name="NoFetcherTestConfluenceSubMCP")
    confluence_sub_mcp.add_tool(search)
    confluence_sub_mcp.add_tool(get_page)
    confluence_sub_mcp.add_tool(get_page_children)
    confluence_sub_mcp.add_tool(get_comments)
    confluence_sub_mcp.add_tool(add_comment)
    confluence_sub_mcp.add_tool(get_labels)
    confluence_sub_mcp.add_tool(add_label)
    confluence_sub_mcp.add_tool(create_page)
    confluence_sub_mcp.add_tool(update_page)
    confluence_sub_mcp.add_tool(delete_page)
    confluence_sub_mcp.add_tool(search_user)

    test_mcp.mount(confluence_sub_mcp, prefix="confluence")

    return test_mcp


@pytest.fixture
def mock_request():
    """Provides a mock Starlette Request object with a state."""
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    return request


@pytest.fixture
async def client(test_confluence_mcp, mock_confluence_fetcher):
    """Create a FastMCP client with mocked Confluence fetcher and request state."""
    with (
        patch(
            "src.mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_confluence_fetcher),
        ),
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            MagicMock(spec=Request, state=MagicMock()),
        ),
    ):
        client_instance = Client(transport=FastMCPTransport(test_confluence_mcp))
        async with client_instance as connected_client:
            yield connected_client


@pytest.fixture
async def no_fetcher_client_fixture(no_fetcher_test_confluence_mcp, mock_request):
    """Create a client that simulates missing Confluence fetcher configuration."""
    client_for_no_fetcher_test = Client(
        transport=FastMCPTransport(no_fetcher_test_confluence_mcp)
    )
    async with client_for_no_fetcher_test as connected_client_for_no_fetcher:
        yield connected_client_for_no_fetcher


@pytest.mark.anyio
async def test_search(client, mock_confluence_fetcher):
    """Test the search tool with basic query."""
    response = await client.call_tool("confluence_search", {"query": "test search"})

    mock_confluence_fetcher.search.assert_called_once()
    args, kwargs = mock_confluence_fetcher.search.call_args
    assert 'siteSearch ~ "test search"' in args[0]
    assert kwargs.get("limit") == 10
    assert kwargs.get("spaces_filter") is None

    result_data = json.loads(response.content[0].text)
    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert result_data[0]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_get_page(client, mock_confluence_fetcher):
    """Test the get_page tool with default parameters."""
    response = await client.call_tool("confluence_get_page", {"page_id": "123456"})

    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=True
    )

    result_data = json.loads(response.content[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page Mock Title"
    assert "content" in result_data["metadata"]
    assert "value" in result_data["metadata"]["content"]
    assert "This is a test page content" in result_data["metadata"]["content"]["value"]


@pytest.mark.anyio
async def test_get_page_no_metadata(client, mock_confluence_fetcher):
    """Test get_page with metadata disabled."""
    response = await client.call_tool(
        "confluence_get_page", {"page_id": "123456", "include_metadata": False}
    )

    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=True
    )

    result_data = json.loads(response.content[0].text)
    assert "metadata" not in result_data
    assert "content" in result_data
    assert "This is a test page content" in result_data["content"]["value"]


@pytest.mark.anyio
async def test_get_page_no_markdown(client, mock_confluence_fetcher):
    """Test get_page with HTML content format."""
    mock_page_html = MagicMock(spec=ConfluencePage)
    mock_page_html.to_simplified_dict.return_value = {
        "id": "123456",
        "title": "Test Page HTML",
        "url": "https://example.com/html",
        "content": "<p>HTML Content</p>",
        "content_format": "storage",
    }
    mock_page_html.content = "<p>HTML Content</p>"
    mock_page_html.content_format = "storage"

    mock_confluence_fetcher.get_page_content.return_value = mock_page_html

    response = await client.call_tool(
        "confluence_get_page", {"page_id": "123456", "convert_to_markdown": False}
    )

    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=False
    )

    result_data = json.loads(response.content[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page HTML"
    assert result_data["metadata"]["content"] == "<p>HTML Content</p>"
    assert result_data["metadata"]["content_format"] == "storage"


@pytest.mark.anyio
async def test_get_page_children(client, mock_confluence_fetcher):
    """Test the get_page_children tool."""
    response = await client.call_tool(
        "confluence_get_page_children", {"parent_id": "123456"}
    )

    mock_confluence_fetcher.get_page_children.assert_called_once()
    call_kwargs = mock_confluence_fetcher.get_page_children.call_args.kwargs
    assert call_kwargs["page_id"] == "123456"
    assert call_kwargs.get("start") == 0
    assert call_kwargs.get("limit") == 25
    assert call_kwargs.get("expand") == "version"

    result_data = json.loads(response.content[0].text)
    assert "parent_id" in result_data
    assert "results" in result_data
    assert len(result_data["results"]) > 0
    assert result_data["results"][0]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_get_comments(client, mock_confluence_fetcher):
    """Test retrieving page comments."""
    response = await client.call_tool("confluence_get_comments", {"page_id": "123456"})

    mock_confluence_fetcher.get_page_comments.assert_called_once_with("123456")

    result_data = json.loads(response.content[0].text)
    assert isinstance(result_data, list)
    assert len(result_data) > 0
    assert result_data[0]["author"] == "Test User"


@pytest.mark.anyio
async def test_add_comment(client, mock_confluence_fetcher):
    """Test adding a comment to a Confluence page."""
    response = await client.call_tool(
        "confluence_add_comment",
        {"page_id": "123456", "content": "Test comment content"},
    )

    mock_confluence_fetcher.add_comment.assert_called_once_with(
        page_id="123456", content="Test comment content"
    )

    result_data = json.loads(response.content[0].text)
    assert isinstance(result_data, dict)
    assert result_data["success"] is True
    assert "comment" in result_data
    assert result_data["comment"]["id"] == "987"
    assert result_data["comment"]["author"] == "Test User"
    assert result_data["comment"]["body"] == "This is a test comment added via API"
    assert result_data["comment"]["created"] == "2023-08-01T13:00:00.000Z"


@pytest.mark.anyio
async def test_get_labels(client, mock_confluence_fetcher):
    """Test retrieving page labels."""
    response = await client.call_tool("confluence_get_labels", {"page_id": "123456"})
    mock_confluence_fetcher.get_page_labels.assert_called_once_with("123456")
    result_data = json.loads(response.content[0].text)
    assert isinstance(result_data, list)
    assert result_data[0]["name"] == "test-label"


@pytest.mark.anyio
async def test_add_label(client, mock_confluence_fetcher):
    """Test adding a label to a page."""
    response = await client.call_tool(
        "confluence_add_label", {"page_id": "123456", "name": "new-label"}
    )
    mock_confluence_fetcher.add_page_label.assert_called_once_with(
        "123456", "new-label"
    )
    result_data = json.loads(response.content[0].text)
    assert isinstance(result_data, list)
    assert result_data[0]["name"] == "test-label"


@pytest.mark.anyio
async def test_search_user(client, mock_confluence_fetcher):
    """Test the search_user tool with CQL query."""
    response = await client.call_tool(
        "confluence_search_user", {"query": 'user.fullname ~ "First Last"', "limit": 10}
    )

    mock_confluence_fetcher.search_user.assert_called_once_with(
        'user.fullname ~ "First Last"', limit=10
    )

    result_data = json.loads(response.content[0].text)
    assert isinstance(result_data, list)
    assert len(result_data) == 1
    assert result_data[0]["entity_type"] == "user"
    assert result_data[0]["title"] == "First Last"
    assert result_data[0]["user"]["account_id"] == "a031248587011jasoidf9832jd8j1"
    assert result_data[0]["user"]["display_name"] == "First Last"


@pytest.mark.anyio
async def test_create_page_with_numeric_parent_id(client, mock_confluence_fetcher):
    """Test creating a page with numeric parent_id (integer) - should convert to string."""
    response = await client.call_tool(
        "confluence_create_page",
        {
            "space_key": "TEST",
            "title": "Test Page",
            "content": "Test content",
            "parent_id": 123456789,  # Numeric ID as integer
        },
    )

    # Verify the parent_id was converted to string when calling the underlying method
    mock_confluence_fetcher.create_page.assert_called_once()
    call_kwargs = mock_confluence_fetcher.create_page.call_args.kwargs
    assert call_kwargs["parent_id"] == "123456789"  # Should be string
    assert call_kwargs["space_key"] == "TEST"
    assert call_kwargs["title"] == "Test Page"

    result_data = json.loads(response.content[0].text)
    assert result_data["message"] == "Page created successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_create_page_with_string_parent_id(client, mock_confluence_fetcher):
    """Test creating a page with string parent_id - should remain unchanged."""
    response = await client.call_tool(
        "confluence_create_page",
        {
            "space_key": "TEST",
            "title": "Test Page",
            "content": "Test content",
            "parent_id": "123456789",  # String ID
        },
    )

    mock_confluence_fetcher.create_page.assert_called_once()
    call_kwargs = mock_confluence_fetcher.create_page.call_args.kwargs
    assert call_kwargs["parent_id"] == "123456789"  # Should remain string
    assert call_kwargs["space_key"] == "TEST"
    assert call_kwargs["title"] == "Test Page"

    result_data = json.loads(response.content[0].text)
    assert result_data["message"] == "Page created successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_update_page_with_numeric_parent_id(client, mock_confluence_fetcher):
    """Test updating a page with numeric parent_id (integer) - should convert to string."""
    response = await client.call_tool(
        "confluence_update_page",
        {
            "page_id": "999999",
            "title": "Updated Page",
            "content": "Updated content",
            "parent_id": 123456789,  # Numeric ID as integer
        },
    )

    mock_confluence_fetcher.update_page.assert_called_once()
    call_kwargs = mock_confluence_fetcher.update_page.call_args.kwargs
    assert call_kwargs["parent_id"] == "123456789"  # Should be string
    assert call_kwargs["page_id"] == "999999"
    assert call_kwargs["title"] == "Updated Page"

    result_data = json.loads(response.content[0].text)
    assert result_data["message"] == "Page updated successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_update_page_with_string_parent_id(client, mock_confluence_fetcher):
    """Test updating a page with string parent_id - should remain unchanged."""
    response = await client.call_tool(
        "confluence_update_page",
        {
            "page_id": "999999",
            "title": "Updated Page",
            "content": "Updated content",
            "parent_id": "123456789",  # String ID
        },
    )

    mock_confluence_fetcher.update_page.assert_called_once()
    call_kwargs = mock_confluence_fetcher.update_page.call_args.kwargs
    assert call_kwargs["parent_id"] == "123456789"  # Should remain string
    assert call_kwargs["page_id"] == "999999"
    assert call_kwargs["title"] == "Updated Page"

    result_data = json.loads(response.content[0].text)
    assert result_data["message"] == "Page updated successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"
