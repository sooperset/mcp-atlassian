"""
Tests for the JiraComment Pydantic model.
"""

from copy import deepcopy
from typing import Any

import pytest

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from mcp_atlassian.models.jira import (
    JiraComment,
    JiraIssue,
    JiraUser,
)


@pytest.mark.parametrize(
    "visibility",
    [
        {"type": "group", "value": "developers", "identifier": "group-id"},
        {"type": "role", "value": "Administrators"},
        None,
        {},
        "invalid",
    ],
    ids=["group", "role", "unrestricted", "empty", "malformed"],
)
def test_comment_visibility_survives_model_serialization(visibility: Any) -> None:
    """Serialize the stored restriction without changing the API response."""
    data = {"id": "10001", "body": "Comment", "visibility": visibility}
    original = deepcopy(data)
    comment = JiraComment.from_api_response(data)
    output = comment.to_simplified_dict()

    if isinstance(visibility, dict) and visibility:
        assert output["visibility"] == visibility
        assert comment.visibility == visibility
    else:
        assert "visibility" not in output
    assert output["body"] == "Comment"
    assert data == original


@pytest.mark.parametrize("use_display_names", [False, True])
def test_issue_output_preserves_comment_visibility(use_display_names: bool) -> None:
    """Both issue response formats retain the stored comment restriction."""
    visibility = {"type": "group", "value": "developers", "identifier": "group-id"}
    issue = JiraIssue.from_api_response(
        {
            "id": "1",
            "key": "TEST-1",
            "fields": {
                "comment": {
                    "comments": [
                        {"id": "10001", "body": "Comment", "visibility": visibility}
                    ]
                }
            },
        },
        requested_fields="comment",
    )
    output = (
        issue.to_display_name_dict()
        if use_display_names
        else issue.to_simplified_dict()
    )
    assert output["comments"][0]["visibility"] == visibility


class TestJiraComment:
    """Tests for the JiraComment model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraComment from valid API data."""
        data = {
            "id": "10000",
            "body": "This is a test comment",
            "created": "2024-01-01T12:00:00.000+0000",
            "updated": "2024-01-01T12:00:00.000+0000",
            "author": {
                "accountId": "user123",
                "displayName": "Comment User",
                "active": True,
            },
        }
        comment = JiraComment.from_api_response(data)
        assert comment.id == "10000"
        assert comment.body == "This is a test comment"
        assert comment.created == "2024-01-01T12:00:00.000+0000"
        assert comment.updated == "2024-01-01T12:00:00.000+0000"
        assert comment.author is not None
        assert comment.author.display_name == "Comment User"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraComment from empty data."""
        comment = JiraComment.from_api_response({})
        assert comment.id == JIRA_DEFAULT_ID
        assert comment.body == EMPTY_STRING
        assert comment.created == EMPTY_STRING
        assert comment.updated == EMPTY_STRING
        assert comment.author is None

    def test_to_simplified_dict(self):
        """Test converting JiraComment to a simplified dictionary."""
        comment = JiraComment(
            id="10000",
            body="This is a test comment",
            created="2024-01-01T12:00:00.000+0000",
            updated="2024-01-01T12:00:00.000+0000",
            author=JiraUser(account_id="user123", display_name="Comment User"),
        )
        simplified = comment.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["id"] == "10000"
        assert "body" in simplified
        assert simplified["body"] == "This is a test comment"
        assert "created" in simplified
        assert isinstance(simplified["created"], str)
        assert "author" in simplified
        assert isinstance(simplified["author"], dict)
        assert simplified["author"]["display_name"] == "Comment User"

    def test_to_simplified_dict_default_id(self):
        """Test that default comment ID is included in simplified dict."""
        comment = JiraComment()
        simplified = comment.to_simplified_dict()
        assert simplified["id"] == JIRA_DEFAULT_ID

    def test_to_simplified_dict_no_author(self):
        """Test comment ID present even without optional fields."""
        comment = JiraComment(id="99999", body="text only")
        simplified = comment.to_simplified_dict()
        assert simplified["id"] == "99999"
        assert "author" not in simplified
