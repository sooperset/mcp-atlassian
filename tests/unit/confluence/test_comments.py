"""Unit tests for the CommentsMixin class."""

from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.confluence.comments import CommentsMixin
from mcp_atlassian.document_types import Document


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
        """Test that get_page_comments returns comments for a page."""
        # Arrange
        page_id = "987654321"
        comments_mixin.confluence.get_page_by_id.return_value = {
            "space": {"key": "SPACE", "name": "Test Space"},
        }

        # Act
        result = comments_mixin.get_page_comments(page_id, return_markdown=True)

        # Assert
        comments_mixin.confluence.get_page_by_id.assert_called_once_with(
            page_id=page_id, expand="space"
        )
        comments_mixin.confluence.get_page_comments.assert_called_once_with(
            content_id=page_id, expand="body.view.value,version", depth="all"
        )

        # Verify result format
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(doc, Document) for doc in result)

        # Verify document content and metadata
        doc = result[0]
        assert doc.page_content == "Processed Markdown"  # from mock_preprocessor
        assert doc.metadata["page_id"] == page_id
        assert doc.metadata["space_key"] == "SPACE"
        assert doc.metadata["space_name"] == "Test Space"
        assert "comment_id" in doc.metadata
        assert "type" in doc.metadata
        assert doc.metadata["type"] == "comment"

    def test_get_page_comments_with_html(self, comments_mixin):
        """Test getting comments with HTML content instead of markdown."""
        # Act
        result = comments_mixin.get_page_comments("987654321", return_markdown=False)

        # Assert
        assert len(result) > 0
        assert (
            result[0].page_content == "<p>Processed HTML</p>"
        )  # from mock_preprocessor

    def test_get_page_comments_api_error(self, comments_mixin):
        """Test handling of API errors."""
        # Arrange
        comments_mixin.confluence.get_page_by_id.side_effect = (
            requests.RequestException("API Error")
        )

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert result == []

    def test_get_page_comments_key_error(self, comments_mixin):
        """Test handling of KeyError when processing results."""
        # Arrange - Return incomplete page data
        comments_mixin.confluence.get_page_by_id.return_value = {"id": "123"}
        # This is the important part - this needs to trigger a KeyError in the result handling
        comments_mixin.confluence.get_page_comments.return_value = {
            "missing_results_key": []
        }

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert result == []

    def test_get_page_comments_value_error(self, comments_mixin):
        """Test handling of ValueError when processing results."""
        # Arrange
        comments_mixin.preprocessor.process_html_content.side_effect = ValueError(
            "Processing error"
        )

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert result == []

    def test_get_page_comments_with_empty_results(self, comments_mixin):
        """Test handling a page with no comments."""
        # Arrange
        comments_mixin.confluence.get_page_comments.return_value = {"results": []}

        # Act
        result = comments_mixin.get_page_comments("987654321")

        # Assert
        assert result == []
