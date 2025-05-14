"""Unit tests for the CommentsMixin class."""

from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.confluence.comments import CommentsMixin


class TestCommentsMixin:
    """Tests for the CommentsMixin class."""

    @pytest.fixture
    def comments_mixin(self, confluence_client):
        """Create a CommentsMixin instance for testing."""
        # CommentsMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = CommentsMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_get_page_comments_success(self, comments_mixin):
        """Test get_page_comments with success response."""
        # Setup
        page_id = "12345"
        # Configure the mock to return a successful response
        comments_mixin.confluence.get_page_comments.return_value = {
            "results": [
                {
                    "id": "12345",
                    "body": {"view": {"value": "<p>Comment content here</p>"}},
                    "version": {"number": 1},
                    "author": {"displayName": "John Doe"},
                }
            ]
        }

        # Mock preprocessor
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )

        # Call the method
        result = comments_mixin.get_page_comments(page_id)

        # Verify
        comments_mixin.confluence.get_page_comments.assert_called_once_with(
            content_id=page_id, expand="body.view.value,version", depth="all"
        )
        assert len(result) == 1
        assert result[0].body == "Processed Markdown"

    def test_get_page_comments_with_html(self, comments_mixin):
        """Test get_page_comments with HTML output instead of markdown."""
        # Setup
        page_id = "12345"
        comments_mixin.confluence.get_page_comments.return_value = {
            "results": [
                {
                    "id": "12345",
                    "body": {"view": {"value": "<p>Comment content here</p>"}},
                    "version": {"number": 1},
                    "author": {"displayName": "John Doe"},
                }
            ]
        }

        # Mock the HTML processing
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed markdown",
        )

        # Call the method
        result = comments_mixin.get_page_comments(page_id, return_markdown=False)

        # Verify result
        assert len(result) == 1
        comment = result[0]
        assert comment.body == "<p>Processed HTML</p>"

    def test_get_page_comments_api_error(self, comments_mixin):
        """Test handling of API errors."""
        # Mock the API to raise an exception
        comments_mixin.confluence.get_page_comments.side_effect = (
            requests.RequestException("API error")
        )

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0  # Empty list on error

    def test_get_page_comments_key_error(self, comments_mixin):
        """Test handling of missing keys in API response."""
        # Mock the response to be missing expected keys
        comments_mixin.confluence.get_page_comments.return_value = {"invalid": "data"}

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0  # Empty list on error

    def test_get_page_comments_value_error(self, comments_mixin):
        """Test handling of unexpected data types."""
        # Cause a value error by returning a string where a dict is expected
        comments_mixin.confluence.get_page_by_id.return_value = "invalid"

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0  # Empty list on error

    def test_get_page_comments_with_empty_results(self, comments_mixin):
        """Test handling of empty results."""
        # Mock empty results
        comments_mixin.confluence.get_page_comments.return_value = {"results": []}

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0  # Empty list with no comments

    def test_add_comment_success(self, comments_mixin):
        """Test adding a comment with success response."""
        # Setup
        page_id = "12345"
        content = "This is a test comment"

        # Mock the page retrieval
        comments_mixin.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }

        # Mock the preprocessor's conversion method
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>This is a test comment</p>"
        )

        # Configure the mock to return a successful response
        comments_mixin.confluence.add_comment.return_value = {
            "id": "98765",
            "body": {"view": {"value": "<p>This is a test comment</p>"}},
            "version": {"number": 1},
            "author": {"displayName": "Test User"},
        }

        # Mock the HTML processing
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>This is a test comment</p>",
            "This is a test comment",
        )

        # Call the method
        result = comments_mixin.add_comment(page_id, content)

        # Verify
        comments_mixin.confluence.add_comment.assert_called_once_with(
            page_id, "<p>This is a test comment</p>"
        )
        assert result is not None
        assert result.id == "98765"
        assert result.body == "This is a test comment"

    def test_add_comment_with_html_content(self, comments_mixin):
        """Test adding a comment with HTML content."""
        # Setup
        page_id = "12345"
        content = "<p>This is an <strong>HTML</strong> comment</p>"

        # Mock the page retrieval
        comments_mixin.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }

        # Configure the mock to return a successful response
        comments_mixin.confluence.add_comment.return_value = {
            "id": "98765",
            "body": {
                "view": {"value": "<p>This is an <strong>HTML</strong> comment</p>"}
            },
            "version": {"number": 1},
            "author": {"displayName": "Test User"},
        }

        # Mock the HTML processing
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>This is an <strong>HTML</strong> comment</p>",
            "This is an **HTML** comment",
        )

        # Call the method
        result = comments_mixin.add_comment(page_id, content)

        # Verify - should not call markdown conversion since content is already HTML
        comments_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()
        comments_mixin.confluence.add_comment.assert_called_once_with(page_id, content)
        assert result is not None
        assert result.body == "This is an **HTML** comment"

    def test_add_comment_api_error(self, comments_mixin):
        """Test handling of API errors when adding a comment."""
        # Setup
        page_id = "12345"
        content = "This is a test comment"

        # Mock the page retrieval
        comments_mixin.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }

        # Mock the preprocessor's conversion method
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>This is a test comment</p>"
        )

        # Mock the API to raise an exception
        comments_mixin.confluence.add_comment.side_effect = requests.RequestException(
            "API error"
        )

        # Call the method
        result = comments_mixin.add_comment(page_id, content)

        # Verify
        assert result is None

    def test_add_comment_empty_response(self, comments_mixin):
        """Test handling of empty API response when adding a comment."""
        # Setup
        page_id = "12345"
        content = "This is a test comment"

        # Mock the page retrieval
        comments_mixin.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }

        # Mock the preprocessor's conversion method
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>This is a test comment</p>"
        )

        # Configure the mock to return an empty response
        comments_mixin.confluence.add_comment.return_value = None

        # Call the method
        result = comments_mixin.add_comment(page_id, content)

        # Verify
        assert result is None
