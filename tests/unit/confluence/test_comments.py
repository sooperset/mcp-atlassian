"""Unit tests for the CommentsMixin class."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_atlassian.confluence.comments import CommentsMixin
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.models.confluence import ConfluenceComment
from tests.fixtures.confluence_mocks import (
    MOCK_COMMENT_REPLY_V1_RESPONSE,
    MOCK_COMMENT_REPLY_V2_RESPONSE,
    MOCK_INLINE_COMMENT_V1_RESPONSE,
    MOCK_INLINE_COMMENT_V2_RESPONSE,
)


@pytest.fixture
def comments_mixin(confluence_client):
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


@pytest.fixture
def comments_mixin_dc():
    """Create a CommentsMixin instance for Server/DC testing (is_cloud=False).

    Inline comments on Server/DC use the v1 API path.
    """
    with patch(
        "mcp_atlassian.confluence.comments.ConfluenceClient.__init__"
    ) as mock_init:
        mock_init.return_value = None
        mixin = CommentsMixin()
        mixin.config = ConfluenceConfig(
            url="https://confluence.example.com",
            auth_type="basic",
            username="test_user",
            api_token="test_token",
        )
        mixin.confluence = MagicMock()
        mixin.confluence._session = MagicMock()
        mock_preprocessor = MagicMock()
        mock_preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )
        mock_preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Processed</p>"
        )
        mixin.preprocessor = mock_preprocessor
        return mixin


class TestCommentsMixin:
    """Tests for the CommentsMixin class."""

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
            "extensions": {"location": "footer"},
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
            "extensions": {"location": "footer"},
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


class TestGetInlineComments:
    """Tests for get_inline_comments method."""

    def test_get_inline_comments_v1_success(self, comments_mixin_dc):
        """get_inline_comments v1 (Server/DC) filters by location=inline."""
        page_id = "12345"
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.confluence.get_page_comments.return_value = {
            "results": [
                MOCK_INLINE_COMMENT_V1_RESPONSE,
                # footer comment that should be filtered out
                {
                    "id": "999",
                    "body": {"view": {"value": "<p>footer</p>"}},
                    "extensions": {"location": "footer"},
                },
            ]
        }
        comments_mixin_dc.preprocessor.process_html_content.return_value = (
            "<p>This is an inline comment</p>",
            "This is an inline comment",
        )

        result = comments_mixin_dc.get_inline_comments(page_id)

        assert len(result) == 1
        assert result[0].location == "inline"
        assert result[0].id == "333444555"
        # Verify expanded fields were requested
        comments_mixin_dc.confluence.get_page_comments.assert_called_once_with(
            content_id=page_id,
            expand="body.view.value,version,extensions.inlineProperties",
            depth="all",
        )

    def test_get_inline_comments_v2_cloud_success(self, comments_mixin):
        """get_inline_comments uses v2 API on Cloud (any auth type)."""
        mock_adapter = MagicMock()
        mock_adapter.get_inline_comments.return_value = [
            {
                "id": "444555666",
                "type": "comment",
                "status": "open",
                "body": {
                    "view": {"value": "<p>v2 inline</p>", "representation": "view"}
                },
                "extensions": {"location": "inline"},
                "version": {"number": 1},
                "_links": {},
            }
        ]
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>v2 inline</p>",
            "v2 inline",
        )

        with patch.object(
            type(comments_mixin),
            "_inline_v2_adapter",
            new_callable=lambda: property(lambda self: mock_adapter),
        ):
            result = comments_mixin.get_inline_comments("12345")

        assert len(result) == 1
        mock_adapter.get_inline_comments.assert_called_once_with("12345")
        # v1 API should not be called
        comments_mixin.confluence.get_page_comments.assert_not_called()

    def test_get_inline_comments_empty(self, comments_mixin_dc):
        """get_inline_comments returns empty list if no inline comments (Server/DC)."""
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.confluence.get_page_comments.return_value = {
            "results": [
                {
                    "id": "999",
                    "body": {"view": {"value": "<p>footer</p>"}},
                    "extensions": {"location": "footer"},
                }
            ]
        }

        result = comments_mixin_dc.get_inline_comments("12345")

        assert result == []

    def test_get_inline_comments_network_error(self, comments_mixin_dc):
        """get_inline_comments returns empty list on network error (Server/DC)."""
        comments_mixin_dc.confluence.get_page_comments.side_effect = (
            requests.RequestException("Network error")
        )

        result = comments_mixin_dc.get_inline_comments("12345")

        assert result == []

    def test_get_inline_comments_html_format(self, comments_mixin_dc):
        """get_inline_comments returns HTML body when markdown=False (Server/DC)."""
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.confluence.get_page_comments.return_value = {
            "results": [MOCK_INLINE_COMMENT_V1_RESPONSE]
        }
        comments_mixin_dc.preprocessor.process_html_content.return_value = (
            "<p>HTML body</p>",
            "Markdown body",
        )

        result = comments_mixin_dc.get_inline_comments("12345", return_markdown=False)

        assert result[0].body == "<p>HTML body</p>"


class TestAddInlineComment:
    """Tests for add_inline_comment method."""

    def test_add_inline_comment_v1_success(self, comments_mixin_dc):
        """add_inline_comment v1 (Server/DC) posts with inline location."""
        page_id = "12345"
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Inline comment</p>"
        )
        comments_mixin_dc.confluence.post.return_value = MOCK_INLINE_COMMENT_V1_RESPONSE
        comments_mixin_dc.preprocessor.process_html_content.return_value = (
            "<p>Inline comment</p>",
            "Inline comment",
        )

        result = comments_mixin_dc.add_inline_comment(
            page_id, "Inline comment", "some text to anchor"
        )

        assert result is not None
        assert result.location == "inline"
        call_args = comments_mixin_dc.confluence.post.call_args
        assert call_args[0][0] == "rest/api/content/"
        data = call_args[1]["data"]
        assert data["extensions"]["location"] == "inline"
        inline_props = data["extensions"]["inlineProperties"]
        assert inline_props["originalSelection"] == "some text to anchor"
        # Server/DC requires four additional fields that the frontend editor
        # normally supplies. Confluence rejects the POST with HTTP 400 if any
        # of them is missing; see add_inline_comment() for the discovered
        # field formats.
        assert inline_props["numMatches"] == 1
        assert inline_props["matchIndex"] == 0
        assert isinstance(inline_props["lastFetchTime"], str)
        assert inline_props["lastFetchTime"].isdigit()
        assert inline_props["serializedHighlights"] == ('[["some text to anchor"]]')

    def test_add_inline_comment_v1_forwards_match_count_and_index(
        self, comments_mixin_dc
    ):
        """v1 path forwards match_count/index to numMatches/matchIndex."""
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>x</p>"
        )
        comments_mixin_dc.confluence.post.return_value = MOCK_INLINE_COMMENT_V1_RESPONSE
        comments_mixin_dc.preprocessor.process_html_content.return_value = (
            "<p>x</p>",
            "x",
        )

        comments_mixin_dc.add_inline_comment(
            "12345",
            "x",
            "repeated text",
            text_selection_match_count=5,
            text_selection_match_index=3,
        )

        inline_props = comments_mixin_dc.confluence.post.call_args[1]["data"][
            "extensions"
        ]["inlineProperties"]
        assert inline_props["numMatches"] == 5
        assert inline_props["matchIndex"] == 3

    def test_add_inline_comment_v2_cloud_success(self, comments_mixin):
        """add_inline_comment uses v2 API on Cloud (any auth type)."""

        v2_converted = {
            "id": "444555666",
            "type": "comment",
            "status": "open",
            "body": {"view": {"value": "<p>v2 inline</p>", "representation": "view"}},
            "extensions": {"location": "inline"},
            "version": {"number": 1},
            "_links": {},
            "inlineCommentProperties": {
                "textSelection": "some text to anchor",
                "textSelectionMatchCount": 1,
                "textSelectionMatchIndex": 0,
            },
        }

        mock_adapter = MagicMock()
        mock_adapter.create_inline_comment.return_value = v2_converted
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>v2 inline</p>"
        )
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>v2 inline</p>",
            "v2 inline",
        )

        with patch.object(
            type(comments_mixin),
            "_inline_v2_adapter",
            new_callable=lambda: property(lambda self: mock_adapter),
        ):
            result = comments_mixin.add_inline_comment(
                "12345",
                "v2 inline",
                "some text to anchor",
                text_selection_match_count=2,
                text_selection_match_index=1,
            )

        assert result is not None
        mock_adapter.create_inline_comment.assert_called_once_with(
            page_id="12345",
            body="<p>v2 inline</p>",
            text_selection="some text to anchor",
            text_selection_match_count=2,
            text_selection_match_index=1,
        )
        # v1 API should not be called
        comments_mixin.confluence.post.assert_not_called()

    def test_add_inline_comment_with_html_content(self, comments_mixin_dc):
        """add_inline_comment skips markdown conversion for HTML content (Server/DC)."""
        html_content = "<p>Already <strong>HTML</strong></p>"
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.confluence.post.return_value = MOCK_INLINE_COMMENT_V1_RESPONSE
        comments_mixin_dc.preprocessor.process_html_content.return_value = (
            html_content,
            "Already **HTML**",
        )

        result = comments_mixin_dc.add_inline_comment(
            "12345", html_content, "some text"
        )

        comments_mixin_dc.preprocessor.markdown_to_confluence_storage.assert_not_called()
        assert result is not None

    def test_add_inline_comment_empty_response(self, comments_mixin_dc):
        """add_inline_comment returns None on empty API response (Server/DC)."""
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )
        comments_mixin_dc.confluence.post.return_value = None

        result = comments_mixin_dc.add_inline_comment("12345", "Test", "anchor text")

        assert result is None

    def test_add_inline_comment_network_error(self, comments_mixin_dc):
        """add_inline_comment returns None on network error (Server/DC)."""
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        comments_mixin_dc.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )
        comments_mixin_dc.confluence.post.side_effect = requests.RequestException(
            "Network error"
        )

        result = comments_mixin_dc.add_inline_comment("12345", "Test", "anchor text")

        assert result is None


class TestInlineCommentModel:
    """Tests for ConfluenceComment model with inline comment data."""

    def test_inline_comment_from_v1_response(self):
        """ConfluenceComment correctly parses v1 inline comment response."""
        comment = ConfluenceComment.from_api_response(MOCK_INLINE_COMMENT_V1_RESPONSE)
        assert comment.id == "333444555"
        assert comment.location == "inline"
        assert comment.body == "<p>This is an inline comment</p>"

    def test_inline_comment_from_v2_response_converted(self):
        """ConfluenceComment parses v2 inline comment after v1 conversion."""
        # Simulate what _convert_v2_inline_comment_to_v1_format outputs
        v1_converted = {
            "id": "444555666",
            "type": "comment",
            "status": "open",
            "body": {
                "view": {
                    "value": "<p>This is a v2 inline comment</p>",
                    "representation": "view",
                }
            },
            "version": MOCK_INLINE_COMMENT_V2_RESPONSE["version"],
            "author": MOCK_INLINE_COMMENT_V2_RESPONSE["author"],
            "_links": MOCK_INLINE_COMMENT_V2_RESPONSE["_links"],
            "extensions": {"location": "inline"},
            "inlineCommentProperties": {
                "textSelection": "some text to anchor",
                "textSelectionMatchCount": 1,
                "textSelectionMatchIndex": 0,
            },
        }
        comment = ConfluenceComment.from_api_response(v1_converted)
        assert comment.id == "444555666"
        assert comment.location == "inline"
        assert comment.body == "<p>This is a v2 inline comment</p>"
        assert comment.author is not None
        assert comment.author.display_name == "Test User"
