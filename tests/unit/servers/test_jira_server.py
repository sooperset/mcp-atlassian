"""Unit tests for the Jira FastMCP server implementation."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport

from src.mcp_atlassian.jira import JiraFetcher
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
        response_data["fields_queried"] = fields
        response_data["expand_param"] = expand
        response_data["comment_limit"] = comment_limit
        response_data["properties_param"] = properties
        response_data["update_history"] = update_history
        mock_issue.to_simplified_dict.return_value = response_data
        return mock_issue

    mock_fetcher.get_issue.side_effect = mock_get_issue

    # Configure get_issue_comments to return fixture data
    def mock_get_issue_comments(issue_key, limit=10):
        return MOCK_JIRA_COMMENTS_SIMPLIFIED["comments"][:limit]

    mock_fetcher.get_issue_comments.side_effect = mock_get_issue_comments

    # Configure search_issues to return fixture data
    def mock_search_issues(jql, **kwargs):
        issues = []
        for issue_data in MOCK_JIRA_JQL_RESPONSE_SIMPLIFIED["issues"]:
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = issue_data
            issues.append(mock_issue)
        return issues

    mock_fetcher.search_issues.side_effect = mock_search_issues

    # Configure create_issue
    def mock_create_issue(
        project_key,
        summary,
        issue_type,
        description=None,
        assignee=None,
        components=None,
        additional_fields=None,
    ):
        if not project_key or project_key.strip() == "":
            raise ValueError("valid project is required")

        # Convert components string to list if provided as a string
        components_list = None
        if components:
            if isinstance(components, str):
                components_list = components.split(",")
            else:
                components_list = components

        mock_issue = MagicMock()
        response_data = {
            "key": f"{project_key}-456",
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
            "status": {"name": "Open"},
            "components": [{"name": comp} for comp in components_list]
            if components_list
            else [],
        }
        mock_issue.to_simplified_dict.return_value = response_data
        return mock_issue

    mock_fetcher.create_issue.side_effect = mock_create_issue

    # Configure batch_create_issues
    def mock_batch_create_issues(issues, validate_only=False):
        if isinstance(issues, str):
            # If it's a string (JSON), parse it
            try:
                issues = json.loads(issues)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON in issues string")

        if not isinstance(issues, list):
            raise ValueError("Issues must be a list")

        mock_issues = []
        for idx, issue_data in enumerate(issues, 1):
            mock_issue = MagicMock()
            mock_issue.to_simplified_dict.return_value = {
                "key": f"{issue_data['project_key']}-{idx}",
                "summary": issue_data["summary"],
                "type": issue_data["issue_type"],
                "status": "To Do",
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
                "type": "Task" if i % 2 == 0 else "Bug",
                "status": "To Do" if i % 2 == 0 else "In Progress",
            }
            mock_issues.append(mock_issue)
        # Return a slice based on start/limit
        return mock_issues[start : start + limit]

    mock_fetcher.get_epic_issues.side_effect = mock_get_epic_issues

    # Configure resource-related methods
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
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
        """Test lifespan that provides our mock fetcher."""
        print("DEBUG: test_lifespan entered")
        try:
            yield {"jira_fetcher": mock_jira_fetcher, "read_only": False}
        finally:
            print("DEBUG: test_lifespan exited")

    # Create a new FastMCP instance with our test lifespan
    test_mcp = FastMCP(
        "TestJira", description="Test Jira MCP Server", lifespan=test_lifespan
    )

    # Import the tool functions we want to test
    from src.mcp_atlassian.servers.jira import (
        batch_create_issues,
        create_issue,
        get_epic_issues,
        get_issue,
        search,
    )

    # Add the tools to our test FastMCP instance
    test_mcp.tool()(get_issue)
    test_mcp.tool()(search)
    test_mcp.tool()(create_issue)
    test_mcp.tool()(batch_create_issues)
    test_mcp.tool()(get_epic_issues)
    return test_mcp


@pytest.fixture
def jira_client(test_jira_mcp):
    """Create a FastMCP client for testing using our test FastMCP instance."""
    transport = FastMCPTransport(test_jira_mcp)
    client = Client(transport=transport)
    return client


@pytest.mark.anyio
async def test_get_issue(jira_client, mock_jira_fetcher):
    """Test the get_issue tool with fixture data."""
    print("DEBUG: test_get_issue started")

    # Call the tool through the FastMCP client
    async with jira_client as client:
        print("DEBUG: Inside client context manager, about to call tool")
        response = await client.call_tool(
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

    # Verify the mock was called with correct parameters
    mock_jira_fetcher.get_issue.assert_called_once_with(
        issue_key="TEST-123",
        fields="summary,description,status",
        expand=None,
        comment_limit=10,
        properties=None,
        update_history=True,
    )


@pytest.mark.anyio
async def test_search(jira_client, mock_jira_fetcher):
    """Test the search tool with fixture data."""
    async with jira_client as client:
        response = await client.call_tool(
            "search",
            {
                "jql": "project = TEST",
                "fields": "summary,status",
                "limit": 10,
            },
        )

    # The response is a list of TextContent objects
    assert isinstance(response, list)
    assert len(response) > 0
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the JSON content
    content = json.loads(text_content.text)
    # The tool returns a JSON array of issues
    assert isinstance(content, list)
    assert len(content) >= 1
    assert content[0]["key"] == "PROJ-123"  # Using the key from fixture data

    # Verify the fetcher was called with the correct parameters
    mock_jira_fetcher.search_issues.assert_called_once_with(
        jql="project = TEST",
        fields="summary,status",
        limit=10,
        start_at=0,
        projects_filter=None,
    )


@pytest.mark.anyio
async def test_create_issue(jira_client, mock_jira_fetcher):
    """Test the create_issue tool with fixture data."""
    async with jira_client as client:
        response = await client.call_tool(
            "create_issue",
            {
                "project_key": "TEST",
                "summary": "New Issue",
                "issue_type": "Task",
                "description": "This is a new task",
                "components": "Frontend,API",
            },
        )

    # The response is a list of TextContent objects
    assert isinstance(response, list)
    assert len(response) > 0
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the JSON content
    content = json.loads(text_content.text)
    assert content["key"] == "TEST-456"

    # Verify the components were properly formatted
    # (should be array of objects with 'name' property)
    assert "components" in content
    assert isinstance(content["components"], list)
    component_names = [comp["name"] for comp in content["components"]]
    assert "Frontend" in component_names
    assert "API" in component_names

    # Verify the fetcher was called with the correct parameters
    mock_jira_fetcher.create_issue.assert_called_once_with(
        project_key="TEST",
        summary="New Issue",
        issue_type="Task",
        description="This is a new task",
        assignee=None,
        components="Frontend,API",
        additional_fields="{}",
    )


@pytest.mark.anyio
async def test_create_issue_with_components(jira_client, mock_jira_fetcher):
    """Test creating a Jira issue with and without components."""
    # First test with components
    async with jira_client as client:
        response = await client.call_tool(
            "create_issue",
            {
                "project_key": "TEST",
                "summary": "Issue with Components",
                "issue_type": "Bug",
                "components": "UI,API",
            },
        )

    # Verify the response
    content = json.loads(response[0].text)
    assert content["key"] == "TEST-456"
    assert "components" in content
    component_names = [comp["name"] for comp in content["components"]]
    assert "UI" in component_names
    assert "API" in component_names

    # Reset the mock
    mock_jira_fetcher.create_issue.reset_mock()

    # Now test without components
    async with jira_client as client:
        response = await client.call_tool(
            "create_issue",
            {
                "project_key": "TEST",
                "summary": "Issue without Components",
                "issue_type": "Bug",
            },
        )

    # Verify the call was made with components=None
    call_kwargs = mock_jira_fetcher.create_issue.call_args[1]
    assert call_kwargs["components"] is None


# The following tests require batch_create_issues to be implemented in jira.py


@pytest.mark.anyio
async def test_batch_create_issues(jira_client, mock_jira_fetcher):
    """Test batch creation of Jira issues."""
    # Create test data
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

    # Convert to JSON string for the API call
    test_issues_json = json.dumps(test_issues)

    # Call the tool with a JSON string as expected by the function
    async with jira_client as client:
        response = await client.call_tool(
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

    # Verify the mock was called correctly - the implementation should parse the JSON
    # and pass the resulting list to batch_create_issues
    mock_jira_fetcher.batch_create_issues.assert_called_once_with(
        issues=test_issues, validate_only=False
    )


@pytest.mark.anyio
async def test_batch_create_issues_invalid_json(jira_client):
    """Test error handling for invalid JSON in batch issue creation."""
    async with jira_client as client:
        response = await client.call_tool(
            "batch_create_issues",
            {"issues": "{invalid json", "validate_only": False},
        )

    # Verify we got an error response
    assert len(response) == 1
    assert response[0].type == "text"
    assert "Invalid JSON" in response[0].text


@pytest.mark.anyio
async def testjira_get_epic_issues(jira_client, mock_jira_fetcher):
    """Test getting issues from an epic."""
    async with jira_client as client:
        response = await client.call_tool(
            "get_epic_issues",
            {"epic_key": "TEST-100", "limit": 10, "startAt": 0},
        )

    # Verify the response
    assert len(response) == 1
    text_content = response[0]
    assert text_content.type == "text"

    # Parse the response JSON
    content = json.loads(text_content.text)
    assert "total" in content
    assert "issues" in content
    assert content["total"] >= 2
    assert len(content["issues"]) >= 2
    assert "key" in content["issues"][0]
    assert "summary" in content["issues"][0]
    assert "status" in content["issues"][0]

    # Verify the mock was called correctly - use kwargs instead of positional args
    mock_jira_fetcher.get_epic_issues.assert_called_once_with(
        epic_key="TEST-100", start=0, limit=10
    )
