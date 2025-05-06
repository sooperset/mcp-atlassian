"""Unit tests for the Jira FastMCP server implementation."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport

from src.mcp_atlassian.jira import JiraFetcher
from src.mcp_atlassian.servers.context import MainAppContext
from tests.fixtures.jira_mocks import (
    MOCK_JIRA_COMMENTS_SIMPLIFIED,
    MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED,
    MOCK_JIRA_JQL_RESPONSE_SIMPLIFIED,
)


@pytest.fixture
def mock_jira_fetcher():
    """Create a mock JiraFetcher using predefined responses from fixtures."""
    mock_fetcher = MagicMock(spec=JiraFetcher)
    mock_fetcher.config = MagicMock()
    mock_fetcher.config.url = "https://test.atlassian.net"

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
        print(f"DEBUG: mock_get_issue called with issue_key={issue_key}")
        if not issue_key:
            raise ValueError("Issue key is required")

        mock_issue = MagicMock()
        response_data = MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED.copy()
        response_data["key"] = issue_key
        response_data["fields_queried"] = fields  # Store for assertion
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

    # Configure search_issues to return fixture data (as list of mock issues)
    def mock_search_issues(jql, **kwargs):
        mock_search_result = MagicMock()
        issues = []
        for issue_data in MOCK_JIRA_JQL_RESPONSE_SIMPLIFIED["issues"]:
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = issue_data
            issues.append(mock_issue)
        # Mock the JiraSearchResult object returned by search_issues
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
        **additional_fields,  # Capture additional fields
    ):
        if not project_key or project_key.strip() == "":
            raise ValueError("valid project is required")

        # Convert components string to list if provided as a string
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
            **additional_fields,  # Include additional fields in the mock response
        }
        mock_issue.to_simplified_dict.return_value = response_data
        return mock_issue

    mock_fetcher.create_issue.side_effect = mock_create_issue

    # Configure batch_create_issues
    def mock_batch_create_issues(issues, validate_only=False):
        if not isinstance(issues, list):
            # Handle case where JSON string might be passed and parsed earlier
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
                "issue_type": {
                    "name": issue_data["issue_type"]
                },  # Corrected field name
                "status": {"name": "To Do"},
            }
            mock_issues.append(mock_issue)
        return mock_issues

    mock_fetcher.batch_create_issues.side_effect = mock_batch_create_issues

    # Configure get_epic_issues
    def mock_get_epic_issues(epic_key, start=0, limit=50):
        mock_issues = []
        # Create 3 mock issues for any epic
        for i in range(1, 4):
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = {
                "key": f"TEST-{i}",
                "summary": f"Epic Issue {i}",
                "issue_type": {
                    "name": "Task" if i % 2 == 0 else "Bug"
                },  # Corrected field name
                "status": {"name": "To Do" if i % 2 == 0 else "In Progress"},
            }
            mock_issues.append(mock_issue)
        # Return a slice based on start/limit
        return mock_issues[start : start + limit]

    mock_fetcher.get_epic_issues.side_effect = mock_get_epic_issues

    # Configure resource-related methods (if needed for context, though tools are primary focus)
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

    return mock_fetcher


@pytest.fixture
def test_jira_mcp(mock_jira_fetcher):
    """Create a FastMCP instance for testing with our mock fetcher."""

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[MainAppContext, None]:
        """Test lifespan that provides our mock fetcher."""
        print("DEBUG: test_lifespan entered")
        try:
            # Simulate the structure provided by main_lifespan
            yield MainAppContext(jira=mock_jira_fetcher, read_only=False)
        finally:
            print("DEBUG: test_lifespan exited")

    # Create a new FastMCP instance with our test lifespan
    test_mcp = FastMCP(
        "TestJira", description="Test Jira MCP Server", lifespan=test_lifespan
    )

    # Import the actual tool functions we want to test
    from src.mcp_atlassian.servers.jira import (
        add_comment,  # Add other tools as needed
        add_worklog,
        batch_create_issues,
        batch_get_changelogs,
        create_issue,
        create_issue_link,
        delete_issue,
        download_attachments,
        get_agile_boards,
        get_board_issues,
        get_issue,
        get_link_types,
        get_project_issues,
        get_sprint_issues,
        get_sprints_from_board,
        get_transitions,
        get_worklog,
        link_to_epic,
        remove_issue_link,
        search,
        search_fields,
        transition_issue,
        update_issue,
        update_sprint,
    )

    # Register the tool functions with our test MCP instance
    test_mcp.tool()(get_issue)
    test_mcp.tool()(search)
    test_mcp.tool()(search_fields)
    test_mcp.tool()(get_project_issues)
    test_mcp.tool()(get_transitions)
    test_mcp.tool()(get_worklog)
    test_mcp.tool()(download_attachments)
    test_mcp.tool()(get_agile_boards)
    test_mcp.tool()(get_board_issues)
    test_mcp.tool()(get_sprints_from_board)
    test_mcp.tool()(get_sprint_issues)
    test_mcp.tool()(get_link_types)
    # Write tools
    test_mcp.tool()(create_issue)
    test_mcp.tool()(batch_create_issues)
    test_mcp.tool()(
        batch_get_changelogs
    )  # Note: Cloud only, might need specific test setup
    test_mcp.tool()(update_issue)
    test_mcp.tool()(delete_issue)
    test_mcp.tool()(add_comment)
    test_mcp.tool()(add_worklog)
    test_mcp.tool()(link_to_epic)
    test_mcp.tool()(create_issue_link)
    test_mcp.tool()(remove_issue_link)
    test_mcp.tool()(transition_issue)
    # test_mcp.tool()(create_sprint) # Needs mock setup
    test_mcp.tool()(update_sprint)

    return test_mcp


@pytest.fixture
async def jira_client(test_jira_mcp):
    """Create a FastMCP client for testing using our test FastMCP instance."""
    transport = FastMCPTransport(test_jira_mcp)
    # Use context manager for client setup/teardown
    async with Client(transport=transport) as client:
        yield client


@pytest.mark.anyio
async def test_get_issue(jira_client, mock_jira_fetcher):
    """Test the get_issue tool with fixture data."""
    print("DEBUG: test_get_issue started")

    # Call the tool through the FastMCP client
    print("DEBUG: Inside client context manager, about to call tool")
    response = await jira_client.call_tool(
        "get_issue",
        {
            "issue_key": "TEST-123",
            "fields": "summary,description,status",
        },
    )
    print(f"DEBUG: Tool call completed, response: {response}")

    # The response is a list of TextContent objects
    assert isinstance(response, list)
    assert len(response) > 0
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the JSON content
    content = json.loads(text_content.text)
    print(f"DEBUG: Response content keys: {content.keys()}")
    assert content["key"] == "TEST-123"
    assert content["summary"] == "Test Issue Summary"  # From fixture

    # Verify the mock was called with correct parameters
    mock_jira_fetcher.get_issue.assert_called_once_with(
        issue_key="TEST-123",
        fields=["summary", "description", "status"],  # Expect list now
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    )


@pytest.mark.anyio
async def test_search(jira_client, mock_jira_fetcher):
    """Test the search tool with fixture data."""
    response = await jira_client.call_tool(
        "search",
        {
            "jql": "project = TEST",
            "fields": "summary,status",
            "limit": 10,
            "start_at": 0,  # Corrected parameter name
        },
    )

    # The response is a list of TextContent objects
    assert isinstance(response, list)
    assert len(response) > 0
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the JSON content
    content = json.loads(text_content.text)
    # The tool now returns a dict with pagination info
    assert isinstance(content, dict)
    assert "issues" in content
    assert isinstance(content["issues"], list)
    assert len(content["issues"]) >= 1
    assert content["issues"][0]["key"] == "PROJ-123"  # From fixture
    assert content["total"] > 0  # From fixture logic
    assert content["start_at"] == 0
    assert content["max_results"] == 10

    # Verify the fetcher was called with the correct parameters
    mock_jira_fetcher.search_issues.assert_called_once_with(
        jql="project = TEST",
        fields=["summary", "status"],  # Expect list
        limit=10,
        start=0,  # start, not start_at for the fetcher method
        projects_filter=None,
        expand=None,
    )


@pytest.mark.anyio
async def test_create_issue(jira_client, mock_jira_fetcher):
    """Test the create_issue tool with fixture data."""
    response = await jira_client.call_tool(
        "create_issue",
        {
            "project_key": "TEST",
            "summary": "New Issue",
            "issue_type": "Task",
            "description": "This is a new task",
            "components": "Frontend,API",  # Pass as comma-separated string
            "additional_fields": {"priority": {"name": "Medium"}},  # Pass as dict
        },
    )

    # The response is a list of TextContent objects
    assert isinstance(response, list)
    assert len(response) > 0
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the JSON content
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
    assert content["issue"]["priority"] == {"name": "Medium"}  # Check additional field

    # Verify the fetcher was called with the correct parameters
    mock_jira_fetcher.create_issue.assert_called_once_with(
        project_key="TEST",
        summary="New Issue",
        issue_type="Task",
        description="This is a new task",
        assignee=None,
        components=["Frontend", "API"],  # Expect list here
        # additional_fields are passed as **kwargs to the fetcher
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

    # Convert to JSON string for the API call - the tool expects a string
    test_issues_json = json.dumps(test_issues)

    response = await jira_client.call_tool(
        "batch_create_issues",
        {"issues": test_issues_json, "validate_only": False},
    )

    # Verify the response
    assert len(response) == 1
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the response JSON
    content = json.loads(text_content.text)
    assert "message" in content
    assert "issues" in content
    assert len(content["issues"]) == 2
    assert content["issues"][0]["key"] == "TEST-1"
    assert content["issues"][1]["key"] == "TEST-2"

    # Explicitly check call args instead of using assert_called_once_with
    # This can sometimes help with complex argument comparison issues in mocks
    call_args, call_kwargs = mock_jira_fetcher.batch_create_issues.call_args
    assert call_args[0] == test_issues
    assert "validate_only" in call_kwargs
    assert call_kwargs["validate_only"] is False


@pytest.mark.anyio
async def test_batch_create_issues_invalid_json(jira_client):
    """Test error handling for invalid JSON in batch issue creation."""
    with pytest.raises(Exception) as excinfo:  # FastMCP raises Validation Error
        await jira_client.call_tool(
            "batch_create_issues",
            {"issues": "{invalid json", "validate_only": False},
        )

    # Check error message comes from Pydantic/FastMCP validation
    assert "invalid json in issues" in str(excinfo.value).lower()
