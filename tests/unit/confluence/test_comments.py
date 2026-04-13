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


# ---------------------------------------------------------------------------
# Inline comment tests
# ---------------------------------------------------------------------------

_INLINE_COMMENT_V2_RESPONSE = {
    "id": "ic-001",
    "status": "current",
    "title": "",
    "body": {"storage": {"value": "<p>Looks good</p>", "representation": "storage"}},
    "version": {"number": 1},
    "author": {"displayName": "Alice"},
    "inlineCommentProperties": {
        "textSelection": "power analysis",
        "textSelectionMatchCount": 1,
        "textSelectionMatchIndex": 0,
    },
    "_links": {},
}


class TestAddInlineComment:
    """Tests for CommentsMixin.add_inline_comment."""

    def test_raises_for_server_dc(self, comments_mixin):
        """add_inline_comment raises ValueError on non-Cloud instances."""
        from unittest.mock import MagicMock

        comments_mixin.config = MagicMock()
        comments_mixin.config.is_cloud = False

        with pytest.raises(ValueError, match="only supported on Confluence Cloud"):
            comments_mixin.add_inline_comment(
                page_id="123",
                content="Note",
                text_selection="some text",
            )

    def test_creates_inline_comment_cloud(self, comments_mixin):
        """add_inline_comment calls the v2 adapter on Cloud instances."""
        from unittest.mock import MagicMock, patch

        # Confirm default fixture is Cloud
        assert comments_mixin.config.is_cloud is True

        # Patch ConfluenceV2Adapter so we don't need real HTTP
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.create_inline_comment.return_value = (
                _build_v1_inline_response()
            )
            mock_adapter_cls.return_value = mock_adapter

            # markdown_to_confluence_storage is called because content lacks "<"
            comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
                "<p>Looks good</p>"
            )
            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>Looks good</p>",
                "Looks good",
            )

            result = comments_mixin.add_inline_comment(
                page_id="123",
                content="Looks good",
                text_selection="power analysis",
            )

        mock_adapter.create_inline_comment.assert_called_once_with(
            page_id="123",
            body="<p>Looks good</p>",
            text_selection="power analysis",
            text_selection_match_index=0,
        )
        assert result is not None
        assert result.id == "ic-001"

    def test_markdown_converted_to_storage(self, comments_mixin):
        """add_inline_comment converts markdown body to storage format."""
        from unittest.mock import MagicMock, patch

        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.create_inline_comment.return_value = (
                _build_v1_inline_response()
            )
            mock_adapter_cls.return_value = mock_adapter

            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>md converted</p>",
                "md converted",
            )

            comments_mixin.add_inline_comment(
                page_id="123",
                content="plain markdown text",
                text_selection="some text",
            )

        # preprocessor.markdown_to_confluence_storage should have been called
        comments_mixin.preprocessor.markdown_to_confluence_storage.assert_called_once_with(
            "plain markdown text"
        )

    def test_storage_format_body_not_reconverted(self, comments_mixin):
        """add_inline_comment skips conversion when body is already storage XML."""
        from unittest.mock import MagicMock, patch

        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.create_inline_comment.return_value = (
                _build_v1_inline_response()
            )
            mock_adapter_cls.return_value = mock_adapter

            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>Already storage</p>",
                "Already storage",
            )

            comments_mixin.add_inline_comment(
                page_id="123",
                content="<p>Already storage</p>",
                text_selection="some text",
            )

        comments_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

    def test_match_index_forwarded(self, comments_mixin):
        """add_inline_comment passes match_index to the adapter."""
        from unittest.mock import MagicMock, patch

        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.create_inline_comment.return_value = (
                _build_v1_inline_response()
            )
            mock_adapter_cls.return_value = mock_adapter

            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>ok</p>",
                "ok",
            )

            comments_mixin.add_inline_comment(
                page_id="123",
                content="<p>ok</p>",
                text_selection="repeated text",
                text_selection_match_index=2,
            )

        call_kwargs = mock_adapter.create_inline_comment.call_args[1]
        assert call_kwargs["text_selection_match_index"] == 2

    def test_api_error_propagates(self, comments_mixin):
        """add_inline_comment propagates ValueError from the v2 adapter."""
        from unittest.mock import MagicMock, patch

        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.create_inline_comment.side_effect = ValueError(
                "text not found on page"
            )
            mock_adapter_cls.return_value = mock_adapter

            comments_mixin.preprocessor.process_html_content.return_value = (
                "<p>ok</p>",
                "ok",
            )

            with pytest.raises(ValueError, match="text not found on page"):
                comments_mixin.add_inline_comment(
                    page_id="123",
                    content="<p>ok</p>",
                    text_selection="nonexistent text",
                )


# ---------------------------------------------------------------------------
# V2Adapter inline-comment unit tests
# ---------------------------------------------------------------------------


class TestV2AdapterCreateInlineComment:
    """Tests for ConfluenceV2Adapter.create_inline_comment."""

    @pytest.fixture
    def adapter(self):
        from unittest.mock import MagicMock

        from mcp_atlassian.confluence.v2_adapter import ConfluenceV2Adapter

        mock_session = MagicMock()
        return ConfluenceV2Adapter(
            session=mock_session, base_url="https://test.atlassian.net/wiki"
        )

    def test_posts_to_correct_endpoint(self, adapter):
        """create_inline_comment POSTs to /api/v2/inline-comments."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _INLINE_COMMENT_V2_RESPONSE
        mock_resp.raise_for_status.return_value = None
        adapter.session.post.return_value = mock_resp

        adapter.create_inline_comment(
            page_id="123",
            body="<p>ok</p>",
            text_selection="power analysis",
        )

        call_args = adapter.session.post.call_args
        assert call_args[0][0].endswith("/api/v2/inline-comments")

    def test_payload_structure(self, adapter):
        """create_inline_comment sends correct payload."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _INLINE_COMMENT_V2_RESPONSE
        mock_resp.raise_for_status.return_value = None
        adapter.session.post.return_value = mock_resp

        adapter.create_inline_comment(
            page_id="456",
            body="<p>comment</p>",
            text_selection="important text",
            text_selection_match_index=1,
        )

        payload = adapter.session.post.call_args[1]["json"]
        assert payload["pageId"] == "456"
        assert payload["body"]["value"] == "<p>comment</p>"
        assert payload["inlineCommentProperties"]["textSelection"] == "important text"
        assert payload["inlineCommentProperties"]["textSelectionMatchIndex"] == 1
        # matchCount must be at least matchIndex + 1
        assert (
            payload["inlineCommentProperties"]["textSelectionMatchCount"]
            >= payload["inlineCommentProperties"]["textSelectionMatchIndex"] + 1
        )

    def test_match_count_ge_match_index_plus_one(self, adapter):
        """textSelectionMatchCount is always >= textSelectionMatchIndex + 1."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _INLINE_COMMENT_V2_RESPONSE
        mock_resp.raise_for_status.return_value = None
        adapter.session.post.return_value = mock_resp

        for idx in range(5):
            adapter.create_inline_comment(
                page_id="1",
                body="<p>x</p>",
                text_selection="text",
                text_selection_match_index=idx,
            )
            payload = adapter.session.post.call_args[1]["json"]
            props = payload["inlineCommentProperties"]
            assert props["textSelectionMatchCount"] >= idx + 1

    def test_converts_v2_response_to_v1_format(self, adapter):
        """create_inline_comment returns v1-compatible dict."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _INLINE_COMMENT_V2_RESPONSE
        mock_resp.raise_for_status.return_value = None
        adapter.session.post.return_value = mock_resp

        result = adapter.create_inline_comment(
            page_id="123",
            body="<p>Looks good</p>",
            text_selection="power analysis",
        )

        assert result["id"] == "ic-001"
        assert result["extensions"]["location"] == "inline"
        assert "body" in result
        assert result["body"]["view"]["value"] == "<p>Looks good</p>"


def _build_v1_inline_response() -> dict:
    """Build a v1-format inline comment response for use in mocks."""
    return {
        "id": "ic-001",
        "type": "comment",
        "status": "current",
        "title": "",
        "body": {
            "view": {
                "value": "<p>Looks good</p>",
                "representation": "view",
            },
        },
        "version": {"number": 1},
        "_links": {},
        "extensions": {"location": "inline"},
    }
