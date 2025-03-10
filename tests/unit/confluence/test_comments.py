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
