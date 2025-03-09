"""Tests for the Jira Comments mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.comments import CommentsMixin


class TestCommentsMixin:
    """Tests for the CommentsMixin class."""

    @pytest.fixture
    def comments_mixin(self, jira_client):
        """Create a CommentsMixin instance with mocked dependencies."""
        mixin = CommentsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Mock methods that are typically provided by other mixins
        mixin._clean_text = MagicMock(side_effect=lambda text: text if text else "")
        mixin.preprocessor = MagicMock()
        mixin.preprocessor.markdown_to_jira = MagicMock(side_effect=lambda text: text)

        return mixin

    def test_get_issue_comments_basic(self, comments_mixin):
        """Test basic functionality of get_issue_comments."""
        # Setup mock response
        mock_comments = {
            "comments": [
                {
                    "id": "10001",
                    "body": "This is a comment",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T10:30:00.000+0000",
                    "author": {"displayName": "Test User"},
                }
            ]
        }
        comments_mixin.jira.issue_get_comments.return_value = mock_comments

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        comments_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["body"] == "This is a comment"
        assert result[0]["author"] == "Test User"
        assert "created" in result[0]
        assert "updated" in result[0]

    def test_get_issue_comments_with_limit(self, comments_mixin):
        """Test get_issue_comments respects the limit parameter."""
        # Setup mock response with multiple comments
        mock_comments = {
            "comments": [
                {
                    "id": "10001",
                    "body": "Comment 1",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T10:30:00.000+0000",
                    "author": {"displayName": "Test User"},
                },
                {
                    "id": "10002",
                    "body": "Comment 2",
                    "created": "2024-01-01T11:00:00.000+0000",
                    "updated": "2024-01-01T11:30:00.000+0000",
                    "author": {"displayName": "Another User"},
                },
            ]
        }
        comments_mixin.jira.issue_get_comments.return_value = mock_comments

        # Call the method with limit=1
        result = comments_mixin.get_issue_comments("TEST-123", limit=1)

        # Verify only one comment is returned
        assert len(result) == 1
        assert result[0]["id"] == "10001"

    def test_get_issue_comments_with_missing_fields(self, comments_mixin):
        """Test get_issue_comments handles missing fields gracefully."""
        # Setup mock response with missing fields
        mock_comments = {
            "comments": [
                {
                    "id": "10001",
                    # Missing body
                    "created": "2024-01-01T10:00:00.000+0000",
                    # Missing updated
                    # Missing author
                }
            ]
        }
        comments_mixin.jira.issue_get_comments.return_value = mock_comments

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["body"] == ""  # Should default to empty string
        assert result[0]["author"] == "Unknown"  # Should default to "Unknown"

    def test_get_issue_comments_with_empty_response(self, comments_mixin):
        """Test get_issue_comments handles empty response."""
        # Setup mock response with no comments
        comments_mixin.jira.issue_get_comments.return_value = {}

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_issue_comments_with_error(self, comments_mixin):
        """Test get_issue_comments error handling."""
        # Setup mock to raise exception
        comments_mixin.jira.issue_get_comments.side_effect = Exception(
            "Comment fetch error"
        )

        # Call the method and verify exception
        with pytest.raises(
            Exception, match="Error getting comments: Comment fetch error"
        ):
            comments_mixin.get_issue_comments("TEST-123")

    def test_add_comment_basic(self, comments_mixin):
        """Test basic functionality of add_comment."""
        # Setup mock response
        mock_result = {
            "id": "10001",
            "body": "Test comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "Test User"},
        }
        comments_mixin.jira.issue_add_comment.return_value = mock_result

        # Call the method
        result = comments_mixin.add_comment("TEST-123", "Test comment")

        # Verify
        comments_mixin.jira.issue_add_comment.assert_called_once_with(
            "TEST-123", "Test comment"
        )
        comments_mixin.preprocessor.markdown_to_jira.assert_called_once_with(
            "Test comment"
        )
        assert result["id"] == "10001"
        assert result["body"] == "Test comment"
        assert result["author"] == "Test User"
        assert "created" in result

    def test_add_comment_with_markdown_conversion(self, comments_mixin):
        """Test add_comment converts markdown to Jira format."""
        # Setup mock response
        mock_result = {
            "id": "10001",
            "body": "Jira formatted text",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "Test User"},
        }
        comments_mixin.jira.issue_add_comment.return_value = mock_result

        # Setup markdown conversion - important to reset the side_effect
        comments_mixin.preprocessor.markdown_to_jira = MagicMock(
            return_value="Jira formatted text"
        )

        # Call the method
        result = comments_mixin.add_comment("TEST-123", "**Markdown** text")

        # Verify
        comments_mixin.preprocessor.markdown_to_jira.assert_called_once_with(
            "**Markdown** text"
        )
        comments_mixin.jira.issue_add_comment.assert_called_once_with(
            "TEST-123", "Jira formatted text"
        )

    def test_add_comment_with_empty_comment(self, comments_mixin):
        """Test add_comment handles empty comment text."""
        # Setup mock response
        mock_result = {
            "id": "10001",
            "body": "",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "Test User"},
        }
        comments_mixin.jira.issue_add_comment.return_value = mock_result

        # Need to reset the mock
        comments_mixin.preprocessor.markdown_to_jira.reset_mock()

        # Call the method
        result = comments_mixin.add_comment("TEST-123", "")

        # Verify - empty string bypasses conversion
        assert comments_mixin.preprocessor.markdown_to_jira.call_count == 0
        comments_mixin.jira.issue_add_comment.assert_called_once_with("TEST-123", "")
        assert result["body"] == ""

    def test_add_comment_with_error(self, comments_mixin):
        """Test add_comment error handling."""
        # Setup mock to raise exception
        comments_mixin.jira.issue_add_comment.side_effect = Exception(
            "Comment add error"
        )

        # Call the method and verify exception
        with pytest.raises(Exception, match="Error adding comment: Comment add error"):
            comments_mixin.add_comment("TEST-123", "Test comment")

    def test_markdown_to_jira(self, comments_mixin):
        """Test markdown to Jira conversion."""
        # Setup - need to replace the mock entirely
        comments_mixin.preprocessor.markdown_to_jira = MagicMock(
            return_value="Jira text"
        )

        # Call the method
        result = comments_mixin._markdown_to_jira("Markdown text")

        # Verify
        assert result == "Jira text"
        comments_mixin.preprocessor.markdown_to_jira.assert_called_once_with(
            "Markdown text"
        )

    def test_markdown_to_jira_with_empty_text(self, comments_mixin):
        """Test markdown to Jira conversion with empty text."""
        # Call the method
        result = comments_mixin._markdown_to_jira("")

        # Verify
        assert result == ""
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()

    def test_parse_date(self, comments_mixin):
        """Test date parsing."""
        # Test ISO format
        assert (
            comments_mixin._parse_date("2024-01-01T10:00:00.000+0000") == "2024-01-01"
        )

        # Test invalid format
        assert comments_mixin._parse_date("invalid date") == "invalid date"

        # Test empty string
        assert comments_mixin._parse_date("") == ""
