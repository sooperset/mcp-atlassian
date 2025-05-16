"""Unit tests for the Confluence FastMCP server."""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport
from fastmcp.exceptions import ToolError
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
        description="Test Confluence MCP Server",
        lifespan=test_lifespan,
    )

    # Create and configure the sub-MCP for Confluence tools
    confluence_sub_mcp = FastMCP(name="TestConfluenceSubMCP")
    confluence_sub_mcp.tool()(search)
    confluence_sub_mcp.tool()(get_page)
    confluence_sub_mcp.tool()(get_page_children)
    confluence_sub_mcp.tool()(get_comments)
    confluence_sub_mcp.tool()(add_comment)
    confluence_sub_mcp.tool()(get_labels)
    confluence_sub_mcp.tool()(add_label)
    confluence_sub_mcp.tool()(create_page)
    confluence_sub_mcp.tool()(update_page)
    confluence_sub_mcp.tool()(delete_page)

    test_mcp.mount("confluence", confluence_sub_mcp)

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
        description="No Fetcher Test Confluence MCP Server",
        lifespan=no_fetcher_test_lifespan,
    )

    # Create and configure the sub-MCP for Confluence tools
    confluence_sub_mcp = FastMCP(name="NoFetcherTestConfluenceSubMCP")
    confluence_sub_mcp.tool()(search)
    confluence_sub_mcp.tool()(get_page)
    confluence_sub_mcp.tool()(get_page_children)
    confluence_sub_mcp.tool()(get_comments)
    confluence_sub_mcp.tool()(add_comment)
    confluence_sub_mcp.tool()(get_labels)
    confluence_sub_mcp.tool()(add_label)
    confluence_sub_mcp.tool()(create_page)
    confluence_sub_mcp.tool()(update_page)
    confluence_sub_mcp.tool()(delete_page)

    test_mcp.mount("confluence", confluence_sub_mcp)

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
    assert kwargs.get("spaces_filter") == ""

    result_data = json.loads(response[0].text)
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

    result_data = json.loads(response[0].text)
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

    result_data = json.loads(response[0].text)
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

    result_data = json.loads(response[0].text)
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

    result_data = json.loads(response[0].text)
    assert "parent_id" in result_data
    assert "results" in result_data
    assert len(result_data["results"]) > 0
    assert result_data["results"][0]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_get_comments(client, mock_confluence_fetcher):
    """Test retrieving page comments."""
    response = await client.call_tool("confluence_get_comments", {"page_id": "123456"})

    mock_confluence_fetcher.get_page_comments.assert_called_once_with("123456")

    result_data = json.loads(response[0].text)
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

    result_data = json.loads(response[0].text)
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
    result_data = json.loads(response[0].text)
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
    result_data = json.loads(response[0].text)
    assert isinstance(result_data, list)
    assert result_data[0]["name"] == "test-label"


@pytest.mark.anyio
async def test_create_page(client, mock_confluence_fetcher):
    """Test creating a new page."""
    response = await client.call_tool(
        "confluence_create_page",
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
        parent_id="",
        is_markdown=True,
    )
    result_data = json.loads(response[0].text)
    assert result_data["message"] == "Page created successfully"
    assert result_data["page"]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_update_page(client, mock_confluence_fetcher):
    """Test updating an existing page."""
    response = await client.call_tool(
        "confluence_update_page",
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
    assert result_data["page"]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_delete_page(client, mock_confluence_fetcher):
    """Test deleting a page."""
    response = await client.call_tool("confluence_delete_page", {"page_id": "123456"})
    mock_confluence_fetcher.delete_page.assert_called_once_with(page_id="123456")
    result_data = json.loads(response[0].text)
    assert result_data["success"] is True


@pytest.mark.anyio
async def test_no_fetcher_update_page(no_fetcher_client_fixture, mock_request):
    """Test that page update fails when Confluence client is not configured."""

    async def mock_get_fetcher_error(*args, **kwargs):
        raise ValueError("Mocked: Confluence client is not configured or available")

    with (
        patch(
            "src.mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(side_effect=mock_get_fetcher_error),
        ),
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            return_value=mock_request,
        ),
    ):
        with pytest.raises(ToolError) as excinfo:
            await no_fetcher_client_fixture.call_tool(
                "confluence_update_page",
                {
                    "page_id": "123456",
                    "title": "Updated Page",
                    "content": "## Updated Content",
                },
            )
    assert "Error calling tool 'update_page'" in str(excinfo.value)


@pytest.mark.anyio
async def test_no_fetcher_delete_page(no_fetcher_client_fixture, mock_request):
    """Test that page deletion fails when Confluence client is not configured."""

    async def mock_get_fetcher_error(*args, **kwargs):
        raise ValueError("Mocked: Confluence client is not configured or available")

    with (
        patch(
            "src.mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(side_effect=mock_get_fetcher_error),
        ),
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            return_value=mock_request,
        ),
    ):
        with pytest.raises(ToolError) as excinfo:
            await no_fetcher_client_fixture.call_tool(
                "confluence_delete_page", {"page_id": "123456"}
            )
    assert "Error calling tool 'delete_page'" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_page_with_user_specific_fetcher_in_state(
    test_confluence_mcp, mock_confluence_fetcher
):
    """Test get_page uses fetcher from request.state if UserTokenMiddleware provided it."""
    _mock_request_with_fetcher_in_state = MagicMock(spec=Request)
    _mock_request_with_fetcher_in_state.state = MagicMock()
    _mock_request_with_fetcher_in_state.state.confluence_fetcher = (
        mock_confluence_fetcher
    )
    _mock_request_with_fetcher_in_state.state.user_atlassian_auth_type = "oauth"
    _mock_request_with_fetcher_in_state.state.user_atlassian_token = (
        "user_specific_token"
    )
    from src.mcp_atlassian.servers.dependencies import (
        get_confluence_fetcher as get_confluence_fetcher_real,
    )

    with (
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            return_value=_mock_request_with_fetcher_in_state,
        ) as mock_get_http,
        patch(
            "src.mcp_atlassian.servers.confluence.get_confluence_fetcher",
            side_effect=AsyncMock(wraps=get_confluence_fetcher_real),
        ),
    ):
        async with Client(
            transport=FastMCPTransport(test_confluence_mcp)
        ) as client_instance:
            response = await client_instance.call_tool(
                "confluence_get_page", {"page_id": "789"}
            )
    mock_get_http.assert_called()
    mock_confluence_fetcher.get_page_content.assert_called_with(
        "789", convert_to_markdown=True
    )
    result_data = json.loads(response[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page Mock Title"


@pytest.mark.anyio
async def test_get_page_by_title_and_space_key(client, mock_confluence_fetcher):
    """Test get_page tool with title and space_key lookup."""
    mock_page = MagicMock(spec=ConfluencePage)
    mock_page.to_simplified_dict.return_value = {
        "id": "654321",
        "title": "Title Lookup Page",
        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/654321/Title+Lookup",
        "content": {
            "value": "Content by title lookup",
            "format": "markdown",
        },
    }
    mock_page.content = "Content by title lookup"
    mock_confluence_fetcher.get_page_by_title.return_value = mock_page

    response = await client.call_tool(
        "confluence_get_page", {"title": "Title Lookup Page", "space_key": "TEST"}
    )
    mock_confluence_fetcher.get_page_by_title.assert_called_once_with(
        "TEST", "Title Lookup Page", convert_to_markdown=True
    )
    result_data = json.loads(response[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Title Lookup Page"
    assert result_data["metadata"]["content"]["value"] == "Content by title lookup"


@pytest.mark.anyio
async def test_get_page_by_title_and_space_key_not_found(
    client, mock_confluence_fetcher
):
    """Test get_page tool with title and space_key when page is not found."""
    mock_confluence_fetcher.get_page_by_title.return_value = None
    response = await client.call_tool(
        "confluence_get_page", {"title": "Missing Page", "space_key": "TEST"}
    )
    result_data = json.loads(response[0].text)
    assert "error" in result_data
    assert "not found" in result_data["error"]


@pytest.mark.anyio
async def test_get_page_error_missing_space_key(client, mock_confluence_fetcher):
    """Test get_page tool with title but missing space_key (should error)."""
    with pytest.raises(ToolError) as excinfo:
        await client.call_tool("confluence_get_page", {"title": "Some Page"})
    assert "Error calling tool 'get_page'" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_page_error_missing_title(client, mock_confluence_fetcher):
    """Test get_page tool with space_key but missing title (should error)."""
    with pytest.raises(ToolError) as excinfo:
        await client.call_tool("confluence_get_page", {"space_key": "TEST"})
    assert "Error calling tool 'get_page'" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_page_error_no_identifiers(client, mock_confluence_fetcher):
    """Test get_page tool with neither page_id nor title+space_key (should error)."""
    with pytest.raises(ToolError) as excinfo:
        await client.call_tool("confluence_get_page", {})
    assert "Error calling tool 'get_page'" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_page_precedence_page_id(client, mock_confluence_fetcher):
    """Test get_page tool uses page_id even if title and space_key are provided."""
    response = await client.call_tool(
        "confluence_get_page",
        {"page_id": "123456", "title": "Ignored", "space_key": "IGNORED"},
    )
    mock_confluence_fetcher.get_page_content.assert_called_once_with(
        "123456", convert_to_markdown=True
    )
    mock_confluence_fetcher.get_page_by_title.assert_not_called()
    result_data = json.loads(response[0].text)
    assert "metadata" in result_data
    assert result_data["metadata"]["title"] == "Test Page Mock Title"
