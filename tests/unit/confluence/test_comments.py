"""Unit tests for the CommentsMixin class."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_atlassian.confluence.comments import CommentsMixin
from mcp_atlassian.models.confluence import ConfluenceComment
from tests.fixtures.confluence_mocks import (
    MOCK_COMMENT_REPLY_V1_RESPONSE,
    MOCK_COMMENT_REPLY_V2_RESPONSE,
)


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


class TestReplyToComment:
    """Tests for reply_to_comment method."""

    @pytest.fixture
    def comments_mixin(self, confluence_client):
        """Create a CommentsMixin instance for testing."""
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = CommentsMixin()
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_reply_to_comment_v1_success(self, comments_mixin):
        """T1: reply_to_comment v1 success - parent_comment_id set."""
        # Mock the POST call for v1 API
        comments_mixin.confluence.post.return_value = MOCK_COMMENT_REPLY_V1_RESPONSE
        # Mock preprocessor
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>This is a reply</p>"
        )
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>This is a reply</p>",
            "This is a reply",
        )

        result = comments_mixin.reply_to_comment("456789123", "This is a reply")

        assert result is not None
        assert result.parent_comment_id == "456789123"
        comments_mixin.confluence.post.assert_called_once()

    def test_reply_to_comment_v2_oauth_success(self, comments_mixin):
        """T2: reply_to_comment v2/OAuth routes through v2_adapter."""
        # Configure as OAuth Cloud
        comments_mixin.config.auth_type = "oauth"
        comments_mixin.config.url = "https://test.atlassian.net/wiki"

        # Mock v2 adapter
        mock_adapter = MagicMock()
        mock_adapter.create_footer_comment.return_value = {
            "id": "222333444",
            "type": "comment",
            "status": "current",
            "title": "Re: Comment",
            "parentCommentId": "456789123",
            "body": {
                "view": {
                    "value": "<p>This is a v2 reply</p>",
                    "representation": "view",
                },
            },
            "version": {"number": 1},
            "_links": {},
        }

        with patch.object(
            type(comments_mixin),
            "_v2_adapter",
            new_callable=lambda: property(lambda self: mock_adapter),
        ):
            comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
                "<p>This is a v2 reply</p>"
            )
            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>This is a v2 reply</p>",
                "This is a v2 reply",
            )

            result = comments_mixin.reply_to_comment("456789123", "This is a v2 reply")

        assert result is not None
        mock_adapter.create_footer_comment.assert_called_once_with(
            parent_comment_id="456789123",
            body="<p>This is a v2 reply</p>",
        )

    def test_reply_with_html_content(self, comments_mixin):
        """T3: Reply with HTML content skips markdown conversion."""
        comments_mixin.confluence.post.return_value = MOCK_COMMENT_REPLY_V1_RESPONSE
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>HTML reply</p>",
            "HTML reply",
        )

        result = comments_mixin.reply_to_comment("456789123", "<p>HTML reply</p>")

        assert result is not None
        comments_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

    def test_reply_network_error(self, comments_mixin):
        """T4: Network error returns None."""
        comments_mixin.confluence.post.side_effect = requests.RequestException(
            "Connection error"
        )
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )

        result = comments_mixin.reply_to_comment("456789123", "Test")

        assert result is None

    def test_reply_empty_response(self, comments_mixin):
        """T5: Empty API response returns None."""
        comments_mixin.confluence.post.return_value = None
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )

        result = comments_mixin.reply_to_comment("456789123", "Test")

        assert result is None


class TestAddCommentV2Routing:
    """Tests for add_comment v2 routing for OAuth Cloud."""

    @pytest.fixture
    def comments_mixin(self, confluence_client):
        """Create a CommentsMixin instance for testing."""
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = CommentsMixin()
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_add_comment_v2_routing_for_oauth_cloud(self, comments_mixin):
        """T10: add_comment routes through v2 adapter for OAuth Cloud."""
        comments_mixin.config.auth_type = "oauth"
        comments_mixin.config.url = "https://test.atlassian.net/wiki"

        mock_adapter = MagicMock()
        mock_adapter.create_footer_comment.return_value = {
            "id": "333444555",
            "type": "comment",
            "status": "current",
            "title": "New Comment",
            "body": {
                "view": {
                    "value": "<p>Comment via v2</p>",
                    "representation": "view",
                },
            },
            "version": {"number": 1},
            "_links": {},
        }

        with patch.object(
            type(comments_mixin),
            "_v2_adapter",
            new_callable=lambda: property(lambda self: mock_adapter),
        ):
            comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
                "<p>Comment via v2</p>"
            )
            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>Comment via v2</p>",
                "Comment via v2",
            )

            result = comments_mixin.add_comment("12345", "Comment via v2")

        assert result is not None
        mock_adapter.create_footer_comment.assert_called_once_with(
            page_id="12345",
            body="<p>Comment via v2</p>",
        )
        # Verify v1 get_page_by_id was NOT called (OAuth shouldn't use v1)
        comments_mixin.confluence.get_page_by_id.assert_not_called()


class TestConfluenceCommentModel:
    """Tests for ConfluenceComment model parent_comment_id and location fields."""

    def test_parent_from_v1_container_type_comment(self):
        """T6: Extract parent_comment_id from v1 container with type='comment'."""
        comment = ConfluenceComment.from_api_response(MOCK_COMMENT_REPLY_V1_RESPONSE)
        assert comment.parent_comment_id == "456789123"

    def test_no_parent_from_v1_container_type_page(self):
        """T7: parent_comment_id is None when container type is 'page'."""
        data = {
            "id": "111222333",
            "type": "comment",
            "container": {
                "id": "12345",
                "type": "page",
                "title": "Some Page",
            },
            "body": {"view": {"value": "<p>Top-level comment</p>"}},
        }
        comment = ConfluenceComment.from_api_response(data)
        assert comment.parent_comment_id is None

    def test_parent_from_v2_parent_comment_id(self):
        """T8: Extract parent_comment_id from v2 parentCommentId field."""
        comment = ConfluenceComment.from_api_response(MOCK_COMMENT_REPLY_V2_RESPONSE)
        assert comment.parent_comment_id == "456789123"

    def test_to_simplified_dict_with_parent(self):
        """T9a: to_simplified_dict includes parent_comment_id when present."""
        comment = ConfluenceComment.from_api_response(MOCK_COMMENT_REPLY_V1_RESPONSE)
        result = comment.to_simplified_dict()
        assert result["parent_comment_id"] == "456789123"

    def test_to_simplified_dict_without_parent(self):
        """T9b: to_simplified_dict omits parent_comment_id when absent."""
        data = {
            "id": "111222333",
            "type": "comment",
            "body": {"view": {"value": "<p>Comment</p>"}},
        }
        comment = ConfluenceComment.from_api_response(data)
        result = comment.to_simplified_dict()
        assert "parent_comment_id" not in result

    def test_location_inline_from_extensions(self):
        """T13: Extract location='inline' from extensions.location."""
        data = {
            "id": "456789123",
            "type": "comment",
            "body": {"view": {"value": "<p>Inline comment</p>"}},
            "extensions": {"location": "inline"},
        }
        comment = ConfluenceComment.from_api_response(data)
        assert comment.location == "inline"

    def test_location_footer_from_extensions(self):
        """T14: Extract location='footer' from extensions.location."""
        comment = ConfluenceComment.from_api_response(MOCK_COMMENT_REPLY_V1_RESPONSE)
        assert comment.location == "footer"

    def test_location_none_when_no_extensions(self):
        """T15: location is None when no extensions present."""
        data = {
            "id": "111222333",
            "type": "comment",
            "body": {"view": {"value": "<p>Comment</p>"}},
        }
        comment = ConfluenceComment.from_api_response(data)
        assert comment.location is None

    def test_to_simplified_dict_with_location(self):
        """to_simplified_dict includes location when present."""
        comment = ConfluenceComment.from_api_response(MOCK_COMMENT_REPLY_V1_RESPONSE)
        result = comment.to_simplified_dict()
        assert result["location"] == "footer"

    def test_to_simplified_dict_without_location(self):
        """to_simplified_dict omits location when absent."""
        data = {
            "id": "111222333",
            "type": "comment",
            "body": {"view": {"value": "<p>Comment</p>"}},
        }
        comment = ConfluenceComment.from_api_response(data)
        result = comment.to_simplified_dict()
        assert "location" not in result
