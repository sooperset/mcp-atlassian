"""Tests for the Jira Comments mixin."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from mcp_atlassian.jira.comments import CommentsMixin


class TestCommentsMixin:
    """Tests for the CommentsMixin class."""

    @pytest.fixture
    def comments_mixin(self, jira_client):
        """Create a CommentsMixin instance with mocked dependencies."""
        mixin = CommentsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Set up a mock preprocessor with markdown_to_jira method
        mixin.preprocessor = Mock()
        mixin.preprocessor.markdown_to_jira = Mock(
            return_value="*This* is _Jira_ formatted"
        )

        # Mock the clean_text method
        mixin._clean_text = Mock(side_effect=lambda x: x)

        return mixin

    def test_get_issue_comments_basic(self, comments_mixin):
        """Test get_issue_comments with basic data."""
        # Setup mock response
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": "This is a comment",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T11:00:00.000+0000",
                    "author": {"displayName": "John Doe"},
                }
            ]
        }

        # Mock the _parse_date method for this test
        with patch.object(
            comments_mixin,
            "_parse_date",
            side_effect=lambda x: x.split("T")[0] if x and "T" in x else x,
        ):
            # Call the method
            result = comments_mixin.get_issue_comments("TEST-123")

            # Verify
            comments_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
            assert len(result) == 1
            assert result[0]["id"] == "10001"
            assert result[0]["body"] == "This is a comment"
            assert result[0]["created"] == "2024-01-01"  # Parsed date
            assert result[0]["author"] == "John Doe"

    def test_get_issue_comments_with_limit(self, comments_mixin):
        """Test get_issue_comments with limit parameter."""
        # Setup mock response with multiple comments
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": "First comment",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "author": {"displayName": "John Doe"},
                },
                {
                    "id": "10002",
                    "body": "Second comment",
                    "created": "2024-01-02T10:00:00.000+0000",
                    "author": {"displayName": "Jane Smith"},
                },
                {
                    "id": "10003",
                    "body": "Third comment",
                    "created": "2024-01-03T10:00:00.000+0000",
                    "author": {"displayName": "Bob Johnson"},
                },
            ]
        }

        # Call the method with limit=2
        result = comments_mixin.get_issue_comments("TEST-123", limit=2)

        # Verify
        comments_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
        assert len(result) == 2  # Only 2 comments should be returned
        assert result[0]["id"] == "10001"
        assert result[1]["id"] == "10002"
        # Third comment shouldn't be included due to limit

    def test_get_issue_comments_with_missing_fields(self, comments_mixin):
        """Test get_issue_comments with missing fields in the response."""
        # Setup mock response with missing fields
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    # Missing body field
                    "created": "2024-01-01T10:00:00.000+0000",
                    # Missing author field
                },
                {
                    # Missing id field
                    "body": "Second comment",
                    # Missing created field
                    "author": {},  # Empty author object
                },
                {
                    "id": "10003",
                    "body": "Third comment",
                    "created": "2024-01-03T10:00:00.000+0000",
                    "author": {"name": "user123"},  # Using name instead of displayName
                },
            ]
        }

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        assert len(result) == 3
        assert result[0]["id"] == "10001"
        assert result[0]["body"] == ""  # Should default to empty string
        assert result[0]["author"] == "Unknown"  # Should default to Unknown

        assert (
            "id" not in result[1] or not result[1]["id"]
        )  # Should be missing or empty
        assert result[1]["author"] == "Unknown"  # Should default to Unknown

        assert (
            result[2]["author"] == "Unknown"
        )  # Should use Unknown when only name is available

    def test_get_issue_comments_with_empty_response(self, comments_mixin):
        """Test get_issue_comments with an empty response."""
        # Setup mock response with no comments
        comments_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        assert len(result) == 0  # Should return an empty list

    def test_get_issue_comments_with_error(self, comments_mixin):
        """Test get_issue_comments with an error response."""
        # Setup mock to raise exception
        comments_mixin.jira.issue_get_comments.side_effect = Exception("API Error")

        # Verify it raises the wrapped exception
        with pytest.raises(Exception, match="Error getting comments"):
            comments_mixin.get_issue_comments("TEST-123")

    def test_add_comment_basic(self, comments_mixin):
        """Test add_comment with basic data."""
        # Setup mock response
        comments_mixin.jira.issue_add_comment.return_value = {
            "id": "10001",
            "body": "This is a comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }

        # Call the method
        result = comments_mixin.add_comment("TEST-123", "Test comment")

        # Verify
        comments_mixin.preprocessor.markdown_to_jira.assert_called_once_with(
            "Test comment"
        )
        comments_mixin.jira.issue_add_comment.assert_called_once_with(
            "TEST-123", "*This* is _Jira_ formatted"
        )
        assert result["id"] == "10001"
        assert result["body"] == "This is a comment"
        assert result["created"] == "2024-01-01"  # Parsed date
        assert result["author"] == "John Doe"

    def test_add_comment_with_markdown_conversion(self, comments_mixin):
        """Test add_comment with markdown conversion."""
        # Setup mock response
        comments_mixin.jira.issue_add_comment.return_value = {
            "id": "10001",
            "body": "*This* is _Jira_ formatted",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }

        # Create a complex markdown comment
        markdown_comment = """
        # Heading 1

        This is a paragraph with **bold** and *italic* text.

        - List item 1
        - List item 2

        ```python
        def hello():
            print("Hello world")
        ```
        """

        # Call the method
        result = comments_mixin.add_comment("TEST-123", markdown_comment)

        # Verify
        comments_mixin.preprocessor.markdown_to_jira.assert_called_once_with(
            markdown_comment
        )
        comments_mixin.jira.issue_add_comment.assert_called_once_with(
            "TEST-123", "*This* is _Jira_ formatted"
        )
        assert result["body"] == "*This* is _Jira_ formatted"

    def test_add_comment_with_empty_comment(self, comments_mixin):
        """Test add_comment with an empty comment."""
        # Setup mock response
        comments_mixin.jira.issue_add_comment.return_value = {
            "id": "10001",
            "body": "",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }

        # Call the method with empty comment
        result = comments_mixin.add_comment("TEST-123", "")

        # Verify - for empty comments, markdown_to_jira should NOT be called as per implementation
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        comments_mixin.jira.issue_add_comment.assert_called_once_with("TEST-123", "")
        assert result["body"] == ""

    def test_add_comment_with_error(self, comments_mixin):
        """Test add_comment with an error response."""
        # Setup mock to raise exception
        comments_mixin.jira.issue_add_comment.side_effect = Exception("API Error")

        # Verify it raises the wrapped exception
        with pytest.raises(Exception, match="Error adding comment"):
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
        # Call the method with empty text
        result = comments_mixin._markdown_to_jira("")

        # Verify
        assert result == ""
        # The preprocessor should not be called with empty text
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()

    def test_parse_date(self, comments_mixin):
        """Test the actual implementation of _parse_date."""
        # Test ISO format
        result = comments_mixin._parse_date("2024-01-01T10:00:00.000+0000")
        assert result == "2024-01-01", f"Expected '2024-01-01' but got '{result}'"

        # Test invalid format
        result = comments_mixin._parse_date("invalid date")
        assert result == "invalid date", f"Expected 'invalid date' but got '{result}'"

        # Test None value
        result = comments_mixin._parse_date(None)
        assert result == "", f"Expected empty string but got '{result}'"
