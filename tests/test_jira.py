import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from mcp_atlassian.document_types import Document
from mcp_atlassian.jira import JiraFetcher

from tests.fixtures.jira_mocks import MOCK_JIRA_ISSUE_RESPONSE, MOCK_JIRA_JQL_RESPONSE


@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables for testing."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "test_user",
            "JIRA_API_TOKEN": "test_token",
        },
    ):
        yield


@pytest.fixture
def mock_jira_fetcher(mock_env_vars):
    """Create a JiraFetcher instance with mocked Jira client."""
    with patch("mcp_atlassian.jira.Jira") as mock_jira:
        # Configure the mock Jira client
        mock_jira_instance = Mock()
        mock_jira_instance.issue.return_value = MOCK_JIRA_ISSUE_RESPONSE
        mock_jira_instance.jql.return_value = MOCK_JIRA_JQL_RESPONSE
        mock_jira.return_value = mock_jira_instance

        fetcher = JiraFetcher()
        return fetcher


def test_jira_fetcher_initialization(mock_env_vars):
    """Test JiraFetcher initialization with environment variables."""
    fetcher = JiraFetcher()
    assert fetcher.config.url == "https://example.atlassian.net"
    assert fetcher.config.username == "test_user"
    assert fetcher.config.api_token == "test_token"


def test_jira_fetcher_initialization_missing_env_vars():
    """Test JiraFetcher initialization with missing environment variables."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="Missing required Jira environment variables"):
            JiraFetcher()


def test_parse_date():
    """Test date parsing with various formats."""
    fetcher = JiraFetcher()

    # Test various date formats
    assert fetcher._parse_date("2024-01-01T10:00:00.000+0000") == "2024-01-01"
    assert fetcher._parse_date("2024-01-01T10:00:00.000-0000") == "2024-01-01"
    assert fetcher._parse_date("2024-01-01T10:00:00.000+0900") == "2024-01-01"
    assert fetcher._parse_date("2024-01-01T10:00:00.000Z") == "2024-01-01"

    # Test empty input
    assert fetcher._parse_date("") == ""

    # Test invalid date
    assert fetcher._parse_date("invalid-date") == "invalid-date"


def test_get_issue(mock_jira_fetcher):
    """Test getting a single issue."""
    document = mock_jira_fetcher.get_issue("PROJ-123")

    # Verify document content
    assert "Issue: PROJ-123" in document.page_content
    assert "Title: Test Issue Summary" in document.page_content
    assert "Type: Task" in document.page_content
    assert "Status: In Progress" in document.page_content

    # Verify metadata
    assert document.metadata["key"] == "PROJ-123"
    assert document.metadata["title"] == "Test Issue Summary"
    assert document.metadata["type"] == "Task"
    assert document.metadata["status"] == "In Progress"
    assert document.metadata["priority"] == "Medium"
    assert document.metadata["created_date"] == "2024-01-01"
    assert document.metadata["link"] == "https://example.atlassian.net/browse/PROJ-123"


def test_get_issue_with_comments(mock_jira_fetcher):
    """Test getting an issue with comments."""
    document = mock_jira_fetcher.get_issue("PROJ-123")

    # Verify comments are included in content
    assert "2024-01-01 - Comment User: This is a test comment" in document.page_content


def test_search_issues(mock_jira_fetcher):
    """Test searching for issues using JQL."""
    documents = mock_jira_fetcher.search_issues("project = PROJ")

    assert len(documents) == 1  # Our mock response has 1 issue

    # Verify the first document
    doc = documents[0]
    assert doc.metadata["key"] == "PROJ-123"
    assert doc.metadata["title"] == "Test Issue Summary"

    # Verify JQL call parameters
    mock_jira_fetcher.jira.jql.assert_called_once_with("project = PROJ", fields="*all", start=0, limit=50, expand=None)


def test_get_project_issues(mock_jira_fetcher):
    """Test getting all issues for a project."""
    documents = mock_jira_fetcher.get_project_issues("PROJ")

    assert len(documents) == 1  # Our mock response has 1 issue

    # Verify JQL query
    mock_jira_fetcher.jira.jql.assert_called_once_with(
        "project = PROJ ORDER BY created DESC",
        fields="*all",
        start=0,
        limit=50,
        expand=None,
    )


def test_error_handling(mock_jira_fetcher):
    """Test error handling in get_issue and search_issues."""
    # Mock Jira client to raise an exception
    mock_jira_fetcher.jira.issue.side_effect = Exception("API Error")

    # Test get_issue error handling
    with pytest.raises(Exception, match="API Error"):
        mock_jira_fetcher.get_issue("PROJ-123")

    # Test search_issues error handling
    mock_jira_fetcher.jira.jql.side_effect = Exception("API Error")
    with pytest.raises(Exception, match="API Error"):
        mock_jira_fetcher.search_issues("project = PROJ")


def test_clean_text(mock_jira_fetcher):
    """Test text cleaning with various inputs."""
    # Test empty text
    assert mock_jira_fetcher._clean_text("") == ""
    assert mock_jira_fetcher._clean_text(None) == ""

    # Test actual text (assuming TextPreprocessor is working)
    with patch.object(mock_jira_fetcher.preprocessor, "clean_jira_text") as mock_clean:
        mock_clean.return_value = "cleaned text"
        assert mock_jira_fetcher._clean_text("some text") == "cleaned text"
        mock_clean.assert_called_once_with("some text")


def test_create_issue(mock_jira_fetcher):
    """Test creating a new issue."""
    # Mock the create_issue response
    mock_jira_fetcher.jira.issue_create.return_value = {"key": "PROJ-123"}
    mock_jira_fetcher.jira.issue.return_value = MOCK_JIRA_ISSUE_RESPONSE

    # Create issue
    document = mock_jira_fetcher.create_issue(
        project_key="PROJ",
        summary="Test Issue",
        issue_type="Task",
        description="Test Description",
    )

    # Verify create_issue was called with correct parameters
    mock_jira_fetcher.jira.issue_create.assert_called_once_with(
        fields={
            "project": {"key": "PROJ"},
            "summary": "Test Issue",
            "issuetype": {"name": "Task"},
            "description": "Test Description",
        }
    )

    # Verify the returned document
    assert document.metadata["key"] == "PROJ-123"
    assert document.metadata["title"] == "Test Issue Summary"
    assert "Type: Task" in document.page_content


def test_create_issue_error(mock_jira_fetcher):
    """Test error handling when creating an issue."""
    mock_jira_fetcher.jira.issue_create.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        mock_jira_fetcher.create_issue(project_key="PROJ", summary="Test Issue", issue_type="Task")


def test_update_issue(mock_jira_fetcher):
    """Test updating an existing issue."""
    # Mock the update response
    mock_jira_fetcher.jira.issue_update.return_value = None
    mock_jira_fetcher.jira.issue.return_value = MOCK_JIRA_ISSUE_RESPONSE

    # Test data
    fields = {"summary": "Updated Title", "description": "Updated Description"}

    # Update issue
    document = mock_jira_fetcher.update_issue("PROJ-123", fields)

    # Verify update_issue was called with correct parameters
    mock_jira_fetcher.jira.issue_update.assert_called_once_with("PROJ-123", fields=fields)

    # Verify the returned document
    assert document.metadata["key"] == "PROJ-123"
    assert "Title: Test Issue Summary" in document.page_content


def test_update_issue_error(mock_jira_fetcher):
    """Test error handling when updating an issue."""
    mock_jira_fetcher.jira.issue_update.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        mock_jira_fetcher.update_issue("PROJ-123", {"summary": "Test"})


def test_delete_issue(mock_jira_fetcher):
    """Test deleting an issue."""
    mock_jira_fetcher.jira.delete_issue.return_value = None

    result = mock_jira_fetcher.delete_issue("PROJ-123")
    mock_jira_fetcher.jira.delete_issue.assert_called_once_with("PROJ-123")

    assert result is True


def test_delete_issue_error(mock_jira_fetcher):
    """Test error handling when deleting an issue."""
    mock_jira_fetcher.jira.delete_issue.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        mock_jira_fetcher.delete_issue("PROJ-123")

    mock_jira_fetcher.jira.delete_issue.assert_called_once_with("PROJ-123")


def test_get_jira_field_ids(mock_jira_fetcher):
    """Test the get_jira_field_ids method."""
    # Mock the fields API response
    mock_fields = [
        {"id": "customfield_10014", "name": "Epic Link", "type": "any"},
        {"id": "customfield_10011", "name": "Epic Name", "type": "any"},
        {"id": "customfield_10010", "name": "Epic Status", "type": "any"},
        {"id": "customfield_10013", "name": "Epic Colour", "type": "any"},
        {"id": "parent", "name": "Parent", "type": "any"},
    ]

    # Set up the mock
    mock_jira_fetcher.jira.fields.return_value = mock_fields

    # Call the method
    field_ids = mock_jira_fetcher.get_jira_field_ids()

    # Verify results
    assert field_ids["epic_link"] == "customfield_10014"
    assert field_ids["epic_name"] == "customfield_10011"
    assert field_ids["epic_status"] == "customfield_10010"
    assert field_ids["epic_color"] == "customfield_10013"
    assert field_ids["parent"] == "parent"

    # Verify the fields method was called
    mock_jira_fetcher.jira.fields.assert_called_once()

    # Test caching - should not call the API again
    mock_jira_fetcher.jira.fields.reset_mock()
    field_ids = mock_jira_fetcher.get_jira_field_ids()
    mock_jira_fetcher.jira.fields.assert_not_called()


def test_link_issue_to_epic_with_discovered_fields(mock_jira_fetcher):
    """Test linking an issue to an epic using discovered field IDs."""
    # Mock the issue response to verify it's an Epic
    mock_epic = {"fields": {"issuetype": {"name": "Epic"}}}

    # Mock the field discovery response
    mock_fields = [{"id": "customfield_10014", "name": "Epic Link", "type": "any"}]

    # Set up the mocks
    mock_jira_fetcher.jira.issue.return_value = mock_epic
    mock_jira_fetcher.jira.fields.return_value = mock_fields

    # Mock the successful update
    mock_jira_fetcher.jira.issue_update.return_value = None

    # Mock the get_issue response for the return value
    mock_jira_fetcher._format_issue_as_document = MagicMock(
        return_value=Document(
            page_content="Issue content",
            metadata={
                "key": "PROJ-123",
                "title": "Test Issue",
                "type": "Task",
                "status": "Open",
                "created_date": "2023-01-01",
            },
        )
    )

    # Call the method
    result = mock_jira_fetcher.link_issue_to_epic("PROJ-123", "PROJ-456")

    # Verify the issue_update was called with the discovered field
    mock_jira_fetcher.jira.issue_update.assert_called_with("PROJ-123", fields={"customfield_10014": "PROJ-456"})

    # Verify result
    assert result.metadata["key"] == "PROJ-123"


def test_markdown_to_jira_conversion(mock_jira_fetcher):
    """Test conversion of Markdown to Jira markup."""
    # Test headers
    assert mock_jira_fetcher._markdown_to_jira("# Heading 1") == "h1. Heading 1"
    assert mock_jira_fetcher._markdown_to_jira("## Heading 2") == "h2. Heading 2"

    # Test text formatting
    assert mock_jira_fetcher._markdown_to_jira("**bold text**") == "*bold text*"
    assert mock_jira_fetcher._markdown_to_jira("*italic text*") == "_italic text_"

    # Test code blocks
    assert mock_jira_fetcher._markdown_to_jira("`code`") == "{{{code}}}"
    assert mock_jira_fetcher._markdown_to_jira("```\nmultiline code\n```") == "{code}\nmultiline code\n{code}"

    # Test lists
    assert mock_jira_fetcher._markdown_to_jira("- Item 1") == "* Item 1"
    assert mock_jira_fetcher._markdown_to_jira("1. Item 1") == "# Item 1"

    # Test complex Markdown
    complex_markdown = """
# Project Overview

## Introduction
This project aims to **improve** the user experience.

### Features
- Feature 1
- Feature 2

### Code Example
```python
def hello():
    print("Hello World")
```

For more information, see [our website](https://example.com).
"""

    expected_jira_markup = """
h1. Project Overview

h2. Introduction
This project aims to *improve* the user experience.

h3. Features
* Feature 1
* Feature 2

h3. Code Example
{code}python
def hello():
    print("Hello World")
{code}

For more information, see [our website|https://example.com].
"""

    # We're not comparing exactly because spacing might be different,
    # but we check that key conversions happened
    converted = mock_jira_fetcher._markdown_to_jira(complex_markdown)
    assert "h1. Project Overview" in converted
    assert "h2. Introduction" in converted
    assert "*improve*" in converted
    assert "* Feature 1" in converted
    assert "{code}" in converted
    assert "[our website|https://example.com]" in converted


def test_get_available_transitions(mock_jira_fetcher):
    """Test getting available transitions for an issue."""
    # Mock the transitions API response
    mock_transitions = {
        "transitions": [
            {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]
    }

    mock_jira_fetcher.jira.get_issue_transitions.return_value = mock_transitions

    # Call the method
    transitions = mock_jira_fetcher.get_available_transitions("PROJ-123")

    # Verify results
    assert len(transitions) == 3
    assert transitions[0]["id"] == "11"
    assert transitions[0]["name"] == "To Do"
    assert transitions[0]["to_status"] == "To Do"
    assert transitions[1]["id"] == "21"
    assert transitions[1]["to_status"] == "In Progress"

    # Verify the API was called correctly
    mock_jira_fetcher.jira.get_issue_transitions.assert_called_once_with("PROJ-123")


def test_transition_issue(mock_jira_fetcher):
    """Test transitioning an issue to a new status."""
    # Mock the transition API call
    mock_jira_fetcher.jira.issue_transition.return_value = None

    # Mock the get_issue response for the return value
    mock_jira_fetcher._format_issue_as_document = MagicMock(
        return_value=Document(
            page_content="Issue content",
            metadata={
                "key": "PROJ-123",
                "title": "Test Issue",
                "type": "Task",
                "status": "In Progress",  # New status after transition
                "created_date": "2023-01-01",
            },
        )
    )

    # Call the method with fields and comment
    result = mock_jira_fetcher.transition_issue(
        "PROJ-123", "21", fields={"customfield_10001": "High"}, comment="Moving to **In Progress**"
    )

    # Verify the API was called with the right parameters
    expected_transition_data = {
        "transition": {"id": "21"},
        "fields": {"customfield_10001": "High"},
        "update": {"comment": [{"add": {"body": "Moving to *In Progress*"}}]},
    }

    mock_jira_fetcher.jira.issue_transition.assert_called_once_with("PROJ-123", expected_transition_data)

    # Verify result
    assert result.metadata["key"] == "PROJ-123"
    assert result.metadata["status"] == "In Progress"


def test_update_issue_with_status_transition(mock_jira_fetcher):
    """Test updating an issue with a status change that requires a transition."""
    # Mock the transitions API response
    mock_transitions = {
        "transitions": [
            {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
        ]
    }

    # Set up mock responses
    mock_jira_fetcher.jira.get_issue_transitions.return_value = mock_transitions
    mock_jira_fetcher.jira.issue_transition.return_value = None

    # Mock the get_issue response for the return value
    mock_jira_fetcher._format_issue_as_document = MagicMock(
        return_value=Document(
            page_content="Issue content",
            metadata={
                "key": "PROJ-123",
                "title": "Test Issue",
                "type": "Task",
                "status": "In Progress",
                "created_date": "2023-01-01",
            },
        )
    )

    # Call update_issue with a status change
    result = mock_jira_fetcher.update_issue("PROJ-123", fields={"status": "In Progress", "customfield_10001": "High"})

    # Verify transitions were fetched
    mock_jira_fetcher.jira.get_issue_transitions.assert_called_once_with("PROJ-123")

    # Verify transition was used for status update
    mock_jira_fetcher.jira.issue_transition.assert_called_once_with(
        "PROJ-123", {"transition": {"id": "21"}, "fields": {"customfield_10001": "High"}}
    )

    # Verify result
    assert result.metadata["key"] == "PROJ-123"
    assert result.metadata["status"] == "In Progress"
