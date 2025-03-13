"""Tests for the Jira FormattingMixin."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.jira.formatting import FormattingMixin
from mcp_atlassian.preprocessing import JiraPreprocessor


@pytest.fixture
def formatting_mixin():
    """Fixture to create a FormattingMixin instance for testing."""
    # Create the mixin without calling its __init__ to avoid config dependencies
    with patch.object(FormattingMixin, "__init__", return_value=None):
        mixin = FormattingMixin()

    # Set up necessary mocks
    mixin.jira = MagicMock()
    mixin.preprocessor = MagicMock(spec=JiraPreprocessor)
    return mixin


def test_markdown_to_jira(formatting_mixin):
    """Test markdown_to_jira method with valid input."""
    formatting_mixin.preprocessor.markdown_to_jira.return_value = "Converted text"

    result = formatting_mixin.markdown_to_jira("# Markdown text")

    assert result == "Converted text"
    formatting_mixin.preprocessor.markdown_to_jira.assert_called_once_with(
        "# Markdown text"
    )


def test_markdown_to_jira_empty_input(formatting_mixin):
    """Test markdown_to_jira method with empty input."""
    result = formatting_mixin.markdown_to_jira("")

    assert result == ""
    formatting_mixin.preprocessor.markdown_to_jira.assert_not_called()


def test_markdown_to_jira_exception(formatting_mixin):
    """Test markdown_to_jira method with exception."""
    formatting_mixin.preprocessor.markdown_to_jira.side_effect = Exception(
        "Conversion error"
    )

    result = formatting_mixin.markdown_to_jira("# Markdown text")

    assert result == "# Markdown text"  # Should return original text on error
    formatting_mixin.preprocessor.markdown_to_jira.assert_called_once()


def test_format_issue_content_basic(formatting_mixin):
    """Test format_issue_content method with basic inputs."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
        }
    }
    description = "This is a test issue."
    comments = []
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": None, "epic_name": None}

    result = formatting_mixin.format_issue_content(
        issue_key, issue, description, comments, created_date, epic_info
    )

    # Check that the result contains all the basic information
    assert "Issue: TEST-123" in result
    assert "Title: Test issue" in result
    assert "Type: Bug" in result
    assert "Status: Open" in result
    assert "Created: 2023-01-01 12:00:00" in result
    assert "Description:" in result
    assert "This is a test issue." in result
    assert "Comments:" not in result  # No comments


def test_format_issue_content_with_epic(formatting_mixin):
    """Test format_issue_content method with epic information."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
        }
    }
    description = "This is a test issue."
    comments = []
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": "EPIC-1", "epic_name": "Test Epic"}

    result = formatting_mixin.format_issue_content(
        issue_key, issue, description, comments, created_date, epic_info
    )

    # Check that the result contains the epic information
    assert "Epic: EPIC-1 - Test Epic" in result


def test_format_issue_content_with_comments(formatting_mixin):
    """Test format_issue_content method with comments."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
        }
    }
    description = "This is a test issue."
    comments = [
        {"created": "2023-01-02", "author": "User1", "body": "Comment 1"},
        {"created": "2023-01-03", "author": "User2", "body": "Comment 2"},
    ]
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": None, "epic_name": None}

    result = formatting_mixin.format_issue_content(
        issue_key, issue, description, comments, created_date, epic_info
    )

    # Check that the result contains the comments
    assert "Comments:" in result
    assert "2023-01-02 - User1: Comment 1" in result
    assert "2023-01-03 - User2: Comment 2" in result


def test_create_issue_metadata_basic(formatting_mixin):
    """Test create_issue_metadata method with basic inputs."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "project": {"key": "TEST", "name": "Test Project"},
        }
    }
    comments = []
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": None, "epic_name": None}

    result = formatting_mixin.create_issue_metadata(
        issue_key, issue, comments, created_date, epic_info
    )

    # Check that the result contains all the basic metadata
    assert result["key"] == "TEST-123"
    assert result["summary"] == "Test issue"
    assert result["type"] == "Bug"
    assert result["status"] == "Open"
    assert result["created"] == "2023-01-01 12:00:00"
    assert result["source"] == "jira"
    assert result["project"] == "TEST"
    assert result["project_name"] == "Test Project"
    assert result["comment_count"] == 0
    assert "epic_key" not in result
    assert "epic_name" not in result


def test_create_issue_metadata_with_assignee_and_reporter(formatting_mixin):
    """Test create_issue_metadata method with assignee and reporter."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "assignee": {"displayName": "John Doe", "name": "jdoe"},
            "reporter": {"displayName": "Jane Smith", "name": "jsmith"},
            "project": {"key": "TEST", "name": "Test Project"},
        }
    }
    comments = []
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": None, "epic_name": None}

    result = formatting_mixin.create_issue_metadata(
        issue_key, issue, comments, created_date, epic_info
    )

    # Check that the result contains assignee and reporter
    assert result["assignee"] == "John Doe"
    assert result["reporter"] == "Jane Smith"


def test_create_issue_metadata_with_priority(formatting_mixin):
    """Test create_issue_metadata method with priority."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "project": {"key": "TEST", "name": "Test Project"},
        }
    }
    comments = []
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": None, "epic_name": None}

    result = formatting_mixin.create_issue_metadata(
        issue_key, issue, comments, created_date, epic_info
    )

    # Check that the result contains priority
    assert result["priority"] == "High"


def test_create_issue_metadata_with_epic(formatting_mixin):
    """Test create_issue_metadata method with epic information."""
    issue_key = "TEST-123"
    issue = {
        "fields": {
            "summary": "Test issue",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "project": {"key": "TEST", "name": "Test Project"},
        }
    }
    comments = []
    created_date = "2023-01-01 12:00:00"
    epic_info = {"epic_key": "EPIC-1", "epic_name": "Test Epic"}

    result = formatting_mixin.create_issue_metadata(
        issue_key, issue, comments, created_date, epic_info
    )

    # Check that the result contains epic information
    assert result["epic_key"] == "EPIC-1"
    assert result["epic_name"] == "Test Epic"


def test_format_date_valid(formatting_mixin):
    """Test format_date method with valid date."""
    result = formatting_mixin.format_date("2023-01-01T12:00:00.000Z")

    assert result == "2023-01-01 12:00:00"


def test_format_date_invalid(formatting_mixin):
    """Test format_date method with invalid date."""
    result = formatting_mixin.format_date("invalid-date")

    assert result == "invalid-date"  # Should return original on error


def test_format_jira_date_valid(formatting_mixin):
    """Test format_jira_date method with valid date."""
    result = formatting_mixin.format_jira_date("2023-01-01T12:00:00.000Z")

    assert result == "2023-01-01 12:00:00"


def test_format_jira_date_none(formatting_mixin):
    """Test format_jira_date method with None input."""
    result = formatting_mixin.format_jira_date(None)

    assert result == ""


def test_format_jira_date_invalid(formatting_mixin):
    """Test format_jira_date method with invalid date."""
    result = formatting_mixin.format_jira_date("invalid-date")

    assert result == "invalid-date"  # Should return original on error


def test_parse_date_for_api_valid(formatting_mixin):
    """Test parse_date_for_api method with valid date."""
    result = formatting_mixin.parse_date_for_api("2023-01-01T12:00:00.000Z")

    assert result == "2023-01-01"


def test_parse_date_for_api_invalid(formatting_mixin):
    """Test parse_date_for_api method with invalid date."""
    result = formatting_mixin.parse_date_for_api("invalid-date")

    assert result == "invalid-date"  # Should return original on error


def test_extract_epic_information_no_fields(formatting_mixin):
    """Test extract_epic_information method with issue having no fields."""
    issue = {}

    result = formatting_mixin.extract_epic_information(issue)

    assert result == {"epic_key": None, "epic_name": None}


def test_extract_epic_information_with_field_ids(formatting_mixin):
    """Test extract_epic_information method with field IDs available."""
    issue = {"fields": {"customfield_10001": "EPIC-1"}}

    # Mock get_jira_field_ids method
    field_ids = {"Epic Link": "customfield_10001", "Epic Name": "customfield_10002"}
    formatting_mixin.get_jira_field_ids = MagicMock(return_value=field_ids)

    # Mock get_issue method
    epic_issue = {"fields": {"customfield_10002": "Test Epic"}}
    formatting_mixin.get_issue = MagicMock(return_value=epic_issue)

    result = formatting_mixin.extract_epic_information(issue)

    assert result == {"epic_key": "EPIC-1", "epic_name": "Test Epic"}
    formatting_mixin.get_jira_field_ids.assert_called_once()
    formatting_mixin.get_issue.assert_called_once_with("EPIC-1")


def test_extract_epic_information_without_get_issue(formatting_mixin):
    """Test extract_epic_information method without get_issue method."""
    issue = {"fields": {"customfield_10001": "EPIC-1"}}

    # Mock get_jira_field_ids method
    field_ids = {"Epic Link": "customfield_10001", "Epic Name": "customfield_10002"}
    formatting_mixin.get_jira_field_ids = MagicMock(return_value=field_ids)

    # Remove get_issue attribute if exists
    if hasattr(formatting_mixin, "get_issue"):
        delattr(formatting_mixin, "get_issue")

    result = formatting_mixin.extract_epic_information(issue)

    assert result == {"epic_key": "EPIC-1", "epic_name": None}
    formatting_mixin.get_jira_field_ids.assert_called_once()


def test_extract_epic_information_get_issue_exception(formatting_mixin):
    """Test extract_epic_information method with get_issue exception."""
    issue = {"fields": {"customfield_10001": "EPIC-1"}}

    # Mock get_jira_field_ids method
    field_ids = {"Epic Link": "customfield_10001", "Epic Name": "customfield_10002"}
    formatting_mixin.get_jira_field_ids = MagicMock(return_value=field_ids)

    # Mock get_issue method to raise exception
    formatting_mixin.get_issue = MagicMock(side_effect=Exception("API error"))

    result = formatting_mixin.extract_epic_information(issue)

    assert result == {"epic_key": "EPIC-1", "epic_name": None}
    formatting_mixin.get_jira_field_ids.assert_called_once()
    formatting_mixin.get_issue.assert_called_once()


def test_sanitize_html_valid(formatting_mixin):
    """Test sanitize_html method with valid HTML."""
    html_content = "<p>This is <b>bold</b> text.</p>"

    result = formatting_mixin.sanitize_html(html_content)

    assert result == "This is bold text."


def test_sanitize_html_with_entities(formatting_mixin):
    """Test sanitize_html method with HTML entities."""
    html_content = "<p>This &amp; that</p>"

    result = formatting_mixin.sanitize_html(html_content)

    assert result == "This & that"


def test_sanitize_html_empty(formatting_mixin):
    """Test sanitize_html method with empty input."""
    result = formatting_mixin.sanitize_html("")

    assert result == ""


def test_sanitize_html_exception(formatting_mixin):
    """Test sanitize_html method with exception."""
    # Mock re.sub to raise exception
    with patch("re.sub", side_effect=Exception("Regex error")):
        result = formatting_mixin.sanitize_html("<p>Test</p>")

        assert result == "<p>Test</p>"  # Should return original on error


def test_sanitize_transition_fields_basic(formatting_mixin):
    """Test sanitize_transition_fields method with basic fields."""
    fields = {"summary": "Test issue", "description": "This is a test issue."}

    result = formatting_mixin.sanitize_transition_fields(fields)

    assert result == fields


def test_sanitize_transition_fields_with_assignee(formatting_mixin):
    """Test sanitize_transition_fields method with assignee field."""
    fields = {"summary": "Test issue", "assignee": "jdoe"}

    # Mock _get_account_id method
    formatting_mixin._get_account_id = MagicMock(return_value="account-123")

    result = formatting_mixin.sanitize_transition_fields(fields)

    assert result["summary"] == "Test issue"
    assert result["assignee"] == {"accountId": "account-123"}
    formatting_mixin._get_account_id.assert_called_once_with("jdoe")


def test_sanitize_transition_fields_with_assignee_dict(formatting_mixin):
    """Test sanitize_transition_fields method with assignee as dictionary."""
    fields = {"summary": "Test issue", "assignee": {"accountId": "account-123"}}

    # Mock _get_account_id method
    formatting_mixin._get_account_id = MagicMock()

    result = formatting_mixin.sanitize_transition_fields(fields)

    assert result["summary"] == "Test issue"
    assert result["assignee"] == {"accountId": "account-123"}
    formatting_mixin._get_account_id.assert_not_called()


def test_sanitize_transition_fields_with_reporter(formatting_mixin):
    """Test sanitize_transition_fields method with reporter field."""
    fields = {"summary": "Test issue", "reporter": "jsmith"}

    # Mock _get_account_id method
    formatting_mixin._get_account_id = MagicMock(return_value="account-456")

    result = formatting_mixin.sanitize_transition_fields(fields)

    assert result["summary"] == "Test issue"
    assert result["reporter"] == {"accountId": "account-456"}
    formatting_mixin._get_account_id.assert_called_once_with("jsmith")


def test_sanitize_transition_fields_without_get_account_id(formatting_mixin):
    """Test sanitize_transition_fields method without _get_account_id method."""
    fields = {"summary": "Test issue", "assignee": "jdoe"}

    # Remove _get_account_id attribute if exists
    if hasattr(formatting_mixin, "_get_account_id"):
        delattr(formatting_mixin, "_get_account_id")

    result = formatting_mixin.sanitize_transition_fields(fields)

    assert result["summary"] == "Test issue"
    assert "assignee" not in result


def test_sanitize_transition_fields_with_none_value(formatting_mixin):
    """Test sanitize_transition_fields method with None value."""
    fields = {"summary": "Test issue", "assignee": None}

    result = formatting_mixin.sanitize_transition_fields(fields)

    assert result == {"summary": "Test issue"}


def test_add_comment_to_transition_data_with_comment(formatting_mixin):
    """Test add_comment_to_transition_data method with comment."""
    transition_data = {"transition": {"id": "10"}}
    comment = "This is a comment"

    # Mock markdown_to_jira method
    formatting_mixin.markdown_to_jira = MagicMock(return_value="Converted comment")

    result = formatting_mixin.add_comment_to_transition_data(transition_data, comment)

    assert result["transition"] == {"id": "10"}
    assert result["update"]["comment"][0]["add"]["body"] == "Converted comment"
    formatting_mixin.markdown_to_jira.assert_called_once_with("This is a comment")


def test_add_comment_to_transition_data_without_comment(formatting_mixin):
    """Test add_comment_to_transition_data method without comment."""
    transition_data = {"transition": {"id": "10"}}

    result = formatting_mixin.add_comment_to_transition_data(transition_data, None)

    assert result == transition_data  # Should return unmodified data
