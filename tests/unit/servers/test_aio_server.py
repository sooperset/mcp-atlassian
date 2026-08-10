"""Unit tests for the AIO Tests FastMCP server implementation."""

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

from mcp_atlassian.aio import AIOFetcher
from mcp_atlassian.aio.config import AIOConfig
from mcp_atlassian.models.aio import (
    AIOFolder,
    AIOFolderTree,
    AIOProject,
    AIOTag,
    AIOTestCase,
    AIOTestCaseSchema,
    AIOTestCaseSearchResult,
)
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.main import AtlassianMCP
from tests.fixtures.aio_mocks import (
    MOCK_AIO_FOLDER_TREE,
    MOCK_AIO_PROJECT_CONFIG,
    MOCK_AIO_SEARCH_RESPONSE,
    MOCK_AIO_TAGS,
    MOCK_AIO_TEST_CASE,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_aio_fetcher():
    """Create a mock AIOFetcher backed by the AIO Tests fixtures."""
    fetcher = MagicMock(spec=AIOFetcher)
    fetcher.config = MagicMock()
    fetcher.config.url = "https://tcms.aiojiraapps.com/aio-tcms/api/v1"

    fetcher.get_project.return_value = AIOProject.from_api_response(
        MOCK_AIO_PROJECT_CONFIG, project_key="PROJ"
    )
    fetcher.get_test_case_schema.return_value = AIOTestCaseSchema.from_api_response(
        MOCK_AIO_PROJECT_CONFIG, project_key="PROJ", fields=[]
    )
    fetcher.get_test_case.return_value = AIOTestCase.from_api_response(
        MOCK_AIO_TEST_CASE
    )
    fetcher.get_test_case_versions.return_value = AIOTestCase.from_api_response(
        MOCK_AIO_TEST_CASE
    )
    fetcher.search_test_cases.return_value = AIOTestCaseSearchResult.from_api_response(
        MOCK_AIO_SEARCH_RESPONSE
    )
    fetcher.create_test_case.return_value = AIOTestCase.from_api_response(
        MOCK_AIO_TEST_CASE
    )
    fetcher.update_test_case.return_value = AIOTestCase.from_api_response(
        MOCK_AIO_TEST_CASE
    )
    fetcher.get_folder_hierarchy.return_value = [
        AIOFolderTree.from_api_response(item) for item in MOCK_AIO_FOLDER_TREE
    ]
    fetcher.flatten_folders.return_value = [
        folder
        for root in MOCK_AIO_FOLDER_TREE
        for folder in AIOFolderTree.from_api_response(root).flatten()
    ]
    fetcher.create_folder.return_value = AIOFolder(
        id=101, name="Checkout", parent_id=100, path="/Regression/Checkout"
    )
    fetcher.get_tags.return_value = [
        AIOTag.from_api_response(tag) for tag in MOCK_AIO_TAGS
    ]
    return fetcher


@pytest.fixture
def mock_base_aio_config():
    """Create a mock base AIOConfig for MainAppContext."""
    return AIOConfig(
        url="https://tcms.aiojiraapps.com/aio-tcms/api/v1",
        auth_type="token",
        api_token="mock-token",
    )


def _build_test_mcp(aio_config: AIOConfig | None, read_only: bool) -> AtlassianMCP:
    """Build a test server exposing the AIO Tests tools.

    Args:
        aio_config: AIO configuration to publish in the lifespan context.
        read_only: Whether the server runs in read-only mode.

    Returns:
        The configured server.
    """

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[dict, None]:
        # Mirrors main_lifespan, which publishes the context under this key.
        try:
            yield {
                "app_lifespan_context": MainAppContext(
                    full_aio_config=aio_config, read_only=read_only
                )
            }
        finally:
            pass

    test_mcp = AtlassianMCP(
        "TestAIO", instructions="Test AIO Tests MCP Server", lifespan=test_lifespan
    )
    from mcp_atlassian.servers.aio import aio_mcp

    test_mcp.mount(aio_mcp, prefix="aio")
    return test_mcp


@pytest.fixture
def test_aio_mcp(mock_base_aio_config):
    """Create a test FastMCP instance with an AIO Tests configuration."""
    return _build_test_mcp(mock_base_aio_config, read_only=False)


@pytest.fixture
def read_only_aio_mcp(mock_base_aio_config):
    """Create a read-only test FastMCP instance."""
    return _build_test_mcp(mock_base_aio_config, read_only=True)


@pytest.fixture
def unconfigured_aio_mcp():
    """Create a test FastMCP instance without an AIO Tests configuration."""
    return _build_test_mcp(None, read_only=False)


@pytest.fixture
def mock_request():
    """Provide a mock Starlette Request object with a state."""
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.aio_fetcher = None
    request.state.atlassian_service_headers = {}
    return request


@pytest.fixture
async def aio_client(test_aio_mcp, mock_aio_fetcher, mock_request):
    """Create a FastMCP client with a mocked AIO Tests fetcher."""
    with (
        patch(
            "mcp_atlassian.servers.aio.get_aio_fetcher",
            AsyncMock(return_value=mock_aio_fetcher),
        ),
        patch(
            "mcp_atlassian.servers.dependencies.get_http_request",
            return_value=mock_request,
        ),
    ):
        async with Client(transport=FastMCPTransport(test_aio_mcp)) as client:
            yield client


@pytest.fixture
async def read_only_client(read_only_aio_mcp, mock_aio_fetcher, mock_request):
    """Create a FastMCP client against the read-only server."""
    with (
        patch(
            "mcp_atlassian.servers.aio.get_aio_fetcher",
            AsyncMock(return_value=mock_aio_fetcher),
        ),
        patch(
            "mcp_atlassian.servers.dependencies.get_http_request",
            return_value=mock_request,
        ),
    ):
        async with Client(transport=FastMCPTransport(read_only_aio_mcp)) as client:
            yield client


def parse(response) -> dict:
    """Parse the JSON payload of a tool response.

    Args:
        response: The tool call response.

    Returns:
        The decoded JSON object.
    """
    assert hasattr(response, "content")
    assert len(response.content) > 0
    assert response.content[0].type == "text"
    return json.loads(response.content[0].text)


@pytest.mark.anyio
async def test_get_project(aio_client, mock_aio_fetcher):
    """aio_get_project reports the project and its AIO Tests availability."""
    content = parse(
        await aio_client.call_tool("aio_get_project", {"project_key": "PROJ"})
    )

    assert content == {
        "aio_enabled": True,
        "project_key": "PROJ",
        "project_id": 10010,
        "adhoc_cycle_key": "AT-CY-1",
    }
    mock_aio_fetcher.get_project.assert_called_once_with("PROJ")


@pytest.mark.anyio
async def test_get_test_case_schema(aio_client, mock_aio_fetcher):
    """aio_get_test_case_schema returns fields and allowed values."""
    content = parse(
        await aio_client.call_tool("aio_get_test_case_schema", {"project_key": "PROJ"})
    )

    assert content["project_key"] == "PROJ"
    assert [
        priority["name"] for priority in content["allowed_values"]["priorities"]
    ] == ["Critical", "Medium"]
    assert {field["name"] for field in content["custom_fields"]} == {
        "Environment",
        "Reviewer",
        "Notes",
    }
    mock_aio_fetcher.get_test_case_schema.assert_called_once_with("PROJ")


@pytest.mark.anyio
async def test_search_test_cases_defaults(aio_client, mock_aio_fetcher):
    """aio_search_test_cases forwards its defaults unchanged."""
    content = parse(
        await aio_client.call_tool("aio_search_test_cases", {"project_key": "PROJ"})
    )

    assert content["count"] == 1
    assert content["test_cases"][0]["key"] == "AT-TC-17"
    kwargs = mock_aio_fetcher.search_test_cases.call_args[1]
    assert kwargs["title"] is None
    assert kwargs["start_at"] == 0
    assert kwargs["max_results"] == 50
    assert kwargs["title_match"] == "CONTAINS"


@pytest.mark.anyio
async def test_search_test_cases_filters(aio_client, mock_aio_fetcher):
    """aio_search_test_cases forwards every supported filter."""
    await aio_client.call_tool(
        "aio_search_test_cases",
        {
            "project_key": "PROJ",
            "title": "cart",
            "title_match": "EXACT_MATCH",
            "statuses": ["Published"],
            "priorities": ["Critical"],
            "folders": ["/Regression"],
            "tags": ["Smoke"],
            "include_archived": False,
            "max_results": 10,
            "start_at": 20,
        },
    )

    kwargs = mock_aio_fetcher.search_test_cases.call_args[1]
    assert kwargs["title"] == "cart"
    assert kwargs["title_match"] == "EXACT_MATCH"
    assert kwargs["statuses"] == ["Published"]
    assert kwargs["priorities"] == ["Critical"]
    assert kwargs["folders"] == ["/Regression"]
    assert kwargs["tags"] == ["Smoke"]
    assert kwargs["include_archived"] is False
    assert kwargs["max_results"] == 10
    assert kwargs["start_at"] == 20


@pytest.mark.anyio
async def test_search_test_cases_rejects_oversized_page(aio_client):
    """The page size is validated before the call."""
    with pytest.raises(ToolError):
        await aio_client.call_tool(
            "aio_search_test_cases", {"project_key": "PROJ", "max_results": 500}
        )


@pytest.mark.anyio
async def test_get_test_case(aio_client, mock_aio_fetcher):
    """aio_get_test_case returns the full case details."""
    content = parse(
        await aio_client.call_tool(
            "aio_get_test_case",
            {"project_key": "PROJ", "test_case_id": "AT-TC-17", "version": 2},
        )
    )

    assert content["key"] == "AT-TC-17"
    assert len(content["steps"]) == 2
    mock_aio_fetcher.get_test_case.assert_called_once_with(
        "PROJ",
        "AT-TC-17",
        version=2,
        include_rtf=False,
        include_attachments=False,
    )


@pytest.mark.anyio
async def test_get_test_case_versions(aio_client, mock_aio_fetcher):
    """aio_get_test_case_versions returns the version history."""
    content = parse(
        await aio_client.call_tool(
            "aio_get_test_case_versions",
            {"project_key": "PROJ", "test_case_id": "AT-TC-17"},
        )
    )

    assert content["key"] == "AT-TC-17"
    assert content["current_version"] == 2
    assert content["versions"] == [
        {"is_current": True, "version": 2, "id": 16557},
        {"is_current": False, "version": 1, "id": 16556},
    ]
    mock_aio_fetcher.get_test_case_versions.assert_called_once_with("PROJ", "AT-TC-17")


@pytest.mark.anyio
async def test_create_test_case(aio_client, mock_aio_fetcher):
    """aio_create_test_case forwards the title, steps and fields."""
    content = parse(
        await aio_client.call_tool(
            "aio_create_test_case",
            {
                "project_key": "PROJ",
                "title": "New case",
                "steps": [{"step": "Login", "expected_result": "Home"}],
                "fields": {"priority": "Critical", "folder": "/Regression"},
            },
        )
    )

    assert content["success"] is True
    assert content["test_case"]["key"] == "AT-TC-17"
    args, kwargs = mock_aio_fetcher.create_test_case.call_args
    assert args == ("PROJ", "New case")
    assert kwargs["priority"] == "Critical"
    assert kwargs["folder"] == "/Regression"
    assert kwargs["steps"] == [{"step": "Login", "expected_result": "Home"}]
    assert kwargs["create_folder_if_missing"] is True


@pytest.mark.anyio
async def test_create_test_case_ignores_duplicate_title_field(
    aio_client, mock_aio_fetcher
):
    """A title inside `fields` never shadows the positional title."""
    await aio_client.call_tool(
        "aio_create_test_case",
        {
            "project_key": "PROJ",
            "title": "Real title",
            "fields": {"title": "Other title"},
        },
    )

    args, kwargs = mock_aio_fetcher.create_test_case.call_args
    assert args == ("PROJ", "Real title")
    assert "title" not in kwargs


@pytest.mark.anyio
async def test_update_test_case(aio_client, mock_aio_fetcher):
    """aio_update_test_case forwards only the requested changes."""
    content = parse(
        await aio_client.call_tool(
            "aio_update_test_case",
            {
                "project_key": "PROJ",
                "test_case_id": "AT-TC-17",
                "fields": {"status": "Published"},
                "create_new_version": True,
            },
        )
    )

    assert content["success"] is True
    args, kwargs = mock_aio_fetcher.update_test_case.call_args
    assert args == ("PROJ", "AT-TC-17")
    assert kwargs["status"] == "Published"
    assert kwargs["create_new_version"] is True
    assert kwargs["version"] is None


@pytest.mark.anyio
async def test_get_folder_hierarchy_tree(aio_client, mock_aio_fetcher):
    """aio_get_folder_hierarchy returns a nested tree by default."""
    content = parse(
        await aio_client.call_tool("aio_get_folder_hierarchy", {"project_key": "PROJ"})
    )

    assert content["folder_type"] == "testcase"
    assert [folder["name"] for folder in content["folders"]] == ["Regression", "Smoke"]
    assert content["folders"][0]["children"][0]["path"] == "/Regression/Checkout"
    mock_aio_fetcher.get_folder_hierarchy.assert_called_once_with("PROJ", "testcase")


@pytest.mark.anyio
async def test_get_folder_hierarchy_flat(aio_client, mock_aio_fetcher):
    """The flat option returns folders with resolved paths."""
    content = parse(
        await aio_client.call_tool(
            "aio_get_folder_hierarchy",
            {"project_key": "PROJ", "folder_type": "testcycle", "flat": True},
        )
    )

    assert [folder["path"] for folder in content["folders"]] == [
        "/Regression",
        "/Regression/Checkout",
        "/Regression/Login",
        "/Smoke",
    ]
    mock_aio_fetcher.flatten_folders.assert_called_once_with("PROJ", "testcycle")


@pytest.mark.anyio
async def test_create_folder(aio_client, mock_aio_fetcher):
    """aio_create_folder forwards the path and folder type."""
    content = parse(
        await aio_client.call_tool(
            "aio_create_folder",
            {
                "project_key": "PROJ",
                "folder_path": "/Regression/Checkout",
                "parent_folder_id": 100,
            },
        )
    )

    assert content["success"] is True
    assert content["folder"]["path"] == "/Regression/Checkout"
    mock_aio_fetcher.create_folder.assert_called_once_with(
        "PROJ",
        "/Regression/Checkout",
        folder_type="testcase",
        parent_folder_id=100,
    )


@pytest.mark.anyio
async def test_get_tags(aio_client, mock_aio_fetcher):
    """aio_get_tags returns the project's tags."""
    content = parse(await aio_client.call_tool("aio_get_tags", {"project_key": "PROJ"}))

    assert content["tags"] == [
        {"id": 1, "name": "AutomationEligible"},
        {"id": 2, "name": "Smoke"},
    ]
    mock_aio_fetcher.get_tags.assert_called_once_with("PROJ")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name,arguments",
    [
        ("aio_create_test_case", {"project_key": "PROJ", "title": "New"}),
        (
            "aio_update_test_case",
            {
                "project_key": "PROJ",
                "test_case_id": "AT-TC-17",
                "fields": {"status": "Draft"},
            },
        ),
        ("aio_create_folder", {"project_key": "PROJ", "folder_path": "New"}),
    ],
)
async def test_write_tools_blocked_in_read_only_mode(
    read_only_client, mock_aio_fetcher, tool_name, arguments
):
    """Write tools refuse to run in read-only mode."""
    with pytest.raises(ToolError, match="read-only mode"):
        await read_only_client.call_tool(tool_name, arguments)


@pytest.mark.anyio
async def test_tools_are_listed_when_configured(test_aio_mcp, mock_request):
    """Every AIO Tests tool is advertised when the service is configured."""
    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request",
        return_value=mock_request,
    ):
        async with Client(transport=FastMCPTransport(test_aio_mcp)) as client:
            tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert names == {
        "aio_get_project",
        "aio_get_test_case_schema",
        "aio_search_test_cases",
        "aio_get_test_case",
        "aio_get_test_case_versions",
        "aio_create_test_case",
        "aio_update_test_case",
        "aio_get_folder_hierarchy",
        "aio_create_folder",
        "aio_get_tags",
    }


@pytest.mark.anyio
async def test_write_tools_hidden_in_read_only_mode(read_only_aio_mcp, mock_request):
    """Read-only mode hides the write tools from the listing."""
    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request",
        return_value=mock_request,
    ):
        async with Client(transport=FastMCPTransport(read_only_aio_mcp)) as client:
            tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert "aio_get_project" in names
    assert "aio_create_test_case" not in names
    assert "aio_update_test_case" not in names
    assert "aio_create_folder" not in names


@pytest.mark.anyio
async def test_tools_hidden_when_not_configured(unconfigured_aio_mcp, mock_request):
    """Without an AIO Tests configuration no AIO tool is advertised."""
    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request",
        return_value=mock_request,
    ):
        async with Client(transport=FastMCPTransport(unconfigured_aio_mcp)) as client:
            tools = await client.list_tools()

    assert [tool.name for tool in tools if tool.name.startswith("aio_")] == []
