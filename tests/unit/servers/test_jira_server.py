"""Unit tests for the Jira FastMCP server implementation."""

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

from src.mcp_atlassian.jira import JiraFetcher
from src.mcp_atlassian.jira.config import JiraConfig
from src.mcp_atlassian.servers.context import MainAppContext
from src.mcp_atlassian.servers.main import AtlassianMCP
from src.mcp_atlassian.utils.oauth import OAuthConfig
from tests.fixtures.jira_mocks import (
    MOCK_JIRA_COMMENTS_SIMPLIFIED,
    MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED,
    MOCK_JIRA_JQL_RESPONSE_SIMPLIFIED,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_jira_fetcher():
    """Create a mock JiraFetcher using predefined responses from fixtures."""
    mock_fetcher = MagicMock(spec=JiraFetcher)
    mock_fetcher.config = MagicMock()
    mock_fetcher.config.read_only = False
    mock_fetcher.config.url = "https://test.atlassian.net"
    mock_fetcher.config.projects_filter = None  # Explicitly set to None by default

    # Configure common methods
    mock_fetcher.get_current_user_account_id.return_value = "test-account-id"
    mock_fetcher.jira = MagicMock()

    # Configure get_issue to return fixture data
    def mock_get_issue(
        issue_key,
        fields=None,
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    ):
        if not issue_key:
            raise ValueError("Issue key is required")
        mock_issue = MagicMock()
        response_data = MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED.copy()
        response_data["key"] = issue_key
        response_data["fields_queried"] = fields
        response_data["expand_param"] = expand
        response_data["comment_limit"] = comment_limit
        response_data["properties_param"] = properties
        response_data["update_history"] = update_history
        response_data["id"] = MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED["id"]
        response_data["summary"] = MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED["fields"][
            "summary"
        ]
        response_data["status"] = {
            "name": MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED["fields"]["status"]["name"]
        }
        mock_issue.to_simplified_dict.return_value = response_data
        return mock_issue

    mock_fetcher.get_issue.side_effect = mock_get_issue

    # Configure get_issue_comments to return fixture data
    def mock_get_issue_comments(issue_key, limit=10):
        return MOCK_JIRA_COMMENTS_SIMPLIFIED["comments"][:limit]

    mock_fetcher.get_issue_comments.side_effect = mock_get_issue_comments

    # Configure search_issues to return fixture data
    def mock_search_issues(jql, **kwargs):
        mock_search_result = MagicMock()
        issues = []
        for issue_data in MOCK_JIRA_JQL_RESPONSE_SIMPLIFIED["issues"]:
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = issue_data
            issues.append(mock_issue)
        mock_search_result.issues = issues
        mock_search_result.total = len(issues)
        mock_search_result.start_at = kwargs.get("start", 0)
        mock_search_result.max_results = kwargs.get("limit", 50)
        mock_search_result.to_simplified_dict.return_value = {
            "total": len(issues),
            "start_at": kwargs.get("start", 0),
            "max_results": kwargs.get("limit", 50),
            "issues": [issue.to_simplified_dict() for issue in issues],
        }
        return mock_search_result

    mock_fetcher.search_issues.side_effect = mock_search_issues

    # Configure create_issue
    def mock_create_issue(
        project_key,
        summary,
        issue_type,
        description=None,
        assignee=None,
        components=None,
        **additional_fields,
    ):
        if not project_key or project_key.strip() == "":
            raise ValueError("valid project is required")
        components_list = None
        if components:
            if isinstance(components, str):
                components_list = components.split(",")
            elif isinstance(components, list):
                components_list = components
        mock_issue = MagicMock()
        response_data = {
            "key": f"{project_key}-456",
            "summary": summary,
            "description": description,
            "issue_type": {"name": issue_type},
            "status": {"name": "Open"},
            "components": [{"name": comp} for comp in components_list]
            if components_list
            else [],
            **additional_fields,
        }
        mock_issue.to_simplified_dict.return_value = response_data
        return mock_issue

    mock_fetcher.create_issue.side_effect = mock_create_issue

    # Configure batch_create_issues
    def mock_batch_create_issues(issues, validate_only=False):
        if not isinstance(issues, list):
            try:
                parsed_issues = json.loads(issues)
                if not isinstance(parsed_issues, list):
                    raise ValueError(
                        "Issues must be a list or a valid JSON array string."
                    )
                issues = parsed_issues
            except (json.JSONDecodeError, TypeError):
                raise ValueError("Issues must be a list or a valid JSON array string.")
        mock_issues = []
        for idx, issue_data in enumerate(issues, 1):
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = {
                "key": f"{issue_data['project_key']}-{idx}",
                "summary": issue_data["summary"],
                "issue_type": {"name": issue_data["issue_type"]},
                "status": {"name": "To Do"},
            }
            mock_issues.append(mock_issue)
        return mock_issues

    mock_fetcher.batch_create_issues.side_effect = mock_batch_create_issues

    # Configure get_epic_issues
    def mock_get_epic_issues(epic_key, start=0, limit=50):
        mock_issues = []
        for i in range(1, 4):
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = {
                "key": f"TEST-{i}",
                "summary": f"Epic Issue {i}",
                "issue_type": {"name": "Task" if i % 2 == 0 else "Bug"},
                "status": {"name": "To Do" if i % 2 == 0 else "In Progress"},
            }
            mock_issues.append(mock_issue)
        return mock_issues[start : start + limit]

    mock_fetcher.get_epic_issues.side_effect = mock_get_epic_issues

    # Configure get_all_projects
    def mock_get_all_projects(include_archived=False):
        projects = [
            {
                "id": "10000",
                "key": "TEST",
                "name": "Test Project",
                "description": "Project for testing",
                "lead": {"name": "admin", "displayName": "Administrator"},
                "projectTypeKey": "software",
                "archived": False,
            }
        ]
        if include_archived:
            projects.append(
                {
                    "id": "10001",
                    "key": "ARCHIVED",
                    "name": "Archived Project",
                    "description": "Archived project",
                    "lead": {"name": "admin", "displayName": "Administrator"},
                    "projectTypeKey": "software",
                    "archived": True,
                }
            )
        return projects

    # Set default side_effect to respect include_archived parameter
    mock_fetcher.get_all_projects.side_effect = mock_get_all_projects

    mock_fetcher.jira.jql.return_value = {
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

    from src.mcp_atlassian.models.jira.common import JiraUser

    mock_user = MagicMock(spec=JiraUser)
    mock_user.to_simplified_dict.return_value = {
        "display_name": "Test User (test.profile@example.com)",
        "name": "Test User (test.profile@example.com)",
        "email": "test.profile@example.com",
        "avatar_url": "https://test.atlassian.net/avatar/test.profile@example.com",
    }
    mock_get_user_profile = MagicMock()

    def side_effect_func(identifier):
        if identifier == "nonexistent@example.com":
            raise ValueError(f"User '{identifier}' not found.")
        return mock_user

    mock_get_user_profile.side_effect = side_effect_func
    mock_fetcher.get_user_profile_by_identifier = mock_get_user_profile
    return mock_fetcher


@pytest.fixture
def mock_base_jira_config():
    """Create a mock base JiraConfig for MainAppContext using OAuth for multi-user scenario."""
    mock_oauth_config = OAuthConfig(
        client_id="server_client_id",
        client_secret="server_client_secret",
        redirect_uri="http://localhost",
        scope="read:jira-work",
        cloud_id="mock_jira_cloud_id",
    )
    return JiraConfig(
        url="https://mock-jira.atlassian.net",
        auth_type="oauth",
        oauth_config=mock_oauth_config,
    )


@pytest.fixture
def test_jira_mcp(mock_jira_fetcher, mock_base_jira_config):
    """Create a test FastMCP instance with standard configuration."""

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[MainAppContext, None]:
        try:
            yield MainAppContext(
                full_jira_config=mock_base_jira_config, read_only=False
            )
        finally:
            pass

    test_mcp = AtlassianMCP(
        "TestJira", instructions="Test Jira MCP Server", lifespan=test_lifespan
    )
    from src.mcp_atlassian.servers.jira import (
        add_comment,
        add_worklog,
        batch_create_issues,
        batch_create_versions,
        batch_get_changelogs,
        create_issue,
        create_issue_link,
        delete_issue,
        download_attachments,
        get_agile_boards,
        get_all_projects,
        get_board_issues,
        get_issue,
        get_link_types,
        get_project_issues,
        get_project_versions,
        get_sprint_issues,
        get_sprints_from_board,
        get_transitions,
        get_user_profile,
        get_worklog,
        link_to_epic,
        remove_issue_link,
        search,
        search_fields,
        transition_issue,
        update_issue,
        update_sprint,
    )

    jira_sub_mcp = FastMCP(name="TestJiraSubMCP")
    jira_sub_mcp.add_tool(get_issue)
    jira_sub_mcp.add_tool(search)
    jira_sub_mcp.add_tool(search_fields)
    jira_sub_mcp.add_tool(get_project_issues)
    jira_sub_mcp.add_tool(get_project_versions)
    jira_sub_mcp.add_tool(get_all_projects)
    jira_sub_mcp.add_tool(get_transitions)
    jira_sub_mcp.add_tool(get_worklog)
    jira_sub_mcp.add_tool(download_attachments)
    jira_sub_mcp.add_tool(get_agile_boards)
    jira_sub_mcp.add_tool(get_board_issues)
    jira_sub_mcp.add_tool(get_sprints_from_board)
    jira_sub_mcp.add_tool(get_sprint_issues)
    jira_sub_mcp.add_tool(get_link_types)
    jira_sub_mcp.add_tool(get_user_profile)
    jira_sub_mcp.add_tool(create_issue)
    jira_sub_mcp.add_tool(batch_create_issues)
    jira_sub_mcp.add_tool(batch_get_changelogs)
    jira_sub_mcp.add_tool(update_issue)
    jira_sub_mcp.add_tool(delete_issue)
    jira_sub_mcp.add_tool(add_comment)
    jira_sub_mcp.add_tool(add_worklog)
    jira_sub_mcp.add_tool(link_to_epic)
    jira_sub_mcp.add_tool(create_issue_link)
    jira_sub_mcp.add_tool(remove_issue_link)
    jira_sub_mcp.add_tool(transition_issue)
    jira_sub_mcp.add_tool(update_sprint)
    jira_sub_mcp.add_tool(batch_create_versions)
    test_mcp.mount(jira_sub_mcp, prefix="jira")
    return test_mcp


@pytest.fixture
def no_fetcher_test_jira_mcp(mock_base_jira_config):
    """Create a test FastMCP instance that simulates missing Jira fetcher."""

    @asynccontextmanager
    async def no_fetcher_test_lifespan(
        app: FastMCP,
    ) -> AsyncGenerator[MainAppContext, None]:
        try:
            yield MainAppContext(full_jira_config=None, read_only=False)
        finally:
            pass

    test_mcp = AtlassianMCP(
        "NoFetcherTestJira",
        instructions="No Fetcher Test Jira MCP Server",
        lifespan=no_fetcher_test_lifespan,
    )
    from src.mcp_atlassian.servers.jira import get_issue

    jira_sub_mcp = FastMCP(name="NoFetcherTestJiraSubMCP")
    jira_sub_mcp.add_tool(get_issue)
    test_mcp.mount(jira_sub_mcp, prefix="jira")
    return test_mcp


@pytest.fixture
def mock_request():
    """Provides a mock Starlette Request object with a state."""
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.jira_fetcher = None
    request.state.user_atlassian_auth_type = None
    request.state.user_atlassian_token = None
    request.state.user_atlassian_email = None
    return request


@pytest.fixture
async def jira_client(test_jira_mcp, mock_jira_fetcher, mock_request):
    """Create a FastMCP client with mocked Jira fetcher and request state."""
    with (
        patch(
            "src.mcp_atlassian.servers.jira.get_jira_fetcher",
            AsyncMock(return_value=mock_jira_fetcher),
        ),
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            return_value=mock_request,
        ),
    ):
        async with Client(transport=FastMCPTransport(test_jira_mcp)) as client_instance:
            yield client_instance


@pytest.fixture
async def no_fetcher_client_fixture(no_fetcher_test_jira_mcp, mock_request):
    """Create a client that simulates missing Jira fetcher configuration."""
    async with Client(
        transport=FastMCPTransport(no_fetcher_test_jira_mcp)
    ) as client_for_no_fetcher:
        yield client_for_no_fetcher


@pytest.mark.anyio
async def test_get_issue(jira_client, mock_jira_fetcher):
    """Test the get_issue tool with fixture data."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {
            "issue_key": "TEST-123",
            "fields": "summary,description,status",
        },
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    text_content = response.content[0]
    assert text_content.type == "text"
    content = json.loads(text_content.text)
    assert content["key"] == "TEST-123"
    assert content["summary"] == "Test Issue Summary"
    mock_jira_fetcher.get_issue.assert_called_once_with(
        issue_key="TEST-123",
        fields=["summary", "description", "status"],
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    )


@pytest.mark.anyio
async def test_search(jira_client, mock_jira_fetcher):
    """Test the search tool with fixture data."""
    response = await jira_client.call_tool(
        "jira_search",
        {
            "jql": "project = TEST",
            "fields": "summary,status",
            "limit": 10,
            "start_at": 0,
        },
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    text_content = response.content[0]
    assert text_content.type == "text"
    content = json.loads(text_content.text)
    assert isinstance(content, dict)
    assert "issues" in content
    assert isinstance(content["issues"], list)
    assert len(content["issues"]) >= 1
    assert content["issues"][0]["key"] == "PROJ-123"
    assert content["total"] > 0
    assert content["start_at"] == 0
    assert content["max_results"] == 10
    mock_jira_fetcher.search_issues.assert_called_once_with(
        jql="project = TEST",
        fields=["summary", "status"],
        limit=10,
        start=0,
        projects_filter=None,
        expand=None,
    )


@pytest.mark.anyio
async def test_create_issue(jira_client, mock_jira_fetcher):
    """Test the create_issue tool with fixture data."""
    response = await jira_client.call_tool(
        "jira_create_issue",
        {
            "project_key": "TEST",
            "summary": "New Issue",
            "issue_type": "Task",
            "description": "This is a new task",
            "components": "Frontend,API",
            "additional_fields": {"priority": {"name": "Medium"}},
        },
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    text_content = response.content[0]
    assert text_content.type == "text"
    content = json.loads(text_content.text)
    assert content["message"] == "Issue created successfully"
    assert "issue" in content
    assert content["issue"]["key"] == "TEST-456"
    assert content["issue"]["summary"] == "New Issue"
    assert content["issue"]["description"] == "This is a new task"
    assert "components" in content["issue"]
    component_names = [comp["name"] for comp in content["issue"]["components"]]
    assert "Frontend" in component_names
    assert "API" in component_names
    assert content["issue"]["priority"] == {"name": "Medium"}
    mock_jira_fetcher.create_issue.assert_called_once_with(
        project_key="TEST",
        summary="New Issue",
        issue_type="Task",
        description="This is a new task",
        assignee=None,
        components=["Frontend", "API"],
        priority={"name": "Medium"},
    )


@pytest.mark.anyio
async def test_batch_create_issues(jira_client, mock_jira_fetcher):
    """Test batch creation of Jira issues."""
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
    test_issues_json = json.dumps(test_issues)
    response = await jira_client.call_tool(
        "jira_batch_create_issues",
        {"issues": test_issues_json, "validate_only": False},
    )
    assert len(response.content) == 1
    text_content = response.content[0]
    assert text_content.type == "text"
    content = json.loads(text_content.text)
    assert "message" in content
    assert "issues" in content
    assert len(content["issues"]) == 2
    assert content["issues"][0]["key"] == "TEST-1"
    assert content["issues"][1]["key"] == "TEST-2"
    call_args, call_kwargs = mock_jira_fetcher.batch_create_issues.call_args
    assert call_args[0] == test_issues
    assert "validate_only" in call_kwargs
    assert call_kwargs["validate_only"] is False


@pytest.mark.anyio
async def test_batch_create_issues_invalid_json(jira_client):
    """Test error handling for invalid JSON in batch issue creation."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_batch_create_issues",
            {"issues": "{invalid json", "validate_only": False},
        )
    assert "Error calling tool 'batch_create_issues'" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_user_profile_tool_success(jira_client, mock_jira_fetcher):
    """Test the get_user_profile tool successfully retrieves user info."""
    response = await jira_client.call_tool(
        "jira_get_user_profile", {"user_identifier": "test.profile@example.com"}
    )
    mock_jira_fetcher.get_user_profile_by_identifier.assert_called_once_with(
        "test.profile@example.com"
    )
    assert len(response.content) == 1
    result_data = json.loads(response.content[0].text)
    assert result_data["success"] is True
    assert "user" in result_data
    user_info = result_data["user"]
    assert user_info["display_name"] == "Test User (test.profile@example.com)"
    assert user_info["email"] == "test.profile@example.com"
    assert (
        user_info["avatar_url"]
        == "https://test.atlassian.net/avatar/test.profile@example.com"
    )


@pytest.mark.anyio
async def test_get_user_profile_tool_not_found(jira_client, mock_jira_fetcher):
    """Test the get_user_profile tool handles 'user not found' errors."""
    response = await jira_client.call_tool(
        "jira_get_user_profile", {"user_identifier": "nonexistent@example.com"}
    )
    assert len(response.content) == 1
    result_data = json.loads(response.content[0].text)
    assert result_data["success"] is False
    assert "error" in result_data
    assert "not found" in result_data["error"]
    assert result_data["user_identifier"] == "nonexistent@example.com"


@pytest.mark.anyio
async def test_no_fetcher_get_issue(no_fetcher_client_fixture, mock_request):
    """Test that get_issue fails when Jira client is not configured (global config missing)."""

    async def mock_get_fetcher_error(*args, **kwargs):
        raise ValueError(
            "Mocked: Jira client (fetcher) not available. Ensure server is configured correctly."
        )

    with (
        patch(
            "src.mcp_atlassian.servers.jira.get_jira_fetcher",
            AsyncMock(side_effect=mock_get_fetcher_error),
        ),
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            return_value=mock_request,
        ),
    ):
        with pytest.raises(ToolError) as excinfo:
            await no_fetcher_client_fixture.call_tool(
                "jira_get_issue",
                {
                    "issue_key": "TEST-123",
                },
            )
    assert "Error calling tool 'get_issue'" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_issue_with_user_specific_fetcher_in_state(
    test_jira_mcp, mock_jira_fetcher, mock_base_jira_config
):
    """Test get_issue uses fetcher from request.state if UserTokenMiddleware provided it."""
    _mock_request_with_fetcher_in_state = MagicMock(spec=Request)
    _mock_request_with_fetcher_in_state.state = MagicMock()
    _mock_request_with_fetcher_in_state.state.jira_fetcher = mock_jira_fetcher
    _mock_request_with_fetcher_in_state.state.user_atlassian_auth_type = "oauth"
    _mock_request_with_fetcher_in_state.state.user_atlassian_token = (
        "user_specific_token"
    )

    # Define the specific fields we expect for this test case
    test_fields_str = "summary,status,issuetype"
    expected_fields_list = ["summary", "status", "issuetype"]

    # Import the real get_jira_fetcher to test its interaction with request.state
    from src.mcp_atlassian.servers.dependencies import (
        get_jira_fetcher as get_jira_fetcher_real,
    )

    with (
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            return_value=_mock_request_with_fetcher_in_state,
        ) as mock_get_http,
        patch(
            "src.mcp_atlassian.servers.jira.get_jira_fetcher",
            side_effect=AsyncMock(wraps=get_jira_fetcher_real),
        ),
    ):
        async with Client(transport=FastMCPTransport(test_jira_mcp)) as client_instance:
            response = await client_instance.call_tool(
                "jira_get_issue",
                {"issue_key": "USER-STATE-1", "fields": test_fields_str},
            )

    mock_get_http.assert_called()
    mock_jira_fetcher.get_issue.assert_called_with(
        issue_key="USER-STATE-1",
        fields=expected_fields_list,
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    )
    result_data = json.loads(response.content[0].text)
    assert result_data["key"] == "USER-STATE-1"


@pytest.mark.anyio
async def test_get_project_versions_tool(jira_client, mock_jira_fetcher):
    """Test the jira_get_project_versions tool returns simplified version list."""
    # Prepare mock raw versions
    raw_versions = [
        {
            "id": "100",
            "name": "v1.0",
            "description": "First",
            "released": True,
            "archived": False,
        },
        {
            "id": "101",
            "name": "v2.0",
            "startDate": "2025-01-01",
            "releaseDate": "2025-02-01",
            "released": False,
            "archived": False,
        },
    ]
    mock_jira_fetcher.get_project_versions.return_value = raw_versions

    response = await jira_client.call_tool(
        "jira_get_project_versions",
        {"project_key": "TEST"},
    )
    assert hasattr(response, "content")
    assert len(response.content) == 1  # FastMCP wraps as list of messages
    msg = response.content[0]
    assert msg.type == "text"
    import json

    data = json.loads(msg.text)
    assert isinstance(data, list)
    # Check fields in simplified dict
    assert data[0]["id"] == "100"
    assert data[0]["name"] == "v1.0"
    assert data[0]["description"] == "First"


@pytest.mark.anyio
async def test_get_all_projects_tool(jira_client, mock_jira_fetcher):
    """Test the jira_get_all_projects tool returns all accessible projects."""
    # Prepare mock project data
    mock_projects = [
        {
            "id": "10000",
            "key": "PROJ1",
            "name": "Project One",
            "description": "First project",
            "lead": {"name": "user1", "displayName": "User One"},
            "projectTypeKey": "software",
            "archived": False,
        },
        {
            "id": "10001",
            "key": "PROJ2",
            "name": "Project Two",
            "description": "Second project",
            "lead": {"name": "user2", "displayName": "User Two"},
            "projectTypeKey": "business",
            "archived": False,
        },
    ]
    # Reset the mock and set specific return value for this test
    mock_jira_fetcher.get_all_projects.reset_mock()
    mock_jira_fetcher.get_all_projects.side_effect = (
        lambda include_archived=False: mock_projects
    )

    # Test with default parameters (include_archived=False)
    response = await jira_client.call_tool(
        "jira_get_all_projects",
        {},
    )
    assert hasattr(response, "content")
    assert len(response.content) == 1  # FastMCP wraps as list of messages
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == "10000"
    assert data[0]["key"] == "PROJ1"
    assert data[0]["name"] == "Project One"
    assert data[1]["id"] == "10001"
    assert data[1]["key"] == "PROJ2"
    assert data[1]["name"] == "Project Two"

    # Verify the underlying method was called with default parameter
    mock_jira_fetcher.get_all_projects.assert_called_once_with(include_archived=False)


@pytest.mark.anyio
async def test_get_all_projects_tool_with_archived(jira_client, mock_jira_fetcher):
    """Test the jira_get_all_projects tool with include_archived=True."""
    mock_projects = [
        {
            "id": "10000",
            "key": "PROJ1",
            "name": "Active Project",
            "description": "Active project",
            "archived": False,
        },
        {
            "id": "10002",
            "key": "ARCHIVED",
            "name": "Archived Project",
            "description": "Archived project",
            "archived": True,
        },
    ]
    # Reset the mock and set specific return value for this test
    mock_jira_fetcher.get_all_projects.reset_mock()
    mock_jira_fetcher.get_all_projects.side_effect = (
        lambda include_archived=False: mock_projects
    )

    # Test with include_archived=True
    response = await jira_client.call_tool(
        "jira_get_all_projects",
        {"include_archived": True},
    )
    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert isinstance(data, list)
    assert len(data) == 2
    # Project keys should always be uppercase in the response
    assert data[0]["key"] == "PROJ1"
    assert data[1]["key"] == "ARCHIVED"

    # Verify the underlying method was called with include_archived=True
    mock_jira_fetcher.get_all_projects.assert_called_once_with(include_archived=True)


@pytest.mark.anyio
async def test_get_all_projects_tool_with_projects_filter(
    jira_client, mock_jira_fetcher
):
    """Test the jira_get_all_projects tool respects project filter configuration."""
    # Prepare mock project data - simulate getting all projects from API
    all_mock_projects = [
        {
            "id": "10000",
            "key": "PROJ1",
            "name": "Project One",
            "description": "First project",
        },
        {
            "id": "10001",
            "key": "PROJ2",
            "name": "Project Two",
            "description": "Second project",
        },
        {
            "id": "10002",
            "key": "OTHER",
            "name": "Other Project",
            "description": "Should be filtered out",
        },
    ]

    # Set up the mock to return all projects
    mock_jira_fetcher.get_all_projects.reset_mock()
    mock_jira_fetcher.get_all_projects.side_effect = (
        lambda include_archived=False: all_mock_projects
    )

    # Set up the projects filter in the config
    mock_jira_fetcher.config.projects_filter = "PROJ1,PROJ2"

    # Call the tool
    response = await jira_client.call_tool(
        "jira_get_all_projects",
        {},
    )

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert isinstance(data, list)

    # Should only return projects in the filter (PROJ1, PROJ2), not OTHER
    assert len(data) == 2
    returned_keys = [project["key"] for project in data]
    # Project keys should always be uppercase in the response
    assert "PROJ1" in returned_keys
    assert "PROJ2" in returned_keys
    assert "OTHER" not in returned_keys

    # Verify the underlying method was called (still gets all projects, but then filters)
    mock_jira_fetcher.get_all_projects.assert_called_once_with(include_archived=False)


@pytest.mark.anyio
async def test_get_all_projects_tool_no_projects_filter(jira_client, mock_jira_fetcher):
    """Test the jira_get_all_projects tool returns all projects when no filter is configured."""
    # Prepare mock project data
    all_mock_projects = [
        {
            "id": "10000",
            "key": "PROJ1",
            "name": "Project One",
            "description": "First project",
        },
        {
            "id": "10001",
            "key": "OTHER",
            "name": "Other Project",
            "description": "Should not be filtered out",
        },
    ]

    # Set up the mock to return all projects
    mock_jira_fetcher.get_all_projects.reset_mock()
    mock_jira_fetcher.get_all_projects.side_effect = (
        lambda include_archived=False: all_mock_projects
    )

    # Ensure no projects filter is set
    mock_jira_fetcher.config.projects_filter = None

    # Call the tool
    response = await jira_client.call_tool(
        "jira_get_all_projects",
        {},
    )

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert isinstance(data, list)

    # Should return all projects when no filter is configured
    assert len(data) == 2
    returned_keys = [project["key"] for project in data]
    # Project keys should always be uppercase in the response
    assert "PROJ1" in returned_keys
    assert "OTHER" in returned_keys

    # Verify the underlying method was called
    mock_jira_fetcher.get_all_projects.assert_called_once_with(include_archived=False)


@pytest.mark.anyio
async def test_get_all_projects_tool_case_insensitive_filter(
    jira_client, mock_jira_fetcher
):
    """Test the jira_get_all_projects tool handles case-insensitive filtering and whitespace."""
    # Prepare mock project data with mixed case
    all_mock_projects = [
        {
            "id": "10000",
            "key": "proj1",  # lowercase
            "name": "Project One",
            "description": "First project",
        },
        {
            "id": "10001",
            "key": "PROJ2",  # uppercase
            "name": "Project Two",
            "description": "Second project",
        },
        {
            "id": "10002",
            "key": "other",  # should be filtered out
            "name": "Other Project",
            "description": "Should be filtered out",
        },
    ]

    # Set up the mock to return all projects
    mock_jira_fetcher.get_all_projects.reset_mock()
    mock_jira_fetcher.get_all_projects.side_effect = (
        lambda include_archived=False: all_mock_projects
    )

    # Set up projects filter with mixed case and whitespace
    mock_jira_fetcher.config.projects_filter = " PROJ1 , proj2 "

    # Call the tool
    response = await jira_client.call_tool(
        "jira_get_all_projects",
        {},
    )

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert isinstance(data, list)

    # Should return projects matching the filter (case-insensitive)
    assert len(data) == 2
    returned_keys = [project["key"] for project in data]
    # Project keys should always be uppercase in the response, regardless of input case
    assert "PROJ1" in returned_keys  # lowercase input converted to uppercase
    assert "PROJ2" in returned_keys  # uppercase stays uppercase
    assert "OTHER" not in returned_keys  # not in filter

    # Verify the underlying method was called
    mock_jira_fetcher.get_all_projects.assert_called_once_with(include_archived=False)


@pytest.mark.anyio
async def test_get_all_projects_tool_empty_response(jira_client, mock_jira_fetcher):
    """Test tool handles empty list of projects from API."""
    mock_jira_fetcher.get_all_projects.side_effect = lambda include_archived=False: []

    response = await jira_client.call_tool("jira_get_all_projects", {})

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert data == []


@pytest.mark.anyio
async def test_get_all_projects_tool_api_error_handling(jira_client, mock_jira_fetcher):
    """Test tool handles API errors gracefully."""
    from requests.exceptions import HTTPError

    mock_jira_fetcher.get_all_projects.side_effect = HTTPError("API Error")

    response = await jira_client.call_tool("jira_get_all_projects", {})

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert data["success"] is False
    assert "API Error" in data["error"]


@pytest.mark.anyio
async def test_get_all_projects_tool_authentication_error_handling(
    jira_client, mock_jira_fetcher
):
    """Test tool handles authentication errors gracefully."""
    from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

    mock_jira_fetcher.get_all_projects.side_effect = MCPAtlassianAuthenticationError(
        "Authentication failed"
    )

    response = await jira_client.call_tool("jira_get_all_projects", {})

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert data["success"] is False
    assert "Authentication/Permission Error" in data["error"]


@pytest.mark.anyio
async def test_get_all_projects_tool_configuration_error_handling(
    jira_client, mock_jira_fetcher
):
    """Test tool handles configuration errors gracefully."""
    mock_jira_fetcher.get_all_projects.side_effect = ValueError(
        "Jira client not configured"
    )

    response = await jira_client.call_tool("jira_get_all_projects", {})

    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert data["success"] is False
    assert "Configuration Error" in data["error"]


@pytest.mark.anyio
async def test_batch_create_versions_all_success(jira_client, mock_jira_fetcher):
    """Test batch creation of Jira versions where all succeed."""
    versions = [
        {
            "name": "v1.0",
            "startDate": "2025-01-01",
            "releaseDate": "2025-02-01",
            "description": "First release",
        },
        {"name": "v2.0", "description": "Second release"},
    ]
    # Patch create_project_version to always succeed
    mock_jira_fetcher.create_project_version.side_effect = lambda **kwargs: {
        "id": f"{kwargs['name']}-id",
        **kwargs,
    }
    response = await jira_client.call_tool(
        "jira_batch_create_versions",
        {"project_key": "TEST", "versions": json.dumps(versions)},
    )
    assert len(response.content) == 1
    content = json.loads(response.content[0].text)
    assert all(item["success"] for item in content)
    assert content[0]["version"]["name"] == "v1.0"
    assert content[1]["version"]["name"] == "v2.0"


@pytest.mark.anyio
async def test_batch_create_versions_partial_failure(jira_client, mock_jira_fetcher):
    """Test batch creation of Jira versions with some failures."""

    def side_effect(
        project_key, name, start_date=None, release_date=None, description=None
    ):
        if name == "bad":
            raise Exception("Simulated failure")
        return {"id": f"{name}-id", "name": name}

    mock_jira_fetcher.create_project_version.side_effect = side_effect
    versions = [
        {"name": "good1"},
        {"name": "bad"},
        {"name": "good2"},
    ]
    response = await jira_client.call_tool(
        "jira_batch_create_versions",
        {"project_key": "TEST", "versions": json.dumps(versions)},
    )
    content = json.loads(response.content[0].text)
    assert content[0]["success"] is True
    assert content[1]["success"] is False
    assert "Simulated failure" in content[1]["error"]
    assert content[2]["success"] is True


@pytest.mark.anyio
async def test_batch_create_versions_all_failure(jira_client, mock_jira_fetcher):
    """Test batch creation of Jira versions where all fail."""
    mock_jira_fetcher.create_project_version.side_effect = Exception("API down")
    versions = [
        {"name": "fail1"},
        {"name": "fail2"},
    ]
    response = await jira_client.call_tool(
        "jira_batch_create_versions",
        {"project_key": "TEST", "versions": json.dumps(versions)},
    )
    content = json.loads(response.content[0].text)
    assert all(not item["success"] for item in content)
    assert all("API down" in item["error"] for item in content)


@pytest.mark.anyio
async def test_batch_create_versions_empty(jira_client, mock_jira_fetcher):
    """Test batch creation of Jira versions with empty input."""
    response = await jira_client.call_tool(
        "jira_batch_create_versions",
        {"project_key": "TEST", "versions": json.dumps([])},
    )
    content = json.loads(response.content[0].text)
    assert content == []
