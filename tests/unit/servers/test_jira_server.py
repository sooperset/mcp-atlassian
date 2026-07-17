"""Unit tests for the Jira FastMCP server implementation."""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport
from fastmcp.exceptions import ToolError
from starlette.requests import Request

from src.mcp_atlassian.jira import JiraFetcher
from src.mcp_atlassian.jira.config import JiraConfig
from src.mcp_atlassian.models.jira import (
    JiraCustomerRequest,
    JiraRequestType,
    JiraRequestTypeField,
    JiraRequestTypeFieldsResult,
    JiraRequestTypesResult,
)
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
    mock_fetcher.get_remote_issue_links.return_value = []
    mock_fetcher.get_available_transitions.return_value = []
    mock_fetcher.get_issue_watchers.return_value = {"watchCount": 0, "watchers": []}
    mock_fetcher.get_worklogs.return_value = []

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

    # Configure update_issue
    def mock_update_issue(issue_key, **kwargs):
        mock_issue = MagicMock()
        mock_issue.to_simplified_dict.return_value = {
            "key": issue_key,
            "summary": "Updated Issue",
            "status": {"name": "Open"},
            **{k: v for k, v in kwargs.items() if k not in ("fields", "status")},
        }
        return mock_issue

    mock_fetcher.update_issue.side_effect = mock_update_issue

    # Configure assign_issue
    def mock_assign_issue(
        issue_key: str, assignee: str | dict[str, Any] | None = None
    ) -> MagicMock:
        mock_issue = MagicMock()
        mock_issue.to_simplified_dict.return_value = {
            "key": issue_key,
            "summary": "Test Issue",
            "status": {"name": "Open"},
            "assignee": (
                {"displayName": "Test User", "accountId": "test-account-id"}
                if assignee
                else None
            ),
        }
        return mock_issue

    mock_fetcher.assign_issue.side_effect = mock_assign_issue

    # Configure move_issue
    def mock_move_issue(issue_key: str, target_project_key: str) -> MagicMock:
        mock_issue = MagicMock()
        new_key = f"{target_project_key}-999"
        mock_issue.to_simplified_dict.return_value = {
            "key": new_key,
            "summary": "Moved Issue",
            "status": {"name": "In Progress"},
            "project": {"key": target_project_key},
        }
        return mock_issue

    mock_fetcher.move_issue.side_effect = mock_move_issue

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

    # Configure search_projects
    def mock_search_projects(query, max_results=20, current_project_ids=None):
        all_projects = [
            {
                "id": "10000",
                "key": "TEST",
                "name": "Test Project",
            },
            {
                "id": "10001",
                "key": "DEMO",
                "name": "Demo Project",
            },
        ]
        # Simple query filtering for test purposes
        results = [
            p
            for p in all_projects
            if query.upper() in p["key"] or query.lower() in p["name"].lower()
        ]
        if current_project_ids:
            exclude = set(current_project_ids)
            results = [p for p in results if p["id"] not in exclude]
        return results[:max_results]

    mock_fetcher.search_projects.side_effect = mock_search_projects

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

    mock_service_desk = MagicMock()
    mock_service_desk.to_simplified_dict.return_value = {
        "id": "4",
        "project_id": "10400",
        "project_key": "SUP",
        "project_name": "support",
        "links": {"self": "https://test.atlassian.net/rest/servicedeskapi/4"},
    }
    mock_fetcher.get_service_desk_for_project.return_value = mock_service_desk

    mock_service_desk_queues = MagicMock()
    mock_service_desk_queues.to_simplified_dict.return_value = {
        "service_desk_id": "4",
        "start": 0,
        "limit": 50,
        "size": 2,
        "is_last_page": True,
        "queues": [
            {"id": "47", "name": "Support Team", "issue_count": 11},
            {"id": "48", "name": "Waiting for customer", "issue_count": 33},
        ],
    }
    mock_fetcher.get_service_desk_queues.return_value = mock_service_desk_queues

    mock_queue_issues = MagicMock()
    mock_queue_issues.to_simplified_dict.return_value = {
        "service_desk_id": "4",
        "queue_id": "47",
        "start": 0,
        "limit": 2,
        "size": 2,
        "is_last_page": True,
        "queue": {"id": "47", "name": "Support Team", "issue_count": 11},
        "issues": [
            {"id": "1", "key": "SUP-1"},
            {"id": "2", "key": "SUP-2"},
        ],
    }
    mock_fetcher.get_queue_issues.return_value = mock_queue_issues

    # Configure add_comment
    mock_fetcher.add_comment.return_value = {
        "id": "10001",
        "body": "Test comment body",
        "created": "2024-01-01 10:00:00+00:00",
        "author": "Test User",
    }

    # Configure edit_comment
    mock_fetcher.edit_comment.return_value = {
        "id": "10001",
        "body": "Updated comment body",
        "updated": "2024-01-02 10:00:00+00:00",
        "author": "Test User",
    }

    # Configure add_worklog
    mock_fetcher.add_worklog.return_value = {
        "id": "10100",
        "comment": "Worked on feature",
        "created": "2024-01-01 10:00:00+00:00",
        "updated": "2024-01-01 10:00:00+00:00",
        "started": "2024-01-01 09:00:00+00:00",
        "time_spent": "1h 30m",
        "time_spent_seconds": 5400,
        "author": "Test User",
        "original_estimate_updated": False,
        "remaining_estimate_updated": False,
    }

    # Configure create_sprint
    mock_sprint = MagicMock()
    mock_sprint.to_simplified_dict.return_value = {
        "id": "100",
        "name": "Sprint 1",
        "state": "future",
        "start_date": "2024-01-01T00:00:00.000Z",
        "end_date": "2024-01-14T00:00:00.000Z",
    }
    mock_fetcher.create_sprint.return_value = mock_sprint

    # Configure update_sprint
    mock_updated_sprint = MagicMock()
    mock_updated_sprint.to_simplified_dict.return_value = {
        "id": "100",
        "name": "Sprint 1 - Renamed",
        "state": "active",
        "start_date": "2024-01-01T00:00:00.000Z",
        "end_date": "2024-01-14T00:00:00.000Z",
    }
    mock_fetcher.update_sprint.return_value = mock_updated_sprint

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
        add_issues_to_sprint,
        add_worklog,
        assign_issue,
        batch_create_issues,
        batch_create_versions,
        batch_get_changelogs,
        create_customer_request,
        create_issue,
        create_issue_link,
        create_remote_issue_link,
        create_sprint,
        delete_issue,
        download_attachments,
        edit_comment,
        get_agile_boards,
        get_all_projects,
        get_board_issues,
        get_create_fields,
        get_cross_project_dependencies,
        get_field_options,
        get_issue,
        get_issue_dates,
        get_issue_development_info,
        get_issue_images,
        get_issue_proforma_forms,
        get_issue_sla,
        get_issues_development_info,
        get_link_types,
        get_proforma_form_details,
        get_project_components,
        get_project_epic_hierarchy,
        get_project_fields,
        get_project_issue_types,
        get_project_issues,
        get_project_versions,
        get_queue_issues,
        get_request_type_fields,
        get_request_types,
        get_service_desk_for_project,
        get_service_desk_queues,
        get_sprint_issues,
        get_sprints_from_board,
        get_transitions,
        get_user_profile,
        get_worklog,
        link_to_epic,
        move_issue,
        move_issues_to_backlog,
        remove_issue_link,
        search,
        search_assignable_users,
        search_fields,
        search_projects,
        transition_issue,
        update_issue,
        update_proforma_form_answers,
        update_sprint,
        update_version,
    )

    jira_sub_mcp = FastMCP(name="TestJiraSubMCP")
    jira_sub_mcp.add_tool(get_issue)
    jira_sub_mcp.add_tool(get_issue_dates)
    jira_sub_mcp.add_tool(get_issue_development_info)
    jira_sub_mcp.add_tool(get_issue_proforma_forms)
    jira_sub_mcp.add_tool(get_issue_sla)
    jira_sub_mcp.add_tool(get_issues_development_info)
    jira_sub_mcp.add_tool(search)
    jira_sub_mcp.add_tool(search_fields)
    jira_sub_mcp.add_tool(get_project_issues)
    jira_sub_mcp.add_tool(get_project_versions)
    jira_sub_mcp.add_tool(get_project_components)
    jira_sub_mcp.add_tool(get_project_fields)
    jira_sub_mcp.add_tool(get_project_issue_types)
    jira_sub_mcp.add_tool(get_create_fields)
    jira_sub_mcp.add_tool(get_all_projects)
    jira_sub_mcp.add_tool(search_projects)
    jira_sub_mcp.add_tool(get_service_desk_for_project)
    jira_sub_mcp.add_tool(get_service_desk_queues)
    jira_sub_mcp.add_tool(get_queue_issues)
    jira_sub_mcp.add_tool(get_request_types)
    jira_sub_mcp.add_tool(get_request_type_fields)
    jira_sub_mcp.add_tool(get_transitions)
    jira_sub_mcp.add_tool(get_worklog)
    jira_sub_mcp.add_tool(download_attachments)
    jira_sub_mcp.add_tool(get_issue_images)
    jira_sub_mcp.add_tool(get_field_options)
    jira_sub_mcp.add_tool(get_cross_project_dependencies)
    jira_sub_mcp.add_tool(get_proforma_form_details)
    jira_sub_mcp.add_tool(get_project_epic_hierarchy)
    jira_sub_mcp.add_tool(get_agile_boards)
    jira_sub_mcp.add_tool(get_board_issues)
    jira_sub_mcp.add_tool(get_sprints_from_board)
    jira_sub_mcp.add_tool(get_sprint_issues)
    jira_sub_mcp.add_tool(get_link_types)
    jira_sub_mcp.add_tool(get_user_profile)
    jira_sub_mcp.add_tool(search_assignable_users)
    jira_sub_mcp.add_tool(create_issue)
    jira_sub_mcp.add_tool(create_customer_request)
    jira_sub_mcp.add_tool(batch_create_issues)
    jira_sub_mcp.add_tool(batch_get_changelogs)
    jira_sub_mcp.add_tool(update_issue)
    jira_sub_mcp.add_tool(assign_issue)
    jira_sub_mcp.add_tool(delete_issue)
    jira_sub_mcp.add_tool(move_issue)
    jira_sub_mcp.add_tool(move_issues_to_backlog)
    jira_sub_mcp.add_tool(add_comment)
    jira_sub_mcp.add_tool(edit_comment)
    jira_sub_mcp.add_tool(add_worklog)
    jira_sub_mcp.add_tool(link_to_epic)
    jira_sub_mcp.add_tool(create_issue_link)
    jira_sub_mcp.add_tool(create_remote_issue_link)
    jira_sub_mcp.add_tool(remove_issue_link)
    jira_sub_mcp.add_tool(transition_issue)
    jira_sub_mcp.add_tool(update_proforma_form_answers)
    jira_sub_mcp.add_tool(create_sprint)
    jira_sub_mcp.add_tool(update_sprint)
    jira_sub_mcp.add_tool(add_issues_to_sprint)
    jira_sub_mcp.add_tool(batch_create_versions)
    jira_sub_mcp.add_tool(update_version)
    test_mcp.mount(jira_sub_mcp, namespace="jira")
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
    test_mcp.mount(jira_sub_mcp, namespace="jira")
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
        expand=None,
        projects_filter=None,
        page_token=None,
    )


@pytest.mark.anyio
async def test_search_returns_error_details(jira_client, mock_jira_fetcher):
    """Test that search tool failures preserve the original error message."""
    mock_jira_fetcher.search_issues.side_effect = RuntimeError(
        "Jira JQL rejected the query"
    )

    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_search",
            {
                "jql": "project = TEST",
                "fields": "summary,status",
                "limit": 10,
                "start_at": 0,
            },
        )

    assert "Error calling tool 'search'" in str(excinfo.value)
    assert "Jira JQL rejected the query" in str(excinfo.value)


@pytest.mark.anyio
async def test_get_service_desk_for_project(jira_client, mock_jira_fetcher):
    """Test service desk lookup by project key."""
    response = await jira_client.call_tool(
        "jira_get_service_desk_for_project", {"project_key": "SUP"}
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0

    content = json.loads(response.content[0].text)
    assert content["project_key"] == "SUP"
    assert content["service_desk"]["id"] == "4"
    assert content["service_desk"]["project_key"] == "SUP"
    mock_jira_fetcher.get_service_desk_for_project.assert_called_once_with(
        project_key="SUP"
    )


@pytest.mark.anyio
async def test_get_service_desk_for_project_not_found(jira_client, mock_jira_fetcher):
    """Test service desk lookup returns null payload when not found."""
    mock_jira_fetcher.get_service_desk_for_project.return_value = None

    response = await jira_client.call_tool(
        "jira_get_service_desk_for_project", {"project_key": "SUP"}
    )
    content = json.loads(response.content[0].text)

    assert content["project_key"] == "SUP"
    assert content["service_desk"] is None


@pytest.mark.anyio
async def test_get_service_desk_queues(jira_client, mock_jira_fetcher):
    """Test queue listing for a service desk."""
    response = await jira_client.call_tool(
        "jira_get_service_desk_queues",
        {"service_desk_id": "4", "start_at": 0, "limit": 50},
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0

    content = json.loads(response.content[0].text)
    assert content["service_desk_id"] == "4"
    assert content["size"] == 2
    assert content["queues"][0]["id"] == "47"
    mock_jira_fetcher.get_service_desk_queues.assert_called_once_with(
        service_desk_id="4",
        start_at=0,
        limit=50,
        include_count=True,
    )


@pytest.mark.anyio
async def test_get_queue_issues(jira_client, mock_jira_fetcher):
    """Test queue issue retrieval."""
    response = await jira_client.call_tool(
        "jira_get_queue_issues",
        {"service_desk_id": "4", "queue_id": "47", "start_at": 0, "limit": 2},
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0

    content = json.loads(response.content[0].text)
    assert content["service_desk_id"] == "4"
    assert content["queue_id"] == "47"
    assert content["size"] == 2
    assert content["issues"][0]["key"] == "SUP-1"
    mock_jira_fetcher.get_queue_issues.assert_called_once_with(
        service_desk_id="4",
        queue_id="47",
        start_at=0,
        limit=2,
    )


@pytest.mark.anyio
async def test_get_request_types(jira_client, mock_jira_fetcher):
    """Test request type listing for a service desk."""
    mock_jira_fetcher.get_request_types.return_value = JiraRequestTypesResult(
        service_desk_id="4",
        size=2,
        request_types=[
            JiraRequestType(id="23", name="Incident"),
            JiraRequestType(id="24", name="Access Request"),
        ],
    )

    response = await jira_client.call_tool(
        "jira_get_request_types",
        {"service_desk_id": "4", "start_at": 0, "limit": 50},
    )
    content = json.loads(response.content[0].text)

    assert content["service_desk_id"] == "4"
    assert content["size"] == 2
    assert content["request_types"][0]["id"] == "23"
    mock_jira_fetcher.get_request_types.assert_called_once_with(
        service_desk_id="4",
        start_at=0,
        limit=50,
    )


@pytest.mark.anyio
async def test_get_request_type_fields(jira_client, mock_jira_fetcher):
    """Test request type field discovery."""
    mock_jira_fetcher.get_request_type_fields.return_value = (
        JiraRequestTypeFieldsResult(
            service_desk_id="4",
            request_type_id="23",
            can_raise_on_behalf_of=True,
            fields=[
                JiraRequestTypeField(
                    field_id="summary",
                    name="Summary",
                    required=True,
                    supports_multiple=False,
                )
            ],
        )
    )

    response = await jira_client.call_tool(
        "jira_get_request_type_fields",
        {"service_desk_id": "4", "request_type_id": "23"},
    )
    content = json.loads(response.content[0].text)

    assert content["service_desk_id"] == "4"
    assert content["request_type_id"] == "23"
    assert content["can_raise_on_behalf_of"] is True
    assert content["fields"][0]["field_id"] == "summary"
    mock_jira_fetcher.get_request_type_fields.assert_called_once_with(
        service_desk_id="4",
        request_type_id="23",
    )


@pytest.mark.anyio
async def test_create_customer_request(jira_client, mock_jira_fetcher):
    """Test customer request creation tool."""
    mock_jira_fetcher.create_customer_request.return_value = JiraCustomerRequest(
        request_id="10010",
        request_key="SUP-101",
        portal_url="https://jira.example.com/servicedesk/customer/portal/4/SUP-101",
        created_mode="created_on_behalf_of",
        on_behalf_user="d.zagitov",
    )

    response = await jira_client.call_tool(
        "jira_create_customer_request",
        {
            "service_desk_id": "4",
            "request_type_id": "23",
            "request_field_values": '{"summary": "Production incident"}',
            "raise_on_behalf_of": "d.zagitov",
            "strict_on_behalf": False,
        },
    )
    content = json.loads(response.content[0].text)

    assert content["request_id"] == "10010"
    assert content["request_key"] == "SUP-101"
    assert content["created_mode"] == "created_on_behalf_of"
    assert content["on_behalf_user"] == "d.zagitov"
    mock_jira_fetcher.create_customer_request.assert_called_once_with(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={"summary": "Production incident"},
        raise_on_behalf_of="d.zagitov",
        request_participants=None,
        attachments=None,
        strict_on_behalf=False,
    )


@pytest.mark.anyio
async def test_create_customer_request_with_attachments(jira_client, mock_jira_fetcher):
    """Customer request tool should forward parsed base64 attachments."""
    mock_jira_fetcher.create_customer_request.return_value = JiraCustomerRequest(
        request_id="10010",
        request_key="SUP-101",
        created_mode="created_direct",
    )

    response = await jira_client.call_tool(
        "jira_create_customer_request",
        {
            "service_desk_id": "4",
            "request_type_id": "23",
            "request_field_values": '{"summary": "Production incident"}',
            "attachments": (
                '[{"filename": "log.txt", "mime_type": "text/plain", '
                '"base64": "aGVsbG8="}]'
            ),
        },
    )
    content = json.loads(response.content[0].text)

    assert content["request_key"] == "SUP-101"
    mock_jira_fetcher.create_customer_request.assert_called_once_with(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={"summary": "Production incident"},
        raise_on_behalf_of=None,
        request_participants=None,
        attachments=[
            {"filename": "log.txt", "mime_type": "text/plain", "base64": "aGVsbG8="}
        ],
        strict_on_behalf=False,
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
            "additional_fields": '{"priority": {"name": "Medium"}}',
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
@pytest.mark.parametrize(
    ("tool_arguments", "expected_link_data"),
    [
        pytest.param(
            {
                "issue_key": "TEST-123",
                "url": "https://example.com/documentation",
                "title": "Project documentation",
            },
            {
                "object": {
                    "url": "https://example.com/documentation",
                    "title": "Project documentation",
                }
            },
            id="web-link",
        ),
        pytest.param(
            {
                "issue_key": "TEST-123",
                "url": (
                    "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456/Plan"
                ),
                "title": "Team plan",
                "summary": "Planning notes",
                "relationship": "documentation",
                "icon_url": "https://example.atlassian.net/favicon.ico",
            },
            {
                "object": {
                    "url": (
                        "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456/Plan"
                    ),
                    "title": "Team plan",
                    "summary": "Planning notes",
                    "icon": {
                        "url16x16": "https://example.atlassian.net/favicon.ico",
                        "title": "Team plan",
                    },
                },
                "relationship": "documentation",
            },
            id="confluence-link",
        ),
    ],
)
async def test_create_remote_issue_link(
    jira_client,
    mock_jira_fetcher,
    tool_arguments: dict[str, str],
    expected_link_data: dict[str, Any],
) -> None:
    """Regression test for creating web and Confluence links (#240)."""
    mock_jira_fetcher.create_remote_issue_link.return_value = {"success": True}

    response = await jira_client.call_tool(
        "jira_create_remote_issue_link",
        tool_arguments,
    )

    assert json.loads(response.content[0].text) == {"success": True}
    mock_jira_fetcher.create_remote_issue_link.assert_called_once_with(
        "TEST-123", expected_link_data
    )


@pytest.mark.anyio
async def test_create_issue_accepts_json_string(jira_client, mock_jira_fetcher):
    """Ensure additional_fields can be a JSON string."""
    response = await jira_client.call_tool(
        "jira_create_issue",
        {
            "project_key": "TEST",
            "summary": "JSON Issue",
            "issue_type": "Task",
            "additional_fields": '{"labels": ["ai", "test"]}',
        },
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    text_content = response.content[0]
    assert text_content.type == "text"
    content = json.loads(text_content.text)
    assert content["message"] == "Issue created successfully"
    assert "issue" in content
    mock_jira_fetcher.create_issue.assert_called_with(
        project_key="TEST",
        summary="JSON Issue",
        issue_type="Task",
        description=None,
        assignee=None,
        components=None,
        labels=["ai", "test"],
    )


@pytest.mark.anyio
async def test_create_issue_additional_fields_empty_string(jira_client):
    """Test that empty string additional_fields raises ToolError."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_create_issue",
            {
                "project_key": "TEST",
                "summary": "Test issue",
                "issue_type": "Task",
                "additional_fields": "",
            },
        )
    assert "not valid JSON" in str(excinfo.value)


@pytest.mark.anyio
async def test_create_issue_additional_fields_invalid_json(jira_client):
    """Test that invalid JSON additional_fields raises ToolError."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_create_issue",
            {
                "project_key": "TEST",
                "summary": "Test issue",
                "issue_type": "Task",
                "additional_fields": "{invalid json",
            },
        )
    assert "not valid JSON" in str(excinfo.value)


@pytest.mark.anyio
async def test_create_issue_additional_fields_non_dict_json(jira_client):
    """Test that JSON array additional_fields raises ToolError."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_create_issue",
            {
                "project_key": "TEST",
                "summary": "Test issue",
                "issue_type": "Task",
                "additional_fields": '["item1", "item2"]',
            },
        )
    assert "not a JSON object" in str(excinfo.value)


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
    assert "Invalid JSON" in str(excinfo.value)


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
async def test_search_assignable_users_tool_success(jira_client, mock_jira_fetcher):
    """Test the search_assignable_users tool returns assignable users."""
    user = MagicMock()
    user.to_simplified_dict.return_value = {
        "account_id": "5b10ac8d82e05b22cc7d4ef5",
        "display_name": "John Smith",
        "name": "jsmith",
        "email": "jsmith@example.com",
    }
    mock_jira_fetcher.search_assignable_users.return_value = [user]

    response = await jira_client.call_tool(
        "jira_search_assignable_users",
        {"query": "Smith", "project_key": "TEST", "limit": 5},
    )

    mock_jira_fetcher.search_assignable_users.assert_called_once_with(
        query="Smith",
        project_key="TEST",
        issue_key=None,
        limit=5,
    )
    result_data = json.loads(response.content[0].text)
    assert result_data == {
        "success": True,
        "count": 1,
        "users": [
            {
                "account_id": "5b10ac8d82e05b22cc7d4ef5",
                "display_name": "John Smith",
                "name": "jsmith",
                "email": "jsmith@example.com",
            }
        ],
    }


@pytest.mark.anyio
async def test_search_assignable_users_tool_requires_scope(
    jira_client, mock_jira_fetcher
):
    """Test search_assignable_users requires project_key or issue_key."""
    response = await jira_client.call_tool(
        "jira_search_assignable_users",
        {"query": "Smith"},
    )

    mock_jira_fetcher.search_assignable_users.assert_not_called()
    result_data = json.loads(response.content[0].text)
    assert result_data["success"] is False
    assert "project_key or issue_key" in result_data["error"]
    assert result_data["query"] == "Smith"


@pytest.mark.anyio
async def test_search_assignable_users_tool_rejects_multiple_scopes(
    jira_client, mock_jira_fetcher
):
    """Test search_assignable_users rejects ambiguous project and issue scopes."""
    response = await jira_client.call_tool(
        "jira_search_assignable_users",
        {"query": "Smith", "project_key": "TEST", "issue_key": "TEST-1"},
    )

    mock_jira_fetcher.search_assignable_users.assert_not_called()
    result_data = json.loads(response.content[0].text)
    assert result_data["success"] is False
    assert "Exactly one" in result_data["error"]
    assert result_data["query"] == "Smith"


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
    assert "Jira client (fetcher) not available" in str(excinfo.value)


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
                {"issue_key": "USRST-1", "fields": test_fields_str},
            )

    mock_get_http.assert_called()
    mock_jira_fetcher.get_issue.assert_called_with(
        issue_key="USRST-1",
        fields=expected_fields_list,
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    )
    result_data = json.loads(response.content[0].text)
    assert result_data["key"] == "USRST-1"


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
async def test_get_project_components_tool(jira_client, mock_jira_fetcher):
    """Test the jira_get_project_components tool returns component list."""
    mock_components = [
        {"id": "10000", "name": "Backend", "description": "Backend services"},
        {"id": "10001", "name": "Frontend", "description": "UI components"},
    ]
    mock_jira_fetcher.get_project_components.return_value = mock_components

    response = await jira_client.call_tool(
        "jira_get_project_components",
        {"project_key": "TEST"},
    )
    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"
    import json

    data = json.loads(msg.text)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == "10000"
    assert data[0]["name"] == "Backend"


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
    mock_jira_fetcher.get_all_projects.side_effect = lambda include_archived=False: (
        mock_projects
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
    mock_jira_fetcher.get_all_projects.side_effect = lambda include_archived=False: (
        mock_projects
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
    mock_jira_fetcher.get_all_projects.side_effect = lambda include_archived=False: (
        all_mock_projects
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
    mock_jira_fetcher.get_all_projects.side_effect = lambda include_archived=False: (
        all_mock_projects
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
    mock_jira_fetcher.get_all_projects.side_effect = lambda include_archived=False: (
        all_mock_projects
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
async def test_search_projects_tool(jira_client, mock_jira_fetcher):
    """Test the jira_search_projects tool returns matching projects."""
    mock_jira_fetcher.search_projects.reset_mock()
    mock_jira_fetcher.search_projects.side_effect = (
        lambda query, max_results=20, current_project_ids=None: [
            {"id": "10000", "key": "test", "name": "Test Project"},
        ]
    )

    response = await jira_client.call_tool(
        "jira_search_projects",
        {"query": "Test"},
    )
    assert hasattr(response, "content")
    assert len(response.content) == 1
    msg = response.content[0]
    assert msg.type == "text"

    data = json.loads(msg.text)
    assert len(data) == 1
    assert data[0]["key"] == "TEST"
    assert data[0]["name"] == "Test Project"

    mock_jira_fetcher.search_projects.assert_called_once_with(
        query="Test",
        max_results=20,
        current_project_ids=None,
    )


@pytest.mark.anyio
async def test_search_projects_tool_with_all_params(jira_client, mock_jira_fetcher):
    """Test the jira_search_projects tool with all parameters."""
    mock_jira_fetcher.search_projects.reset_mock()
    mock_jira_fetcher.search_projects.side_effect = (
        lambda query, max_results=20, current_project_ids=None: [
            {"id": "10001", "key": "demo", "name": "Demo Project"},
        ]
    )

    response = await jira_client.call_tool(
        "jira_search_projects",
        {
            "query": "Demo",
            "max_results": 5,
            "current_project_ids": "10000, 10002",
        },
    )
    assert hasattr(response, "content")
    data = json.loads(response.content[0].text)
    assert len(data) == 1
    assert data[0]["key"] == "DEMO"

    mock_jira_fetcher.search_projects.assert_called_once_with(
        query="Demo",
        max_results=5,
        current_project_ids=["10000", "10002"],
    )


@pytest.mark.anyio
async def test_search_projects_tool_empty_response(jira_client, mock_jira_fetcher):
    """Test tool handles empty results."""
    mock_jira_fetcher.search_projects.reset_mock()
    mock_jira_fetcher.search_projects.side_effect = (
        lambda query, max_results=20, current_project_ids=None: []
    )

    response = await jira_client.call_tool(
        "jira_search_projects", {"query": "nonexistent"}
    )
    data = json.loads(response.content[0].text)
    assert data == []


@pytest.mark.anyio
async def test_search_projects_tool_api_error_handling(jira_client, mock_jira_fetcher):
    """Test tool handles API errors gracefully."""
    from requests.exceptions import HTTPError

    mock_jira_fetcher.search_projects.side_effect = HTTPError("API Error")

    response = await jira_client.call_tool("jira_search_projects", {"query": "test"})
    data = json.loads(response.content[0].text)
    assert data["success"] is False
    assert "Network or API Error" in data["error"]


@pytest.mark.anyio
async def test_search_projects_tool_authentication_error_handling(
    jira_client, mock_jira_fetcher
):
    """Test tool handles authentication errors gracefully."""
    from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

    mock_jira_fetcher.search_projects.side_effect = MCPAtlassianAuthenticationError(
        "Authentication failed"
    )

    response = await jira_client.call_tool("jira_search_projects", {"query": "test"})
    data = json.loads(response.content[0].text)
    assert data["success"] is False
    assert "Authentication/Permission Error" in data["error"]


@pytest.mark.anyio
async def test_get_project_issue_types_tool(jira_client, mock_jira_fetcher):
    """Test jira_get_project_issue_types returns compact discovery metadata."""
    mock_jira_fetcher.get_project_issue_types.return_value = [
        {
            "self": "https://example.atlassian.net/rest/api/2/issuetype/10000",
            "id": 10000,
            "name": "Epic",
            "untranslatedName": "Epic",
            "description": "A large body of work.",
            "iconUrl": "https://example.atlassian.net/icon.svg",
            "subtask": False,
            "hierarchyLevel": 1,
        }
    ]

    response = await jira_client.call_tool(
        "jira_get_project_issue_types",
        {"project_key": "TEST"},
    )

    mock_jira_fetcher.get_project_issue_types.assert_called_once_with("TEST")
    data = json.loads(response.content[0].text)
    assert data == [
        {
            "id": "10000",
            "name": "Epic",
            "description": "A large body of work.",
            "subtask": False,
            "untranslated_name": "Epic",
        }
    ]


@pytest.mark.anyio
async def test_get_create_fields_tool(jira_client, mock_jira_fetcher):
    """Test jira_get_create_fields returns compact per-type field metadata."""
    mock_jira_fetcher.get_create_fields.return_value = [
        {
            "fieldId": "summary",
            "name": "Summary",
            "required": True,
            "schema": {"type": "string", "system": "summary"},
            "operations": ["set"],
        }
    ]

    response = await jira_client.call_tool(
        "jira_get_create_fields",
        {"project_key": "TEST", "issue_type_id": "10000"},
    )

    mock_jira_fetcher.get_create_fields.assert_called_once_with("TEST", "10000")
    data = json.loads(response.content[0].text)
    assert data == [
        {
            "field_id": "summary",
            "name": "Summary",
            "required": True,
            "schema": {"type": "string", "system": "summary"},
        }
    ]


@pytest.mark.anyio
async def test_get_project_fields_tool(jira_client, mock_jira_fetcher):
    """Test the jira_get_project_fields tool returns project field schema."""
    mock_fields = [
        {
            "field_id": "summary",
            "name": "Summary",
            "required": True,
            "schema_type": "string",
            "custom": False,
            "issue_types": ["Bug", "Task"],
        }
    ]
    mock_jira_fetcher.get_project_fields.return_value = mock_fields

    response = await jira_client.call_tool(
        "jira_get_project_fields",
        {"project_key": "TEST"},
    )

    mock_jira_fetcher.get_project_fields.assert_called_once_with("TEST")
    data = json.loads(response.content[0].text)
    assert data == mock_fields


@pytest.mark.anyio
async def test_get_project_fields_tool_configuration_error(
    jira_client, mock_jira_fetcher
):
    """Test jira_get_project_fields handles configuration errors."""
    mock_jira_fetcher.get_project_fields.side_effect = ValueError(
        "Jira client not configured"
    )

    response = await jira_client.call_tool(
        "jira_get_project_fields",
        {"project_key": "TEST"},
    )

    data = json.loads(response.content[0].text)
    assert data["success"] is False
    assert data["project_key"] == "TEST"
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


@pytest.mark.anyio
async def test_update_version_success(jira_client, mock_jira_fetcher):
    """Test updating a Jira version forwards provided fields."""
    mock_jira_fetcher.update_project_version.return_value = {
        "id": "10001",
        "name": "v1.0-renamed",
        "archived": False,
    }

    response = await jira_client.call_tool(
        "jira_update_version",
        {
            "version_id": "10001",
            "name": "v1.0-renamed",
            "archived": False,
        },
    )

    content = json.loads(response.content[0].text)
    assert content == {
        "id": "10001",
        "name": "v1.0-renamed",
        "archived": False,
    }
    mock_jira_fetcher.update_project_version.assert_called_once_with(
        version_id="10001",
        name="v1.0-renamed",
        description=None,
        start_date=None,
        release_date=None,
        archived=False,
        released=None,
    )


@pytest.mark.anyio
async def test_update_version_error(jira_client, mock_jira_fetcher):
    """Test updating a Jira version returns an error payload on failure."""
    mock_jira_fetcher.update_project_version.side_effect = ValueError(
        "update_version requires at least one field to update"
    )

    response = await jira_client.call_tool(
        "jira_update_version",
        {"version_id": "10001"},
    )

    content = json.loads(response.content[0].text)
    assert content == {
        "success": False,
        "error": "update_version requires at least one field to update",
    }


# Regression tests for issue #883: project keys with 4+ characters
# https://github.com/sooperset/mcp-atlassian/issues/883


@pytest.mark.anyio
async def test_get_issue_long_project_key(jira_client, mock_jira_fetcher):
    """Regression test for #883: 4-character project keys with digits should work."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "ACV2-642"},
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    content = json.loads(response.content[0].text)
    assert content["key"] == "ACV2-642"
    mock_jira_fetcher.get_issue.assert_called_once()


@pytest.mark.anyio
async def test_get_issue_five_char_project_key(jira_client, mock_jira_fetcher):
    """Regression test for #883: 5-character project keys should work."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "CMSV2-1"},
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    content = json.loads(response.content[0].text)
    assert content["key"] == "CMSV2-1"


@pytest.mark.anyio
async def test_get_issue_min_length_project_key(jira_client, mock_jira_fetcher):
    """Test minimum length (2-character) project keys still work."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "AB-1"},
    )
    assert hasattr(response, "content")
    content = json.loads(response.content[0].text)
    assert content["key"] == "AB-1"


@pytest.mark.anyio
async def test_get_issue_max_length_project_key(jira_client, mock_jira_fetcher):
    """Test maximum length (10-character) project keys work."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "ABCDEFGHIJ-99"},
    )
    assert hasattr(response, "content")
    content = json.loads(response.content[0].text)
    assert content["key"] == "ABCDEFGHIJ-99"


@pytest.mark.anyio
async def test_get_project_issues_long_key(jira_client, mock_jira_fetcher):
    """Regression test for #883: get_project_issues with 4+ char project key."""
    mock_search_result = MagicMock()
    mock_search_result.to_simplified_dict.return_value = {
        "total": 0,
        "start_at": 0,
        "max_results": 10,
        "issues": [],
    }
    mock_jira_fetcher.get_project_issues.return_value = mock_search_result

    response = await jira_client.call_tool(
        "jira_get_project_issues",
        {"project_key": "CMSV2"},
    )
    assert hasattr(response, "content")
    content = json.loads(response.content[0].text)
    assert content["total"] == 0
    mock_jira_fetcher.get_project_issues.assert_called_once_with(
        project_key="CMSV2", start=0, limit=10
    )


def test_issue_key_pattern_validation():
    """Verify the issue key and project key regex patterns accept valid keys."""
    import re

    from src.mcp_atlassian.servers.jira import ISSUE_KEY_PATTERN, PROJECT_KEY_PATTERN

    # Valid issue keys
    assert re.match(ISSUE_KEY_PATTERN, "PROJ-123")
    assert re.match(ISSUE_KEY_PATTERN, "ACV2-642")
    assert re.match(ISSUE_KEY_PATTERN, "CMSV2-1")
    assert re.match(ISSUE_KEY_PATTERN, "AB-1")
    assert re.match(ISSUE_KEY_PATTERN, "ABCDEFGHIJ-99")
    assert re.match(ISSUE_KEY_PATTERN, "D_DEV-123")
    assert re.match(ISSUE_KEY_PATTERN, "MY_PROJECT-1")
    assert re.match(ISSUE_KEY_PATTERN, "B7-214-68901")
    assert re.match(ISSUE_KEY_PATTERN, "PRJ-1-2-3")
    # Invalid issue keys
    assert not re.match(ISSUE_KEY_PATTERN, "a-1")
    assert not re.match(ISSUE_KEY_PATTERN, "PROJ")
    assert not re.match(ISSUE_KEY_PATTERN, "2ABC-1")
    assert not re.match(ISSUE_KEY_PATTERN, "A-1-2")
    assert not re.match(ISSUE_KEY_PATTERN, "B7-214--68901")
    assert not re.match(ISSUE_KEY_PATTERN, "B7-214-")
    assert not re.match(ISSUE_KEY_PATTERN, "B7-214-68901A")

    # Valid project keys
    assert re.match(PROJECT_KEY_PATTERN, "PROJ")
    assert re.match(PROJECT_KEY_PATTERN, "ACV2")
    assert re.match(PROJECT_KEY_PATTERN, "CMSV2")
    assert re.match(PROJECT_KEY_PATTERN, "AB")
    assert re.match(PROJECT_KEY_PATTERN, "ABCDEFGHIJ")
    assert re.match(PROJECT_KEY_PATTERN, "D_DEV")
    assert re.match(PROJECT_KEY_PATTERN, "MY_PROJECT")
    # Invalid project keys
    assert not re.match(PROJECT_KEY_PATTERN, "a")
    assert not re.match(PROJECT_KEY_PATTERN, "2ABC")
    assert not re.match(PROJECT_KEY_PATTERN, "A")


def test_issue_and_project_key_patterns_accept_long_server_dc_keys():
    import re

    from src.mcp_atlassian.servers.jira import ISSUE_KEY_PATTERN, PROJECT_KEY_PATTERN

    assert re.match(ISSUE_KEY_PATTERN, "VERYLONGPROJECTKEY-123")
    assert re.match(PROJECT_KEY_PATTERN, "VERYLONGPROJECTKEY")


def test_issue_and_project_key_patterns_reject_invalid_keys():
    import re

    from src.mcp_atlassian.servers.jira import ISSUE_KEY_PATTERN, PROJECT_KEY_PATTERN

    assert not re.match(ISSUE_KEY_PATTERN, "lowercase-123")
    assert not re.match(ISSUE_KEY_PATTERN, "123-456")
    assert not re.match(ISSUE_KEY_PATTERN, "-123")

    assert not re.match(PROJECT_KEY_PATTERN, "lowercase")
    assert not re.match(PROJECT_KEY_PATTERN, "123")


# =============================================================================
# update_issue additional_fields JSON string tests
# =============================================================================


@pytest.mark.anyio
async def test_update_issue_accepts_json_string_fields(jira_client, mock_jira_fetcher):
    """Regression: fields must accept a JSON string (not just a dict).

    d57b7fd narrowed all dict-typed tool params to str for AI platform
    schema compatibility but missed the fields param in update_issue,
    causing a Pydantic validation error when an LLM passed a JSON string.
    """
    response = await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated via JSON string"}',
        },
    )
    content = json.loads(response.content[0].text)
    assert content["message"] == "Issue updated successfully"
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert call_kwargs["summary"] == "Updated via JSON string"


@pytest.mark.anyio
async def test_update_issue_accepts_json_string_additional_fields(
    jira_client, mock_jira_fetcher
):
    """Ensure update_issue additional_fields can be a JSON string."""
    response = await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "additional_fields": '{"labels": ["ai"]}',
        },
    )
    assert hasattr(response, "content")
    assert len(response.content) > 0
    text_content = response.content[0]
    assert text_content.type == "text"
    content = json.loads(text_content.text)
    assert content["message"] == "Issue updated successfully"
    assert "issue" in content


@pytest.mark.anyio
async def test_update_issue_additional_fields_invalid_json(jira_client):
    """Test that invalid JSON additional_fields raises ToolError."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_update_issue",
            {
                "issue_key": "TEST-123",
                "fields": '{"summary": "Updated"}',
                "additional_fields": "{invalid",
            },
        )
    assert "not valid JSON" in str(excinfo.value)


@pytest.mark.anyio
async def test_update_issue_additional_fields_non_dict_json(jira_client):
    """Test that JSON array additional_fields raises ToolError."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_update_issue",
            {
                "issue_key": "TEST-123",
                "fields": '{"summary": "Updated"}',
                "additional_fields": '["a","b"]',
            },
        )
    assert "not a JSON object" in str(excinfo.value)


@pytest.mark.anyio
async def test_update_issue_additional_fields_empty_string(jira_client):
    """Test that empty string additional_fields raises ToolError."""
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_update_issue",
            {
                "issue_key": "TEST-123",
                "fields": '{"summary": "Updated"}',
                "additional_fields": "",
            },
        )
    assert "not valid JSON" in str(excinfo.value)


@pytest.mark.anyio
async def test_update_issue_with_components(jira_client, mock_jira_fetcher):
    """Test components CSV param is parsed and passed to update_issue."""
    response = await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "components": "Frontend,API",
        },
    )
    text_content = response.content[0]
    content = json.loads(text_content.text)
    assert content["message"] == "Issue updated successfully"
    # Verify components were passed to the fetcher
    mock_jira_fetcher.update_issue.assert_called_once()
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert call_kwargs["components"] == ["Frontend", "API"]


@pytest.mark.anyio
async def test_update_issue_with_components_single(jira_client, mock_jira_fetcher):
    """Test single component is parsed as single-item list."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "components": "Frontend",
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert call_kwargs["components"] == ["Frontend"]


@pytest.mark.anyio
async def test_update_issue_with_components_empty(jira_client, mock_jira_fetcher):
    """Test empty components string is not passed to update_issue."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "components": "",
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert "components" not in call_kwargs


@pytest.mark.anyio
async def test_update_issue_with_components_none(jira_client, mock_jira_fetcher):
    """Test None components (default) is not passed to update_issue."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert "components" not in call_kwargs


@pytest.mark.anyio
async def test_update_issue_components_with_additional_fields(
    jira_client, mock_jira_fetcher
):
    """Test components param merged with additional_fields; components takes precedence."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "components": "Frontend,API",
            "additional_fields": '{"labels": ["urgent"], "components": ["Backend"]}',
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    # Explicit components param should override additional_fields
    assert call_kwargs["components"] == ["Frontend", "API"]
    assert call_kwargs["labels"] == ["urgent"]


@pytest.mark.anyio
async def test_update_issue_passes_return_fields(jira_client, mock_jira_fetcher):
    """return_fields CSV is parsed to a list and forwarded to update_issue."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "return_fields": "summary,duedate",
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert call_kwargs["return_fields"] == ["summary", "duedate"]


@pytest.mark.anyio
async def test_update_issue_return_fields_all(jira_client, mock_jira_fetcher):
    """return_fields='*all' is forwarded verbatim (not split into a list)."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
            "return_fields": "*all",
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert call_kwargs["return_fields"] == "*all"


@pytest.mark.anyio
async def test_update_issue_default_return_fields(jira_client, mock_jira_fetcher):
    """Omitting return_fields defaults to '*all' (backward-compatible full issue)."""
    await jira_client.call_tool(
        "jira_update_issue",
        {
            "issue_key": "TEST-123",
            "fields": '{"summary": "Updated"}',
        },
    )
    call_kwargs = mock_jira_fetcher.update_issue.call_args[1]
    assert call_kwargs["return_fields"] == "*all"


# --- Tests for download_attachments 50 MB size limit ---


@pytest.mark.anyio
async def test_download_attachments_skips_oversized_at_server_layer(
    jira_client, mock_jira_fetcher
):
    """Server-layer fallback: attachment data bytes > 50MB are caught."""
    oversized_data = b"x" * (50 * 1024 * 1024 + 1)

    mock_jira_fetcher.get_issue_attachment_contents.return_value = {
        "success": True,
        "issue_key": "TEST-123",
        "total": 1,
        "attachments": [
            {
                "filename": "huge.bin",
                "content_type": "application/octet-stream",
                "size": len(oversized_data),
                "data": oversized_data,
            }
        ],
        "failed": [],
    }

    response = await jira_client.call_tool(
        "jira_download_attachments",
        {"issue_key": "TEST-123"},
    )

    # The summary text should be first
    summary = json.loads(response.content[0].text)
    assert summary["success"] is True
    # The oversized attachment should be in the failed list, not embedded
    assert len(summary["failed"]) == 1
    assert "50 MB" in summary["failed"][0]["error"]
    # No EmbeddedResource should be returned for the oversized attachment
    assert len(response.content) == 1  # Only the text summary, no resource


@pytest.mark.anyio
async def test_download_attachments_allows_normal_size(jira_client, mock_jira_fetcher):
    """Normal-size attachments pass through fine at server layer."""
    normal_data = b"normal content"

    mock_jira_fetcher.get_issue_attachment_contents.return_value = {
        "success": True,
        "issue_key": "TEST-123",
        "total": 1,
        "attachments": [
            {
                "filename": "small.txt",
                "content_type": "text/plain",
                "size": len(normal_data),
                "data": normal_data,
            }
        ],
        "failed": [],
    }

    response = await jira_client.call_tool(
        "jira_download_attachments",
        {"issue_key": "TEST-123"},
    )

    summary = json.loads(response.content[0].text)
    assert summary["success"] is True
    assert summary["downloaded"] == 1
    assert len(summary["failed"]) == 0
    # Should have text summary + 1 non-image attachment payload (TextContent)
    assert len(response.content) == 2


@pytest.mark.anyio
async def test_download_attachments_binary_uses_text_content(
    jira_client, mock_jira_fetcher
):
    """Non-image attachments (e.g. .zip) must be returned as TextContent
    carrying a base64 payload, not as an EmbeddedResource blob -- many MCP
    clients reject non-image EmbeddedResource mime types outright (#1419)."""
    import base64

    zip_data = b"PK\x03\x04fake zip bytes"

    mock_jira_fetcher.get_issue_attachment_contents.return_value = {
        "success": True,
        "issue_key": "TEST-123",
        "total": 1,
        "attachments": [
            {
                "filename": "archive.zip",
                "content_type": "application/zip",
                "size": len(zip_data),
                "data": zip_data,
            }
        ],
        "failed": [],
    }

    response = await jira_client.call_tool(
        "jira_download_attachments",
        {"issue_key": "TEST-123"},
    )

    assert len(response.content) == 2
    payload_content = response.content[1]
    # Must be TextContent (type="text"), not an EmbeddedResource (type="resource")
    assert payload_content.type == "text"
    payload = json.loads(payload_content.text)
    assert payload["success"] is True
    assert payload["filename"] == "archive.zip"
    assert payload["mime_type"] == "application/zip"
    assert payload["encoding"] == "base64"
    assert base64.b64decode(payload["content"]) == zip_data


@pytest.mark.anyio
async def test_download_attachments_image_still_uses_embedded_resource(
    jira_client, mock_jira_fetcher
):
    """Image attachments must keep going through EmbeddedResource -- only
    the non-image path changes for #1419."""
    image_data = b"\x89PNG\r\n\x1a\nfake png bytes"

    mock_jira_fetcher.get_issue_attachment_contents.return_value = {
        "success": True,
        "issue_key": "TEST-123",
        "total": 1,
        "attachments": [
            {
                "filename": "screenshot.png",
                "content_type": "image/png",
                "size": len(image_data),
                "data": image_data,
            }
        ],
        "failed": [],
    }

    response = await jira_client.call_tool(
        "jira_download_attachments",
        {"issue_key": "TEST-123"},
    )

    assert len(response.content) == 2
    resource_content = response.content[1]
    # Must be EmbeddedResource (type="resource"), unchanged from before #1419
    assert resource_content.type == "resource"
    assert resource_content.resource.mimeType == "image/png"


# ── jira_get_issue_images tests ──────────────────────────────────────


@pytest.mark.anyio
async def test_get_issue_images_basic(jira_client, mock_jira_fetcher):
    """Test with a mix of image and non-image attachments."""
    from mcp_atlassian.models.jira import JiraAttachment

    mock_jira_fetcher.get_issue_attachments.return_value = [
        JiraAttachment(
            id="1",
            filename="photo.png",
            size=1024,
            content_type="image/png",
            url="https://jira.example.com/att/1",
        ),
        JiraAttachment(
            id="2",
            filename="readme.txt",
            size=100,
            content_type="text/plain",
            url="https://jira.example.com/att/2",
        ),
    ]
    mock_jira_fetcher.fetch_attachment_content.return_value = b"\x89PNG"

    response = await jira_client.call_tool(
        "jira_get_issue_images", {"issue_key": "TEST-123"}
    )

    summary = json.loads(response.content[0].text)
    assert summary["total_images"] == 1
    assert summary["downloaded"] == 1
    assert response.content[1].type == "image"
    assert response.content[1].mimeType == "image/png"


@pytest.mark.anyio
async def test_get_issue_images_octet_stream_fallback(jira_client, mock_jira_fetcher):
    """Test that application/octet-stream with image extension is detected."""
    from mcp_atlassian.models.jira import JiraAttachment

    mock_jira_fetcher.get_issue_attachments.return_value = [
        JiraAttachment(
            id="1",
            filename="screenshot.jpg",
            size=2048,
            content_type="application/octet-stream",
            url="https://jira.example.com/att/1",
        ),
    ]
    mock_jira_fetcher.fetch_attachment_content.return_value = b"\xff\xd8\xff"

    response = await jira_client.call_tool(
        "jira_get_issue_images", {"issue_key": "TEST-123"}
    )

    summary = json.loads(response.content[0].text)
    assert summary["total_images"] == 1
    assert response.content[1].type == "image"
    assert response.content[1].mimeType == "image/jpeg"


@pytest.mark.anyio
async def test_get_issue_images_no_images(jira_client, mock_jira_fetcher):
    """Test when issue has no image attachments."""
    from mcp_atlassian.models.jira import JiraAttachment

    mock_jira_fetcher.get_issue_attachments.return_value = [
        JiraAttachment(
            id="1",
            filename="doc.pdf",
            size=5000,
            content_type="application/pdf",
            url="https://jira.example.com/att/1",
        ),
    ]

    response = await jira_client.call_tool(
        "jira_get_issue_images", {"issue_key": "TEST-123"}
    )

    summary = json.loads(response.content[0].text)
    assert summary["total_images"] == 0
    assert len(response.content) == 1  # Only summary, no images


@pytest.mark.anyio
async def test_get_issue_images_size_limit(jira_client, mock_jira_fetcher):
    """Test that images exceeding 50 MB are skipped."""
    from mcp_atlassian.models.jira import JiraAttachment

    mock_jira_fetcher.get_issue_attachments.return_value = [
        JiraAttachment(
            id="1",
            filename="huge.png",
            size=60 * 1024 * 1024,
            content_type="image/png",
            url="https://jira.example.com/att/1",
        ),
    ]

    response = await jira_client.call_tool(
        "jira_get_issue_images", {"issue_key": "TEST-123"}
    )

    summary = json.loads(response.content[0].text)
    assert summary["total_images"] == 1
    assert summary["downloaded"] == 0
    assert len(summary["failed"]) == 1
    assert "50 MB" in summary["failed"][0]["error"]


@pytest.mark.anyio
async def test_get_issue_images_fetch_failure(jira_client, mock_jira_fetcher):
    """Test graceful handling when fetch_attachment_content returns None."""
    from mcp_atlassian.models.jira import JiraAttachment

    mock_jira_fetcher.get_issue_attachments.return_value = [
        JiraAttachment(
            id="1",
            filename="broken.png",
            size=1024,
            content_type="image/png",
            url="https://jira.example.com/att/1",
        ),
    ]
    mock_jira_fetcher.fetch_attachment_content.return_value = None

    response = await jira_client.call_tool(
        "jira_get_issue_images", {"issue_key": "TEST-123"}
    )

    summary = json.loads(response.content[0].text)
    assert summary["downloaded"] == 0
    assert len(summary["failed"]) == 1
    assert "Fetch failed" in summary["failed"][0]["error"]


# --- Tests for input/output parameter name alignment ---


@pytest.mark.anyio
async def test_add_comment(jira_client, mock_jira_fetcher):
    """Test add_comment accepts 'body' parameter matching response field name."""
    response = await jira_client.call_tool(
        "jira_add_comment",
        {"issue_key": "TEST-123", "body": "Test comment body"},
    )

    mock_jira_fetcher.add_comment.assert_called_once_with(
        "TEST-123", "Test comment body", None, public=None
    )

    result = json.loads(response.content[0].text)
    assert result["id"] == "10001"
    assert result["body"] == "Test comment body"


@pytest.mark.anyio
async def test_add_comment_ignores_empty_optional_fields(
    jira_client, mock_jira_fetcher
):
    """Test add_comment treats a client's default empty fields as omitted."""
    mock_jira_fetcher._is_internal_only_project.return_value = False

    response = await jira_client.call_tool(
        "jira_add_comment",
        {
            "issue_key": "TEST-123",
            "body": "Test comment body",
            "visibility": "",
            "public": False,
        },
    )

    mock_jira_fetcher.add_comment.assert_called_once_with(
        "TEST-123", "Test comment body", None, public=None
    )

    result = json.loads(response.content[0].text)
    assert result["id"] == "10001"
    assert result["body"] == "Test comment body"


@pytest.mark.anyio
async def test_add_comment_accepts_comment_alias(jira_client, mock_jira_fetcher):
    """Test add_comment accepts 'comment' as a compatibility alias for body."""
    response = await jira_client.call_tool(
        "jira_add_comment",
        {"issue_key": "TEST-123", "comment": "Test comment body"},
    )

    mock_jira_fetcher.add_comment.assert_called_once_with(
        "TEST-123", "Test comment body", None, public=None
    )

    result = json.loads(response.content[0].text)
    assert result["id"] == "10001"
    assert result["body"] == "Test comment body"


@pytest.mark.anyio
async def test_add_comment_restricted_visibility_with_client_default_false(
    jira_client, mock_jira_fetcher
):
    """A client's default public=false must not break a restricted comment.

    Some MCP clients auto-fill omitted optional fields, sending public=false
    alongside a real visibility. Forwarding that false would trip the
    public/visibility conflict and break a restricted comment that used to work.
    """
    mock_jira_fetcher._is_internal_only_project.return_value = False

    response = await jira_client.call_tool(
        "jira_add_comment",
        {
            "issue_key": "TEST-123",
            "body": "Test comment body",
            "visibility": '{"type":"role","value":"Developer"}',
            "public": False,
        },
    )

    mock_jira_fetcher.add_comment.assert_called_once_with(
        "TEST-123",
        "Test comment body",
        {"type": "role", "value": "Developer"},
        public=None,
    )

    result = json.loads(response.content[0].text)
    assert result["id"] == "10001"


@pytest.mark.anyio
async def test_add_comment_forwards_false_for_internal_only_project(
    jira_client, mock_jira_fetcher
):
    """On a listed project, public=false must survive to the client.

    Dropping it here is what blocked internal comments outright: the guard only
    accepts an exact False, so a coerced None read as "omitted" and was refused.
    """
    mock_jira_fetcher._is_internal_only_project.return_value = True
    base_args = {"issue_key": "TEST-123", "body": "Test comment body"}

    await jira_client.call_tool("jira_add_comment", {**base_args, "public": False})
    await jira_client.call_tool("jira_add_comment", {**base_args, "public": True})
    await jira_client.call_tool("jira_add_comment", base_args)

    assert mock_jira_fetcher.add_comment.call_args_list == [
        call("TEST-123", "Test comment body", None, public=False),
        call("TEST-123", "Test comment body", None, public=True),
        call("TEST-123", "Test comment body", None, public=None),
    ]


@pytest.mark.anyio
async def test_add_comment_drops_client_default_false_on_ordinary_project(
    jira_client, mock_jira_fetcher
):
    """On an unlisted project, a bare false stays "omitted".

    Some MCP clients auto-fill an omitted optional boolean as false. Forwarding
    that would route ordinary Jira comments through the ServiceDesk API, which
    answers 403 for non-JSM issues. public=true still routes, as before.
    """
    mock_jira_fetcher._is_internal_only_project.return_value = False
    base_args = {"issue_key": "TEST-123", "body": "Test comment body"}

    await jira_client.call_tool("jira_add_comment", {**base_args, "public": False})
    await jira_client.call_tool("jira_add_comment", {**base_args, "public": True})

    assert mock_jira_fetcher.add_comment.call_args_list == [
        call("TEST-123", "Test comment body", None, public=None),
        call("TEST-123", "Test comment body", None, public=True),
    ]


@pytest.mark.anyio
async def test_add_comment_public_true_keeps_servicedesk_routing(
    jira_client, mock_jira_fetcher
):
    """Test add_comment preserves explicit public=true for JSM comments."""
    await jira_client.call_tool(
        "jira_add_comment",
        {
            "issue_key": "TEST-123",
            "body": "Test comment body",
            "visibility": "",
            "public": True,
        },
    )

    mock_jira_fetcher.add_comment.assert_called_once_with(
        "TEST-123", "Test comment body", None, public=True
    )


@pytest.mark.anyio
async def test_edit_comment(jira_client, mock_jira_fetcher):
    """Test edit_comment accepts 'body' parameter matching response field name."""
    response = await jira_client.call_tool(
        "jira_edit_comment",
        {
            "issue_key": "TEST-123",
            "comment_id": "10001",
            "body": "Updated comment body",
        },
    )

    mock_jira_fetcher.edit_comment.assert_called_once_with(
        "TEST-123", "10001", "Updated comment body", None
    )

    result = json.loads(response.content[0].text)
    assert result["id"] == "10001"
    assert result["body"] == "Updated comment body"


@pytest.mark.anyio
async def test_add_worklog(jira_client, mock_jira_fetcher):
    """Test add_worklog accepts 'time_spent' matching response 'timeSpent' field."""
    response = await jira_client.call_tool(
        "jira_add_worklog",
        {"issue_key": "TEST-123", "time_spent": "1h 30m"},
    )

    mock_jira_fetcher.add_worklog.assert_called_once_with(
        issue_key="TEST-123",
        time_spent="1h 30m",
        comment=None,
        started=None,
        original_estimate=None,
        remaining_estimate=None,
    )

    result = json.loads(response.content[0].text)
    assert result["worklog"]["time_spent"] == "1h 30m"
    assert result["worklog"]["time_spent_seconds"] == 5400


@pytest.mark.anyio
async def test_create_sprint(jira_client, mock_jira_fetcher):
    """Test create_sprint accepts 'name' parameter matching response field name."""
    response = await jira_client.call_tool(
        "jira_create_sprint",
        {
            "board_id": "1000",
            "name": "Sprint 1",
            "start_date": "2024-01-01T00:00:00.000Z",
            "end_date": "2024-01-14T00:00:00.000Z",
        },
    )

    mock_jira_fetcher.create_sprint.assert_called_once_with(
        board_id="1000",
        sprint_name="Sprint 1",
        start_date="2024-01-01T00:00:00.000Z",
        end_date="2024-01-14T00:00:00.000Z",
        goal=None,
    )

    result = json.loads(response.content[0].text)
    assert result["name"] == "Sprint 1"
    assert result["state"] == "future"


@pytest.mark.anyio
async def test_update_sprint(jira_client, mock_jira_fetcher):
    """Test update_sprint accepts 'name' parameter matching response field name."""
    response = await jira_client.call_tool(
        "jira_update_sprint",
        {
            "sprint_id": "100",
            "name": "Sprint 1 - Renamed",
            "state": "active",
        },
    )

    mock_jira_fetcher.update_sprint.assert_called_once_with(
        sprint_id="100",
        sprint_name="Sprint 1 - Renamed",
        state="active",
        start_date=None,
        end_date=None,
        goal=None,
    )

    result = json.loads(response.content[0].text)
    assert result["name"] == "Sprint 1 - Renamed"
    assert result["state"] == "active"


@pytest.mark.anyio
async def test_add_issues_to_sprint(jira_client, mock_jira_fetcher):
    """Test add_issues_to_sprint splits comma-separated keys and calls mixin."""
    mock_jira_fetcher.add_issues_to_sprint.return_value = True

    response = await jira_client.call_tool(
        "jira_add_issues_to_sprint",
        {
            "sprint_id": "100",
            "issue_keys": "PROJ-1, PROJ-2, PROJ-3",
        },
    )

    mock_jira_fetcher.add_issues_to_sprint.assert_called_once_with(
        "100", ["PROJ-1", "PROJ-2", "PROJ-3"]
    )

    result = json.loads(response.content[0].text)
    assert "3" in result["message"]
    assert result["sprint_id"] == "100"


@pytest.mark.anyio
async def test_add_issues_to_sprint_single_key(jira_client, mock_jira_fetcher):
    """Test add_issues_to_sprint with a single key (no commas)."""
    mock_jira_fetcher.add_issues_to_sprint.return_value = True

    response = await jira_client.call_tool(
        "jira_add_issues_to_sprint",
        {
            "sprint_id": "200",
            "issue_keys": "PROJ-42",
        },
    )

    mock_jira_fetcher.add_issues_to_sprint.assert_called_once_with("200", ["PROJ-42"])

    result = json.loads(response.content[0].text)
    assert "1" in result["message"]
    assert result["sprint_id"] == "200"


# ============================================================================
# Field Options Filtering Tests
# ============================================================================


class TestMatchesContains:
    """Tests for _matches_contains helper function."""

    @pytest.mark.parametrize(
        "option, needle, expected",
        [
            pytest.param(
                {"value": "High Priority"},
                "high",
                True,
                id="parent_match",
            ),
            pytest.param(
                {"value": "High Priority"},
                "low",
                False,
                id="no_match",
            ),
            pytest.param(
                {
                    "value": "Parent",
                    "child_options": [
                        {"value": "Child Alpha"},
                        {"value": "Child Beta"},
                    ],
                },
                "alpha",
                True,
                id="child_match",
            ),
            pytest.param(
                {"value": "MiXeD CaSe"},
                "mixed case",
                True,
                id="case_insensitive",
            ),
            pytest.param({}, "test", False, id="empty_option"),
            pytest.param({"value": 123}, "123", False, id="non_string_value"),
            pytest.param(
                {"value": "Simple"},
                "simple",
                True,
                id="no_children_key",
            ),
        ],
    )
    def test_matches_contains(self, option, needle, expected):
        from src.mcp_atlassian.servers.jira import _matches_contains

        assert _matches_contains(option, needle) is expected


class TestApplyOptionFilters:
    """Tests for _apply_option_filters helper function."""

    @pytest.mark.parametrize(
        "options, contains, return_limit, expected_values",
        [
            pytest.param(
                [{"value": "High"}, {"value": "Medium"}, {"value": "Low"}],
                "high",
                None,
                ["High"],
                id="contains_filter",
            ),
            pytest.param(
                [{"value": "A"}, {"value": "B"}, {"value": "C"}],
                None,
                2,
                ["A", "B"],
                id="return_limit",
            ),
            pytest.param(
                [
                    {"value": "Alpha"},
                    {"value": "Beta"},
                    {"value": "Gamma"},
                    {"value": "Alpha Two"},
                ],
                "alpha",
                1,
                ["Alpha"],
                id="contains_then_limit",
            ),
            pytest.param(
                [{"value": "A"}, {"value": "B"}],
                None,
                None,
                ["A", "B"],
                id="no_filters",
            ),
            pytest.param([], "test", 5, [], id="empty_options"),
        ],
    )
    def test_apply_option_filters(
        self, options, contains, return_limit, expected_values
    ):
        from src.mcp_atlassian.servers.jira import _apply_option_filters

        result = _apply_option_filters(options, contains, return_limit)
        assert [opt["value"] for opt in result] == expected_values


class TestToValuesOnlyPayload:
    """Tests for _to_values_only_payload helper function."""

    @pytest.mark.parametrize(
        "options, expected",
        [
            pytest.param(
                [
                    {"id": "1", "value": "High"},
                    {"id": "2", "value": "Medium"},
                    {"id": "3", "value": "Low"},
                ],
                ["High", "Medium", "Low"],
                id="simple_options",
            ),
            pytest.param(
                [
                    {
                        "id": "1",
                        "value": "Parent",
                        "child_options": [
                            {"id": "2", "value": "Child A"},
                            {"id": "3", "value": "Child B"},
                        ],
                    },
                ],
                [{"value": "Parent", "children": ["Child A", "Child B"]}],
                id="cascading_options",
            ),
            pytest.param(
                [
                    {"id": "1", "value": "Simple"},
                    {
                        "id": "2",
                        "value": "Cascading",
                        "child_options": [{"id": "3", "value": "Child"}],
                    },
                ],
                ["Simple", {"value": "Cascading", "children": ["Child"]}],
                id="mixed_options",
            ),
            pytest.param([], [], id="empty_options"),
        ],
    )
    def test_to_values_only_payload(self, options, expected):
        from src.mcp_atlassian.servers.jira import _to_values_only_payload

        assert _to_values_only_payload(options) == expected


# ============================================================================
# Field Options Tool Integration Tests
# ============================================================================


def _make_mock_field_options():
    """Create mock FieldOption objects for testing."""
    opt1 = MagicMock()
    opt1.to_simplified_dict.return_value = {"id": "1", "value": "High"}

    opt2 = MagicMock()
    opt2.to_simplified_dict.return_value = {"id": "2", "value": "Medium"}

    opt3 = MagicMock()
    opt3.to_simplified_dict.return_value = {"id": "3", "value": "Low"}

    opt4 = MagicMock()
    opt4.to_simplified_dict.return_value = {
        "id": "4",
        "value": "Parent",
        "child_options": [
            {"id": "5", "value": "High Child"},
            {"id": "6", "value": "Low Child"},
        ],
    }

    return [opt1, opt2, opt3, opt4]


@pytest.mark.anyio
async def test_get_field_options_default(jira_client, mock_jira_fetcher):
    """Test get_field_options with no filtering params (default behavior)."""
    mock_jira_fetcher.get_field_options.return_value = _make_mock_field_options()

    response = await jira_client.call_tool(
        "jira_get_field_options",
        {"field_id": "customfield_10001"},
    )

    assert hasattr(response, "content")
    result = json.loads(response.content[0].text)
    assert len(result) == 4
    assert result[0]["value"] == "High"
    assert result[3]["value"] == "Parent"


@pytest.mark.anyio
async def test_get_field_options_contains(jira_client, mock_jira_fetcher):
    """Test get_field_options with contains filter."""
    mock_jira_fetcher.get_field_options.return_value = _make_mock_field_options()

    response = await jira_client.call_tool(
        "jira_get_field_options",
        {"field_id": "customfield_10001", "contains": "high"},
    )

    result = json.loads(response.content[0].text)
    # Should match "High" (parent) and "Parent" (has "High Child" child)
    assert len(result) == 2
    values = [opt["value"] for opt in result]
    assert "High" in values
    assert "Parent" in values


@pytest.mark.anyio
async def test_get_field_options_return_limit(jira_client, mock_jira_fetcher):
    """Test get_field_options with return_limit."""
    mock_jira_fetcher.get_field_options.return_value = _make_mock_field_options()

    response = await jira_client.call_tool(
        "jira_get_field_options",
        {"field_id": "customfield_10001", "return_limit": 2},
    )

    result = json.loads(response.content[0].text)
    assert len(result) == 2
    assert result[0]["value"] == "High"
    assert result[1]["value"] == "Medium"


@pytest.mark.anyio
async def test_get_field_options_values_only(jira_client, mock_jira_fetcher):
    """Test get_field_options with values_only=True."""
    mock_options = _make_mock_field_options()[:3]  # Simple options only
    mock_jira_fetcher.get_field_options.return_value = mock_options

    response = await jira_client.call_tool(
        "jira_get_field_options",
        {"field_id": "customfield_10001", "values_only": True},
    )

    result = json.loads(response.content[0].text)
    assert result == ["High", "Medium", "Low"]


@pytest.mark.anyio
async def test_get_field_options_values_only_cascading(jira_client, mock_jira_fetcher):
    """Test get_field_options with values_only=True for cascading options."""
    mock_jira_fetcher.get_field_options.return_value = _make_mock_field_options()

    response = await jira_client.call_tool(
        "jira_get_field_options",
        {"field_id": "customfield_10001", "values_only": True},
    )

    result = json.loads(response.content[0].text)
    assert result[0] == "High"
    assert result[1] == "Medium"
    assert result[2] == "Low"
    assert result[3] == {
        "value": "Parent",
        "children": ["High Child", "Low Child"],
    }


@pytest.mark.anyio
async def test_get_field_options_combined(jira_client, mock_jira_fetcher):
    """Test get_field_options with contains + return_limit + values_only."""
    mock_jira_fetcher.get_field_options.return_value = _make_mock_field_options()

    response = await jira_client.call_tool(
        "jira_get_field_options",
        {
            "field_id": "customfield_10001",
            "contains": "high",
            "return_limit": 1,
            "values_only": True,
        },
    )

    result = json.loads(response.content[0].text)
    # "High" matches directly, "Parent" matches via child "High Child"
    # return_limit=1 caps to first match
    assert len(result) == 1
    assert result[0] == "High"


@pytest.mark.anyio
async def test_get_issue_include_remote_links(jira_client, mock_jira_fetcher):
    """get_issue with include=remote_links fetches remote links."""
    mock_jira_fetcher.get_remote_issue_links.return_value = [
        {
            "id": 1,
            "object": {
                "url": "https://example.com",
                "title": "Link",
            },
        }
    ]

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123", "include": "remote_links"},
    )
    content = json.loads(response.content[0].text)
    assert "remote_links" in content
    assert len(content["remote_links"]) == 1
    mock_jira_fetcher.get_remote_issue_links.assert_called_once_with("TEST-123")


@pytest.mark.anyio
async def test_get_issue_include_watchers(jira_client, mock_jira_fetcher):
    """get_issue with include=watchers fetches watchers."""
    mock_jira_fetcher.get_issue_watchers.return_value = {
        "watchCount": 1,
        "watchers": [{"name": "user1"}],
    }

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123", "include": "watchers"},
    )
    content = json.loads(response.content[0].text)
    assert "watchers" in content
    assert content["watchers"]["watchCount"] == 1
    mock_jira_fetcher.get_issue_watchers.assert_called_once_with("TEST-123")


@pytest.mark.anyio
async def test_get_issue_include_transitions_fetches_transitions(
    jira_client, mock_jira_fetcher
):
    """get_issue with include=transitions fetches available transitions."""
    mock_jira_fetcher.get_available_transitions.return_value = [
        {"id": "11", "name": "Done", "to_status": "Done"}
    ]

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123", "include": "transitions"},
    )
    content = json.loads(response.content[0].text)
    assert content["transitions"] == [{"id": "11", "name": "Done", "to_status": "Done"}]
    mock_jira_fetcher.get_available_transitions.assert_called_once_with("TEST-123")
    call_args = mock_jira_fetcher.get_issue.call_args
    assert call_args.kwargs.get("expand") is None


@pytest.mark.anyio
async def test_get_issue_include_changelog_adds_expand(jira_client, mock_jira_fetcher):
    """get_issue with include=changelog adds to expand."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123", "include": "changelog"},
    )
    content = json.loads(response.content[0].text)
    assert content["changelogs"] == []
    call_args = mock_jira_fetcher.get_issue.call_args
    expand_val = call_args.kwargs.get("expand", "")
    assert "changelog" in expand_val


@pytest.mark.anyio
async def test_get_issue_include_comments_adds_comment_field(
    jira_client, mock_jira_fetcher
):
    """get_issue with include=comments requests the comment field."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {
            "issue_key": "TEST-123",
            "fields": "summary,status",
            "include": "comments",
        },
    )
    content = json.loads(response.content[0].text)
    assert content["comments"] == []
    call_args = mock_jira_fetcher.get_issue.call_args
    assert call_args.kwargs["fields"] == ["summary", "status", "comment"]


@pytest.mark.anyio
async def test_get_issue_include_worklogs(jira_client, mock_jira_fetcher):
    """get_issue with include=worklogs fetches worklogs."""
    mock_jira_fetcher.get_worklogs.return_value = [
        {"id": "10001", "time_spent": "1h", "time_spent_seconds": 3600}
    ]

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123", "include": "worklogs"},
    )
    content = json.loads(response.content[0].text)
    assert content["worklogs"] == [
        {"id": "10001", "time_spent": "1h", "time_spent_seconds": 3600}
    ]
    mock_jira_fetcher.get_worklogs.assert_called_once_with("TEST-123")


@pytest.mark.anyio
async def test_get_issue_include_multiple(jira_client, mock_jira_fetcher):
    """get_issue with multiple include sections."""
    mock_jira_fetcher.get_remote_issue_links.return_value = []
    mock_jira_fetcher.get_issue_watchers.return_value = {
        "watchCount": 0,
    }
    mock_jira_fetcher.get_available_transitions.return_value = [
        {"id": "11", "name": "Done"}
    ]

    response = await jira_client.call_tool(
        "jira_get_issue",
        {
            "issue_key": "TEST-123",
            "include": "remote_links,watchers,transitions,changelog",
        },
    )
    content = json.loads(response.content[0].text)
    assert "remote_links" in content
    assert "watchers" in content
    assert content["transitions"] == [{"id": "11", "name": "Done"}]
    call_args = mock_jira_fetcher.get_issue.call_args
    expand_val = call_args.kwargs.get("expand", "")
    assert "changelog" in expand_val


@pytest.mark.anyio
async def test_get_issue_include_all(jira_client, mock_jira_fetcher):
    """get_issue with include=all enables every supported include section."""
    mock_jira_fetcher.get_remote_issue_links.return_value = [{"id": 1}]
    mock_jira_fetcher.get_available_transitions.return_value = [{"id": "11"}]
    mock_jira_fetcher.get_issue_watchers.return_value = {"watchCount": 1}
    mock_jira_fetcher.get_worklogs.return_value = [{"id": "10001"}]

    response = await jira_client.call_tool(
        "jira_get_issue",
        {
            "issue_key": "TEST-123",
            "fields": "summary,status",
            "include": "all",
        },
    )
    content = json.loads(response.content[0].text)
    assert content["remote_links"] == [{"id": 1}]
    assert content["transitions"] == [{"id": "11"}]
    assert content["watchers"] == {"watchCount": 1}
    assert content["worklogs"] == [{"id": "10001"}]
    assert content["comments"] == []
    assert content["changelogs"] == []

    call_args = mock_jira_fetcher.get_issue.call_args
    assert call_args.kwargs["fields"] == ["summary", "status", "comment"]
    assert call_args.kwargs["expand"] == "changelog"


@pytest.mark.anyio
async def test_get_issue_include_unknown_sections_are_ignored(
    jira_client, mock_jira_fetcher, caplog
):
    """Unknown include sections are ignored without failing the tool call."""
    mock_jira_fetcher.get_remote_issue_links.return_value = [{"id": 1}]

    with caplog.at_level(logging.WARNING):
        response = await jira_client.call_tool(
            "jira_get_issue",
            {"issue_key": "TEST-123", "include": "remote_links,nope"},
        )

    content = json.loads(response.content[0].text)
    assert content["remote_links"] == [{"id": 1}]
    assert "Ignoring unsupported jira_get_issue include section: nope" in caplog.text
    mock_jira_fetcher.get_issue_watchers.assert_not_called()


@pytest.mark.anyio
async def test_get_issue_include_preserves_existing_expand(
    jira_client, mock_jira_fetcher
):
    """include merges with an existing expand parameter."""
    await jira_client.call_tool(
        "jira_get_issue",
        {
            "issue_key": "TEST-123",
            "expand": "renderedFields",
            "include": "changelog",
        },
    )
    call_args = mock_jira_fetcher.get_issue.call_args
    expand_val = call_args.kwargs.get("expand", "")
    assert "renderedFields" in expand_val
    assert "changelog" in expand_val


@pytest.mark.anyio
async def test_get_issue_include_none_no_enrichments(jira_client, mock_jira_fetcher):
    """Omitting include produces no enrichment keys."""
    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123"},
    )
    content = json.loads(response.content[0].text)
    assert "remote_links" not in content
    assert "transitions" not in content
    assert "watchers" not in content
    assert "worklogs" not in content


# =============================================================================
# assign_issue tests
# =============================================================================


@pytest.mark.anyio
async def test_assign_issue(jira_client, mock_jira_fetcher):
    """Test assigning an issue to a user."""
    response = await jira_client.call_tool(
        "jira_assign_issue",
        {
            "issue_key": "TEST-123",
            "assignee": "user@example.com",
        },
    )
    content = json.loads(response.content[0].text)
    assert content["message"] == "Issue TEST-123 assigned successfully"
    assert "issue" in content
    mock_jira_fetcher.assign_issue.assert_called_once_with(
        issue_key="TEST-123", assignee="user@example.com"
    )


@pytest.mark.anyio
async def test_assign_issue_unassign(jira_client, mock_jira_fetcher):
    """Test unassigning an issue (passing None)."""
    response = await jira_client.call_tool(
        "jira_assign_issue",
        {
            "issue_key": "TEST-123",
            "assignee": None,
        },
    )
    content = json.loads(response.content[0].text)
    assert content["message"] == "Issue TEST-123 assigned successfully"
    mock_jira_fetcher.assign_issue.assert_called_once_with(
        issue_key="TEST-123", assignee=None
    )


@pytest.mark.anyio
async def test_assign_issue_with_resolved_user_dict(jira_client, mock_jira_fetcher):
    """Test assigning an issue with a resolved user object JSON string."""
    assignee = {
        "account_id": "5b10ac8d82e05b22cc7d4ef5",
        "display_name": "Test User",
    }

    response = await jira_client.call_tool(
        "jira_assign_issue",
        {
            "issue_key": "TEST-123",
            "assignee": json.dumps(assignee),
        },
    )
    content = json.loads(response.content[0].text)
    assert content["message"] == "Issue TEST-123 assigned successfully"
    mock_jira_fetcher.assign_issue.assert_called_once_with(
        issue_key="TEST-123", assignee=assignee
    )


@pytest.mark.anyio
async def test_assign_issue_error(jira_client, mock_jira_fetcher):
    """Test assign_issue error handling."""
    mock_jira_fetcher.assign_issue.side_effect = ValueError("User not found")
    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_assign_issue",
            {
                "issue_key": "TEST-123",
                "assignee": "nonexistent@example.com",
            },
        )
    assert "User not found" in str(excinfo.value)


# =============================================================================
# move_issue tests
# =============================================================================


@pytest.mark.anyio
async def test_jira_move_issue_success(jira_client, mock_jira_fetcher):
    """Test successful cross-project issue move."""
    response = await jira_client.call_tool(
        "jira_move_issue",
        {"issue_key": "PROJ-123", "target_project_key": "OTHER"},
    )
    content = json.loads(response.content[0].text)
    assert "moved successfully" in content["message"]
    assert "PROJ-123" in content["message"]
    assert "OTHER" in content["message"]
    assert content["issue"]["key"] == "OTHER-999"
    assert content["issue"]["project"]["key"] == "OTHER"
    mock_jira_fetcher.move_issue.assert_called_once_with("PROJ-123", "OTHER")


@pytest.mark.anyio
async def test_jira_move_issue_failure(jira_client, mock_jira_fetcher):
    """Test that a move failure propagates as ToolError."""
    mock_jira_fetcher.move_issue.side_effect = ValueError("Target project not found")

    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_move_issue",
            {"issue_key": "PROJ-123", "target_project_key": "NONEXISTENT"},
        )
    assert "Target project not found" in str(excinfo.value)


@pytest.mark.anyio
async def test_jira_move_issue_not_cloud(jira_client, mock_jira_fetcher):
    """Test that calling move on a Server/DC instance raises ToolError."""
    mock_jira_fetcher.move_issue.side_effect = NotImplementedError(
        "Cross-project issue move is only available on Jira Cloud."
    )

    with pytest.raises(ToolError) as excinfo:
        await jira_client.call_tool(
            "jira_move_issue",
            {"issue_key": "PROJ-123", "target_project_key": "OTHER"},
        )
    assert "Jira Cloud" in str(excinfo.value)


# ============================================================================
# Display-Name Feature Tests
# ============================================================================


@pytest.mark.anyio
async def test_get_issue_use_display_names(jira_client, mock_jira_fetcher):
    """Test get_issue with use_display_names=True returns display-name keys."""
    display_name_response = {
        "key": "TEST-123",
        "summary": "Test Issue Summary",
        "status": {"name": "Open"},
        "Story Points": {"value": 5, "field_id": "customfield_10243"},
    }

    def mock_get_issue_dn(
        issue_key,
        fields=None,
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    ):
        mock_issue = MagicMock()
        mock_issue.to_simplified_dict.return_value = {
            "key": issue_key,
            "summary": "Test Issue Summary",
            "status": {"name": "Open"},
            "customfield_10243": 5,
        }
        mock_issue.to_display_name_dict.return_value = {
            **display_name_response,
            "key": issue_key,
        }
        return mock_issue

    mock_jira_fetcher.get_issue.side_effect = mock_get_issue_dn

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "TEST-123", "use_display_names": True},
    )
    content = json.loads(response.content[0].text)
    assert "Story Points" in content
    assert "customfield_10243" not in content

    mock_jira_fetcher.get_issue.assert_called_once()
    call_kwargs = mock_jira_fetcher.get_issue.call_args
    assert call_kwargs[1]["issue_key"] == "TEST-123"
    assert call_kwargs[1]["expand"] == "names"


@pytest.mark.anyio
async def test_search_use_display_names(jira_client, mock_jira_fetcher):
    """Test search with use_display_names=True returns display-name keys."""
    display_name_issues = [
        {
            "key": "PROJ-123",
            "summary": "First issue",
            "Story Points": {"value": 3, "field_id": "customfield_10243"},
        },
    ]

    def mock_search_dn(jql, **kwargs):
        mock_search_result = MagicMock()
        mock_search_result.to_simplified_dict.return_value = {
            "total": 1,
            "start_at": kwargs.get("start", 0),
            "max_results": kwargs.get("limit", 50),
            "issues": [
                {"key": "PROJ-123", "summary": "First issue", "customfield_10243": 3},
            ],
        }
        mock_search_result.to_display_name_dict.return_value = {
            "total": 1,
            "start_at": kwargs.get("start", 0),
            "max_results": kwargs.get("limit", 50),
            "issues": display_name_issues,
        }
        return mock_search_result

    mock_jira_fetcher.search_issues.side_effect = mock_search_dn

    response = await jira_client.call_tool(
        "jira_search",
        {
            "jql": "project = TEST",
            "expand": "renderedFields",
            "use_display_names": True,
        },
    )
    content = json.loads(response.content[0].text)
    assert content["issues"][0].get("Story Points") is not None
    assert "customfield_10243" not in content["issues"][0]

    mock_jira_fetcher.search_issues.assert_called_once()
    call_kwargs = mock_jira_fetcher.search_issues.call_args
    assert call_kwargs[1]["jql"] == "project = TEST"
    assert call_kwargs[1]["expand"] == "renderedFields,names"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "include_key",
    ["remote_links", "transitions", "watchers", "worklogs"],
)
async def test_display_name_collision_with_include_key_preserves_both(
    jira_client, mock_jira_fetcher, include_key
):
    """Custom field whose display name collides with include output key falls back to raw ID."""
    output_key_map = {
        "remote_links": "remote_links",
        "transitions": "transitions",
        "watchers": "watchers",
        "worklogs": "worklogs",
    }
    output_key = output_key_map[include_key]

    def mock_get_issue_collision(
        issue_key,
        fields=None,
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    ):
        mock_issue = MagicMock()
        mock_issue.to_simplified_dict.return_value = {
            "key": issue_key,
            "summary": "Test",
            "status": {"name": "Open"},
            "customfield_99999": {"name": output_key, "value": "custom"},
        }

        def display_name_dict(extra_reserved_keys=None):
            if extra_reserved_keys and output_key in extra_reserved_keys:
                return {
                    "key": issue_key,
                    "summary": "Test",
                    "status": {"name": "Open"},
                    "customfield_99999": {
                        "value": "custom",
                        "field_id": "customfield_99999",
                    },
                }
            return {
                "key": issue_key,
                "summary": "Test",
                "status": {"name": "Open"},
                output_key: {"value": "custom", "field_id": "customfield_99999"},
            }

        mock_issue.to_display_name_dict.side_effect = display_name_dict
        return mock_issue

    mock_jira_fetcher.get_issue.side_effect = mock_get_issue_collision
    mock_jira_fetcher.get_remote_issue_links.return_value = [{"url": "http://x"}]
    mock_jira_fetcher.get_available_transitions.return_value = [{"name": "Done"}]
    mock_jira_fetcher.get_issue_watchers.return_value = {"watchers": ["u1"]}
    mock_jira_fetcher.get_worklogs.return_value = [{"time": "1h"}]

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "COL-1", "use_display_names": True, "include": include_key},
    )
    content = json.loads(response.content[0].text)

    assert "customfield_99999" in content
    assert content["customfield_99999"]["value"] == "custom"

    assert output_key in content
    assert content[output_key] != {"value": "custom", "field_id": "customfield_99999"}


@pytest.mark.anyio
@pytest.mark.parametrize("include_key", ["comments", "changelog"])
async def test_display_name_collision_with_setdefault_include_key(
    jira_client, mock_jira_fetcher, include_key
):
    """Custom field whose display name matches a setdefault enrichment key falls back to raw ID."""
    output_key_map = {"comments": "comments", "changelog": "changelogs"}
    output_key = output_key_map[include_key]

    def mock_get_issue_collision(
        issue_key,
        fields=None,
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    ):
        mock_issue = MagicMock()
        mock_issue.to_simplified_dict.return_value = {
            "key": issue_key,
            "summary": "Test",
            "status": {"name": "Open"},
            "customfield_88888": {"name": output_key, "value": "custom"},
        }

        def display_name_dict(extra_reserved_keys=None):
            if extra_reserved_keys and output_key in extra_reserved_keys:
                return {
                    "key": issue_key,
                    "summary": "Test",
                    "status": {"name": "Open"},
                    "customfield_88888": {
                        "value": "custom",
                        "field_id": "customfield_88888",
                    },
                }
            return {
                "key": issue_key,
                "summary": "Test",
                "status": {"name": "Open"},
                output_key: {"value": "custom", "field_id": "customfield_88888"},
            }

        mock_issue.to_display_name_dict.side_effect = display_name_dict
        return mock_issue

    mock_jira_fetcher.get_issue.side_effect = mock_get_issue_collision

    response = await jira_client.call_tool(
        "jira_get_issue",
        {"issue_key": "COL-2", "use_display_names": True, "include": include_key},
    )
    content = json.loads(response.content[0].text)

    assert "customfield_88888" in content
    assert content["customfield_88888"]["value"] == "custom"
    assert output_key in content


class TestJiraToolInputParsers:
    """Tests for Jira tool JSON and comma-separated input parsers."""

    def test_parse_get_issue_include_ignores_empty_sections(self):
        """Test blank include sections are ignored."""
        from src.mcp_atlassian.servers.jira import _parse_get_issue_include

        assert _parse_get_issue_include("comments,, worklog") == {
            "comments",
            "worklogs",
        }

    @pytest.mark.parametrize(
        ("visibility", "expected"),
        [
            (None, None),
            ("", None),
            ("null", None),
            (
                '{"type":"group","value":"jira-users"}',
                {"type": "group", "value": "jira-users"},
            ),
        ],
    )
    def test_parse_visibility(self, visibility, expected):
        """Test supported visibility JSON values."""
        from src.mcp_atlassian.servers.jira import _parse_visibility

        assert _parse_visibility(visibility) == expected

    @pytest.mark.parametrize("visibility", ["[]", "not-json"])
    def test_parse_visibility_rejects_invalid_values(self, visibility):
        """Test invalid visibility values are rejected."""
        from src.mcp_atlassian.servers.jira import _parse_visibility

        with pytest.raises(ValueError):
            _parse_visibility(visibility)

    @pytest.mark.parametrize(
        ("additional_fields", "expected"),
        [
            (None, {}),
            ({"labels": ["test"]}, {"labels": ["test"]}),
            ('{"labels":["test"]}', {"labels": ["test"]}),
        ],
    )
    def test_parse_additional_fields(self, additional_fields, expected):
        """Test supported additional field input formats."""
        from src.mcp_atlassian.servers.jira import _parse_additional_fields

        assert _parse_additional_fields(additional_fields) == expected

    @pytest.mark.parametrize("additional_fields", ["[]", "not-json", 42])
    def test_parse_additional_fields_rejects_invalid_values(self, additional_fields):
        """Test invalid additional field payloads are rejected."""
        from src.mcp_atlassian.servers.jira import _parse_additional_fields

        with pytest.raises(ValueError):
            _parse_additional_fields(additional_fields)

    @pytest.mark.parametrize(
        ("participants", "expected"),
        [
            (None, None),
            ("", None),
            ([" alice ", "", "bob"], ["alice", "bob"]),
            ('["alice", " bob "]', ["alice", "bob"]),
            ("alice, bob,,", ["alice", "bob"]),
        ],
    )
    def test_parse_request_participants(self, participants, expected):
        """Test supported request participant input formats."""
        from src.mcp_atlassian.servers.jira import _parse_request_participants

        assert _parse_request_participants(participants) == expected

    @pytest.mark.parametrize("participants", ['{"accountId":"abc"}', 42])
    def test_parse_request_participants_rejects_invalid_types(self, participants):
        """Test invalid request participant values are rejected."""
        from src.mcp_atlassian.servers.jira import _parse_request_participants

        with pytest.raises(ValueError):
            _parse_request_participants(participants)

    @pytest.mark.parametrize(
        ("attachments", "expected"),
        [
            (None, None),
            ("", None),
            ('[{"filename":"a.txt"}]', [{"filename": "a.txt"}]),
            ([{"filename": "a.txt"}], [{"filename": "a.txt"}]),
        ],
    )
    def test_parse_attachments(self, attachments, expected):
        """Test supported attachment input formats."""
        from src.mcp_atlassian.servers.jira import _parse_attachments

        assert _parse_attachments(attachments) == expected

    @pytest.mark.parametrize("attachments", ["not-json", "{}", '["a.txt"]'])
    def test_parse_attachments_rejects_invalid_values(self, attachments):
        """Test invalid attachment payloads are rejected."""
        from src.mcp_atlassian.servers.jira import _parse_attachments

        with pytest.raises(ValueError):
            _parse_attachments(attachments)


@pytest.mark.anyio
async def test_get_issue_proforma_forms(jira_client, mock_jira_fetcher):
    """Test listing ProForma forms for an issue."""
    form = MagicMock()
    form.to_simplified_dict.return_value = {"id": "form-1", "name": "Intake"}
    mock_jira_fetcher.get_issue_forms.return_value = [form]

    response = await jira_client.call_tool(
        "jira_get_issue_proforma_forms", {"issue_key": "TEST-123"}
    )
    content = json.loads(response.content[0].text)

    assert content == {
        "success": True,
        "forms": [{"id": "form-1", "name": "Intake"}],
        "count": 1,
    }
    mock_jira_fetcher.get_issue_forms.assert_called_once_with("TEST-123")


@pytest.mark.anyio
async def test_get_proforma_form_details_not_found(jira_client, mock_jira_fetcher):
    """Test a missing ProForma form returns a structured response."""
    mock_jira_fetcher.get_form_details.return_value = None

    response = await jira_client.call_tool(
        "jira_get_proforma_form_details",
        {"issue_key": "TEST-123", "form_id": "form-1"},
    )
    content = json.loads(response.content[0].text)

    assert content["success"] is False
    assert content["issue_key"] == "TEST-123"
    assert content["form_id"] == "form-1"
    assert "not found" in content["error"]


@pytest.mark.anyio
async def test_get_proforma_form_details(jira_client, mock_jira_fetcher):
    """Test retrieving the details of an existing ProForma form."""
    form = MagicMock()
    form.to_simplified_dict.return_value = {"id": "form-1", "name": "Intake"}
    mock_jira_fetcher.get_form_details.return_value = form

    response = await jira_client.call_tool(
        "jira_get_proforma_form_details",
        {"issue_key": "TEST-123", "form_id": "form-1"},
    )
    content = json.loads(response.content[0].text)

    assert content == {
        "success": True,
        "form": {"id": "form-1", "name": "Intake"},
    }


@pytest.mark.anyio
async def test_update_proforma_form_answers_converts_dates(
    jira_client, mock_jira_fetcher
):
    """Test form updates convert date values before delegation."""
    mock_jira_fetcher.update_form_answers.return_value = {"updated": True}

    response = await jira_client.call_tool(
        "jira_update_proforma_form_answers",
        {
            "issue_key": "TEST-123",
            "form_id": "form-1",
            "answers": [
                {"questionId": "q1", "type": "DATE", "value": "2024-12-17"},
                {"questionId": "q2", "type": "TEXT", "value": "unchanged"},
            ],
        },
    )
    content = json.loads(response.content[0].text)

    assert content["success"] is True
    assert content["updated_fields"] == 2
    processed_answers = mock_jira_fetcher.update_form_answers.call_args.args[2]
    assert isinstance(processed_answers[0]["value"], int)
    assert processed_answers[1]["value"] == "unchanged"


@pytest.mark.anyio
async def test_get_issue_dates(jira_client, mock_jira_fetcher):
    """Test issue date metrics are serialized and delegated."""
    result = MagicMock()
    result.to_simplified_dict.return_value = {"issue_key": "TEST-123"}
    mock_jira_fetcher.get_issue_dates.return_value = result

    response = await jira_client.call_tool(
        "jira_get_issue_dates",
        {
            "issue_key": "TEST-123",
            "include_status_changes": False,
            "include_status_summary": True,
        },
    )

    assert json.loads(response.content[0].text) == {"issue_key": "TEST-123"}
    mock_jira_fetcher.get_issue_dates.assert_called_once_with(
        issue_key="TEST-123",
        include_created=True,
        include_updated=True,
        include_due_date=True,
        include_resolution_date=True,
        include_status_changes=False,
        include_status_summary=True,
    )


@pytest.mark.anyio
async def test_get_issue_sla_parses_metrics(jira_client, mock_jira_fetcher):
    """Test SLA metric names are parsed before delegation."""
    result = MagicMock()
    result.to_simplified_dict.return_value = {"cycle_time": 120}
    mock_jira_fetcher.get_issue_sla.return_value = result

    response = await jira_client.call_tool(
        "jira_get_issue_sla",
        {
            "issue_key": "TEST-123",
            "metrics": "cycle_time, time_in_status",
            "working_hours_only": True,
            "include_raw_dates": True,
        },
    )

    assert json.loads(response.content[0].text) == {"cycle_time": 120}
    mock_jira_fetcher.get_issue_sla.assert_called_once_with(
        issue_key="TEST-123",
        metrics=["cycle_time", "time_in_status"],
        working_hours_only=True,
        include_raw_dates=True,
    )


@pytest.mark.anyio
async def test_get_issue_development_info(jira_client, mock_jira_fetcher):
    """Test retrieving development information for one issue."""
    mock_jira_fetcher.get_issue_development_info.return_value = {
        "issue_key": "TEST-123",
        "pullRequests": [],
    }

    response = await jira_client.call_tool(
        "jira_get_issue_development_info",
        {
            "issue_key": "TEST-123",
            "application_type": "GitHub",
            "data_type": "pullrequest",
        },
    )

    assert json.loads(response.content[0].text)["issue_key"] == "TEST-123"
    mock_jira_fetcher.get_issue_development_info.assert_called_once_with(
        issue_key="TEST-123",
        application_type="GitHub",
        data_type="pullrequest",
    )


@pytest.mark.anyio
async def test_get_issues_development_info_parses_keys(jira_client, mock_jira_fetcher):
    """Test batch development information parses comma-separated issue keys."""
    mock_jira_fetcher.get_issues_development_info.return_value = [
        {"issue_key": "TEST-1"},
        {"issue_key": "TEST-2"},
    ]

    response = await jira_client.call_tool(
        "jira_get_issues_development_info",
        {"issue_keys": "TEST-1, TEST-2,,"},
    )

    assert len(json.loads(response.content[0].text)) == 2
    mock_jira_fetcher.get_issues_development_info.assert_called_once_with(
        issue_keys=["TEST-1", "TEST-2"],
        application_type=None,
        data_type=None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "fetcher_method", "expected_kwargs"),
    [
        (
            "jira_get_project_epic_hierarchy",
            {"project_key": "TEST", "max_epics": 25},
            "get_project_epic_hierarchy",
            {"project_key": "TEST", "max_epics": 25},
        ),
        (
            "jira_get_cross_project_dependencies",
            {"project_key": "TEST", "max_issues": 50},
            "get_cross_project_dependencies",
            {"project_key": "TEST", "max_issues": 50},
        ),
    ],
)
async def test_project_analysis_tools_delegate(
    jira_client,
    mock_jira_fetcher,
    tool_name,
    arguments,
    fetcher_method,
    expected_kwargs,
):
    """Test project analysis tools delegate with their configured limits."""
    method = getattr(mock_jira_fetcher, fetcher_method)
    method.return_value = {"project_key": "TEST", "groups": []}

    response = await jira_client.call_tool(tool_name, arguments)

    assert json.loads(response.content[0].text)["project_key"] == "TEST"
    method.assert_called_once_with(**expected_kwargs)


@pytest.mark.anyio
async def test_move_issues_to_backlog_parses_keys(jira_client, mock_jira_fetcher):
    """Test moving issues to backlog parses comma-separated issue keys."""
    response = await jira_client.call_tool(
        "jira_move_issues_to_backlog", {"issue_keys": "TEST-1, TEST-2,,"}
    )
    content = json.loads(response.content[0].text)

    assert content["issue_keys"] == ["TEST-1", "TEST-2"]
    assert content["message"] == "Successfully moved 2 issue(s) to backlog"
    mock_jira_fetcher.move_issues_to_backlog.assert_called_once_with(
        ["TEST-1", "TEST-2"]
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "fetcher_method"),
    [
        (
            "jira_get_issue_proforma_forms",
            {"issue_key": "TEST-123"},
            "get_issue_forms",
        ),
        (
            "jira_get_proforma_form_details",
            {"issue_key": "TEST-123", "form_id": "form-1"},
            "get_form_details",
        ),
        (
            "jira_update_proforma_form_answers",
            {
                "issue_key": "TEST-123",
                "form_id": "form-1",
                "answers": [],
            },
            "update_form_answers",
        ),
        (
            "jira_get_issue_dates",
            {"issue_key": "TEST-123"},
            "get_issue_dates",
        ),
        (
            "jira_get_issue_sla",
            {"issue_key": "TEST-123"},
            "get_issue_sla",
        ),
        (
            "jira_get_issue_development_info",
            {"issue_key": "TEST-123"},
            "get_issue_development_info",
        ),
        (
            "jira_get_issues_development_info",
            {"issue_keys": "TEST-1,TEST-2"},
            "get_issues_development_info",
        ),
    ],
)
async def test_jira_analysis_tools_return_structured_errors(
    jira_client,
    mock_jira_fetcher,
    tool_name,
    arguments,
    fetcher_method,
):
    """Test analysis and form tools preserve fetcher error details."""
    getattr(mock_jira_fetcher, fetcher_method).side_effect = RuntimeError(
        "service unavailable"
    )

    response = await jira_client.call_tool(tool_name, arguments)
    content = json.loads(response.content[0].text)

    assert content["success"] is False
    assert content["error"] == "service unavailable"
