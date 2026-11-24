"""Unit tests for the CommentsMixin class."""

import json
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest
import requests

from mcp_atlassian.confluence.comments import CommentsMixin
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.models.confluence import ConfluenceComment
from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor
from tests.fixtures.confluence_mocks import (
    MOCK_COMMENT_REPLY_V1_RESPONSE,
    MOCK_COMMENT_REPLY_V2_RESPONSE,
    MOCK_INLINE_COMMENT_V1_RESPONSE,
    MOCK_INLINE_COMMENT_V2_RESPONSE,
    MOCK_PARENT_COMMENT_V1_RESPONSE,
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
            content_id=page_id,
            expand=(
                "body.view.value,version,container,ancestors,"
                "extensions.inlineProperties,extensions.resolution"
            ),
            depth="all",
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

    def test_get_page_comments_paginates_v1_results(self, comments_mixin):
        """All v1 comment pages are returned when Confluence provides next."""
        first_comment = {
            "id": "first",
            "body": {"view": {"value": "<p>First</p>"}},
        }
        second_comment = {
            "id": "second",
            "body": {"view": {"value": "<p>Second</p>"}},
        }
        comments_mixin.confluence.get_page_comments.side_effect = [
            {
                "results": [first_comment],
                "start": 0,
                "limit": 1,
                "size": 1,
                "_links": {"next": "/rest/api/content/12345/child/comment?start=1"},
            },
            {
                "results": [second_comment],
                "start": 1,
                "limit": 1,
                "size": 1,
                "_links": {},
            },
        ]

        result = comments_mixin.get_page_comments("12345")

        assert [comment.id for comment in result] == ["first", "second"]
        assert comments_mixin.confluence.get_page_comments.call_count == 2
        second_call = comments_mixin.confluence.get_page_comments.call_args_list[1]
        assert second_call.kwargs["start"] == 1
        assert second_call.kwargs["limit"] == 1

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
        """Test adding a comment with storage-format content."""
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
        result = comments_mixin.add_comment(page_id, content, content_format="storage")

        # Verify - storage format is sent as is
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

    def test_reply_to_comment_v1_cloud_basic_success(self, comments_mixin):
        """V1 Cloud Basic replies use the parent page as the container."""
        assert comments_mixin.config.is_cloud is True
        comments_mixin.confluence.get_page_by_id.side_effect = [
            MOCK_PARENT_COMMENT_V1_RESPONSE,
            {"id": "987654321", "space": {"key": "TEST"}},
        ]
        comments_mixin.confluence.post.return_value = MOCK_COMMENT_REPLY_V1_RESPONSE
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
        assert comments_mixin.confluence.get_page_by_id.call_args_list == [
            call(page_id="456789123", expand="container,ancestors"),
            call(page_id="987654321", expand="space"),
        ]
        comments_mixin.confluence.post.assert_called_once_with(
            "rest/api/content/",
            data={
                "type": "comment",
                "container": {"id": "987654321", "type": "page"},
                "ancestors": [{"id": "456789123"}],
                "body": {
                    "storage": {
                        "value": "<p>This is a reply</p>",
                        "representation": "storage",
                    },
                },
            },
        )

    def test_reply_to_nested_comment_uses_page_ancestor(self, comments_mixin):
        """Nested comment replies resolve their nearest page ancestor."""
        comments_mixin.confluence.get_page_by_id.side_effect = [
            {
                "id": "nested-comment",
                "container": {"id": "parent-comment", "type": "comment"},
                "ancestors": [
                    {"id": "987654321", "type": "page"},
                    {"id": "parent-comment", "type": "comment"},
                ],
            },
            {"id": "987654321", "space": {"key": "TEST"}},
        ]
        comments_mixin.confluence.post.return_value = MOCK_COMMENT_REPLY_V1_RESPONSE
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Nested reply</p>"
        )

        result = comments_mixin.reply_to_comment("nested-comment", "Nested reply")

        assert result is not None
        payload = comments_mixin.confluence.post.call_args.kwargs["data"]
        assert payload["container"] == {"id": "987654321", "type": "page"}
        assert payload["ancestors"] == [{"id": "nested-comment"}]

    def test_reply_to_comment_v1_server_dc_success(self, comments_mixin_dc):
        """V1 Server/DC replies use the parent page as the container."""
        comments_mixin_dc.confluence.get_page_by_id.side_effect = [
            MOCK_PARENT_COMMENT_V1_RESPONSE,
            {"id": "987654321", "space": {"key": "TEST"}},
        ]
        comments_mixin_dc.confluence.post.return_value = MOCK_COMMENT_REPLY_V1_RESPONSE

        result = comments_mixin_dc.reply_to_comment("456789123", "This is a reply")

        assert result is not None
        assert comments_mixin_dc.config.is_cloud is False
        payload = comments_mixin_dc.confluence.post.call_args.kwargs["data"]
        assert payload["container"] == {"id": "987654321", "type": "page"}
        assert payload["ancestors"] == [{"id": "456789123"}]

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
        """Reply with content_format='storage' skips markdown conversion."""
        comments_mixin.confluence.get_page_by_id.side_effect = [
            MOCK_PARENT_COMMENT_V1_RESPONSE,
            {"id": "987654321", "space": {"key": "TEST"}},
        ]
        comments_mixin.confluence.post.return_value = MOCK_COMMENT_REPLY_V1_RESPONSE
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>HTML reply</p>",
            "HTML reply",
        )

        result = comments_mixin.reply_to_comment(
            "456789123", "<p>HTML reply</p>", content_format="storage"
        )

        assert result is not None
        comments_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

    def test_reply_network_error(self, comments_mixin):
        """Network error returns None."""
        comments_mixin.confluence.get_page_by_id.side_effect = [
            MOCK_PARENT_COMMENT_V1_RESPONSE,
            {"id": "987654321", "space": {"key": "TEST"}},
        ]
        comments_mixin.confluence.post.side_effect = requests.RequestException(
            "Connection error"
        )
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )

        result = comments_mixin.reply_to_comment("456789123", "Test")

        assert result is None

    def test_reply_empty_response(self, comments_mixin):
        """Empty API response returns None."""
        comments_mixin.confluence.get_page_by_id.side_effect = [
            MOCK_PARENT_COMMENT_V1_RESPONSE,
            {"id": "987654321", "space": {"key": "TEST"}},
        ]
        comments_mixin.confluence.post.return_value = None
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )

        result = comments_mixin.reply_to_comment("456789123", "Test")

        assert result is None

    def test_reply_missing_container_page_returns_none(self, comments_mixin):
        """Missing page resolution doesn't post an empty reply stub."""
        comments_mixin.confluence.get_page_by_id.return_value = {
            "id": "456789123",
            "type": "comment",
            "container": {},
        }
        comments_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>Test</p>"
        )

        result = comments_mixin.reply_to_comment("456789123", "Test")

        assert result is None
        comments_mixin.confluence.post.assert_not_called()

    def test_reply_unsupported_parent_path_returns_none(self, comments_mixin):
        """A non-page container and ancestors don't produce a reply."""
        comments_mixin.confluence.get_page_by_id.return_value = {
            "id": "456789123",
            "type": "comment",
            "container": {"id": "blog-1", "type": "blogpost"},
            "ancestors": [{"id": "space-1", "type": "space"}],
        }

        result = comments_mixin.reply_to_comment("456789123", "Test")

        assert result is None
        comments_mixin.confluence.post.assert_not_called()

    def test_process_comment_response_falls_back_to_storage_body(self, comments_mixin):
        """Comment responses without view content use storage content."""
        comments_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )
        response = {
            "id": "111222333",
            "type": "comment",
            "body": {
                "storage": {
                    "value": "<p>Storage body</p>",
                    "representation": "storage",
                },
            },
        }

        result = comments_mixin._process_comment_response(response, "TEST")

        assert result.body == "Processed Markdown"
        comments_mixin.preprocessor.process_html_content.assert_called_once_with(
            "<p>Storage body</p>",
            space_key="TEST",
            confluence_client=comments_mixin.confluence,
        )


class TestAddCommentV2Routing:
    """Tests for add_comment v2 routing for OAuth Cloud."""

    @pytest.mark.parametrize(
        ("auth_type", "url", "uses_v2"),
        [
            ("oauth", "https://test.atlassian.net/wiki", True),
            ("pat", "https://test.atlassian.net/wiki", True),
            ("basic", "https://test.atlassian.net/wiki", False),
            ("pat", "https://confluence.example.com", False),
        ],
    )
    def test_v2_adapter_supports_only_cloud_oauth_and_pat(
        self, comments_mixin, auth_type, url, uses_v2
    ):
        """Only supported Cloud authentication routes footer comments through v2."""
        comments_mixin.config.auth_type = auth_type
        comments_mixin.config.url = url

        with patch("mcp_atlassian.confluence.comments.ConfluenceV2Adapter") as adapter:
            result = comments_mixin._v2_adapter

        if uses_v2:
            assert result is adapter.return_value
            adapter.assert_called_once()
        else:
            assert result is None
            adapter.assert_not_called()

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

    def test_inline_metadata_from_v1_extensions(self):
        """Inline anchor and resolution metadata survive v1 simplification."""
        comment = ConfluenceComment.from_api_response(MOCK_INLINE_COMMENT_V1_RESPONSE)

        assert comment.marker_ref == "marker-ref-123"
        assert comment.original_selection == "some text to anchor"
        assert comment.resolution_status == "open"
        assert comment.created == "2024-01-03T10:00:00.000Z"
        assert comment.to_simplified_dict()["marker_ref"] == "marker-ref-123"

    def test_inline_metadata_from_v2_properties(self):
        """Current Cloud v2 inline properties are normalized."""
        data = {
            "id": "456789123",
            "body": {"view": {"value": "<p>Inline comment</p>"}},
            "parentCommentId": "123456789",
            "properties": {
                "inlineMarkerRef": "cloud-marker-ref",
                "inlineOriginalSelection": "selected cloud text",
            },
            "resolutionStatus": "resolved",
        }

        result = ConfluenceComment.from_api_response(data).to_simplified_dict()

        assert result["parent_comment_id"] == "123456789"
        assert result["marker_ref"] == "cloud-marker-ref"
        assert result["original_selection"] == "selected cloud text"
        assert result["resolution_status"] == "resolved"

    def test_parent_comment_from_v1_ancestors(self):
        """Server/DC replies use the nearest comment ancestor as their parent."""
        data = {
            "id": "reply-2",
            "body": {"view": {"value": "<p>Nested reply</p>"}},
            "container": {"id": "page-1", "type": "page"},
            "ancestors": [
                {"id": "page-1", "type": "page"},
                {"id": "root-comment", "type": "comment"},
                {"id": "reply-1", "type": "comment"},
            ],
        }

        comment = ConfluenceComment.from_api_response(data)

        assert comment.parent_comment_id == "reply-1"


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
        assert result[0].marker_ref == "marker-ref-123"
        assert result[0].original_selection == "some text to anchor"
        assert result[0].resolution_status == "open"
        # Verify expanded fields were requested
        comments_mixin_dc.confluence.get_page_comments.assert_called_once_with(
            content_id=page_id,
            expand=(
                "body.view.value,version,container,ancestors,"
                "extensions.inlineProperties,extensions.resolution"
            ),
            depth="all",
        )

    def test_get_inline_comments_v2_cloud_success(self, comments_mixin):
        """get_inline_comments uses v2 API on Cloud (any auth type)."""
        mock_adapter = MagicMock()
        mock_adapter.get_inline_comments.return_value = [
            {
                "id": "333444555",
                "type": "comment",
                "status": "open",
                "body": {
                    "view": {"value": "<p>v2 inline</p>", "representation": "view"}
                },
                "extensions": {"location": "inline"},
                "properties": {
                    "inlineMarkerRef": "cloud-marker-ref",
                    "inlineOriginalSelection": "selected cloud text",
                },
                "resolutionStatus": "open",
                "version": {"number": 1},
                "_links": {},
            },
            {
                "id": "444555666",
                "type": "comment",
                "status": "open",
                "parentCommentId": "333444555",
                "body": {
                    "view": {"value": "<p>v2 reply</p>", "representation": "view"}
                },
                "extensions": {"location": "inline"},
                "version": {"number": 1},
                "_links": {},
            },
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

        assert len(result) == 2
        assert result[0].parent_comment_id is None
        assert result[0].marker_ref == "cloud-marker-ref"
        assert result[0].original_selection == "selected cloud text"
        assert result[0].resolution_status == "open"
        assert result[1].parent_comment_id == result[0].id
        assert result[1].location == "inline"
        mock_adapter.get_inline_comments.assert_called_once_with("12345")
        # v1 API should not be called
        comments_mixin.confluence.get_page_comments.assert_not_called()

    def test_get_inline_comments_paginates_v1_results(self, comments_mixin_dc):
        """Server/DC inline comments include matches beyond the first page."""
        comments_mixin_dc.confluence.get_page_by_id.return_value = {
            "space": {"key": "TEST"}
        }
        footer_comment = {
            "id": "footer",
            "body": {"view": {"value": "<p>footer</p>"}},
            "extensions": {"location": "footer"},
        }
        comments_mixin_dc.confluence.get_page_comments.side_effect = [
            {
                "results": [footer_comment],
                "start": 0,
                "limit": 1,
                "size": 1,
                "_links": {"next": "/rest/api/content/12345/child/comment?start=1"},
            },
            {
                "results": [MOCK_INLINE_COMMENT_V1_RESPONSE],
                "start": 1,
                "limit": 1,
                "size": 1,
                "_links": {},
            },
        ]

        result = comments_mixin_dc.get_inline_comments("12345")

        assert [comment.id for comment in result] == ["333444555"]
        second_call = comments_mixin_dc.confluence.get_page_comments.call_args_list[1]
        assert second_call.kwargs["start"] == 1
        assert second_call.kwargs["limit"] == 1

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
        """add_inline_comment sends storage content as is (Server/DC)."""
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
            "12345", html_content, "some text", content_format="storage"
        )

        markdown_to_storage = (
            comments_mixin_dc.preprocessor.markdown_to_confluence_storage
        )
        markdown_to_storage.assert_not_called()
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


class TestCommentsMixinCloudOAuthRead:
    """Comment reads on Cloud OAuth go through the v2 API.

    Atlassian answers 410 Gone for the v1 page and ``child/comment`` reads on
    the OAuth gateway. The old path caught that error and returned an empty
    list, so a page with comments looked uncommented.
    """

    @pytest.fixture
    def oauth_comments_mixin(self, oauth_confluence_client):
        """Create a CommentsMixin configured for Cloud OAuth."""
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = CommentsMixin()
            mixin.confluence = oauth_confluence_client.confluence
            mixin.config = oauth_confluence_client.config
            mixin.preprocessor = oauth_confluence_client.preprocessor
            return mixin

    def test_get_page_comments_uses_v2_on_cloud_oauth(self, oauth_comments_mixin):
        """Footer and inline comments come from v2; the v1 reads are not made."""
        adapter = MagicMock()
        adapter.get_page.return_value = {"id": "1", "space": {"key": "FDE"}}
        adapter.get_footer_comments.return_value = [
            {
                "id": "1288142878",
                "type": "comment",
                "status": "current",
                "title": "Re: Page",
                "body": {"view": {"value": "<p>Footer</p>", "representation": "view"}},
                "version": {"number": 1, "createdAt": "2026-10-19T11:45:01.000Z"},
                "extensions": {"location": "footer"},
            }
        ]
        adapter.get_inline_comments.return_value = [
            {
                "id": "1306492931",
                "type": "comment",
                "status": "current",
                "title": "Re: Page",
                "body": {"view": {"value": "<p>Inline</p>", "representation": "view"}},
                "version": {"number": 1, "createdAt": "2026-10-19T11:45:01.000Z"},
                "extensions": {"location": "inline"},
            }
        ]
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter",
            return_value=adapter,
        ):
            result = oauth_comments_mixin.get_page_comments("1")

        adapter.get_page.assert_called_once_with("1")
        adapter.get_footer_comments.assert_called_once_with("1")
        adapter.get_inline_comments.assert_called_once_with("1")
        oauth_comments_mixin.confluence.get_page_by_id.assert_not_called()
        oauth_comments_mixin.confluence.get_page_comments.assert_not_called()
        assert [c.id for c in result] == ["1288142878", "1306492931"]
        oauth_comments_mixin.preprocessor.process_html_content.assert_any_call(
            "<p>Footer</p>",
            space_key="FDE",
            confluence_client=ANY,
        )

    def test_get_page_comments_v2_failure_returns_empty(self, oauth_comments_mixin):
        """An adapter failure still degrades to an empty list, as before."""
        adapter = MagicMock()
        adapter.get_page.return_value = {"id": "1", "space": {"key": "FDE"}}
        adapter.get_footer_comments.side_effect = ValueError("boom")
        with patch(
            "mcp_atlassian.confluence.comments.ConfluenceV2Adapter",
            return_value=adapter,
        ):
            assert oauth_comments_mixin.get_page_comments("1") == []


class _RecordingV2Session:
    """Fake v2 session: N root footer and inline comments, one reply each.

    Pages hold two results and point to the next page with a cursor, so the
    request count shows how much of the collection a read walks.
    """

    PAGE_SIZE = 2

    def __init__(self, roots: int, *, runaway: bool = False) -> None:
        self.roots = roots
        self.runaway = runaway
        self.urls: list[str] = []

    def _items(self, url: str) -> list[dict]:
        if url.endswith("/children"):
            parent = url.rsplit("/", 2)[-2]
            return [_v2_comment(f"{parent}-r")] if "-r" not in parent else []
        kind = "f" if "footer" in url else "i"
        return [_v2_comment(f"{kind}{n}") for n in range(self.roots)]

    def get(self, url: str, params: dict | None = None, **_: object) -> MagicMock:
        self.urls.append(url)
        if len(self.urls) > 2000:
            raise AssertionError("unbounded read")
        response = MagicMock()
        response.links = {}
        if url.endswith("/pages/1"):
            data: dict = {"id": "1", "title": "Page", "spaceId": "9"}
        else:
            offset = int((params or {}).get("cursor") or 0)
            items = self._items(url)
            data = {"results": items[offset : offset + self.PAGE_SIZE]}
            if self.runaway or offset + self.PAGE_SIZE < len(items):
                data["_links"] = {"next": f"{url}?cursor={offset + self.PAGE_SIZE}"}
        response.json.return_value = data
        return response


def _v2_comment(comment_id: str) -> dict:
    return {
        "id": comment_id,
        "status": "current",
        "body": {"storage": {"value": f"<p>{comment_id}</p>"}},
        "version": {"number": 1, "createdAt": "2026-01-01T00:00:00Z"},
    }


def _cloud_oauth_comments_mixin(session: _RecordingV2Session) -> CommentsMixin:
    mixin = CommentsMixin.__new__(CommentsMixin)
    mixin.config = MagicMock()
    mixin.config.is_cloud = True
    mixin.config.auth_type = "oauth"
    mixin.config.url = "https://api.atlassian.com/ex/confluence/site"
    mixin.confluence = MagicMock()
    mixin.confluence._session = session
    mixin.confluence.url = "https://api.atlassian.com/ex/confluence/site"
    mixin.preprocessor = ConfluencePreprocessor(base_url=mixin.config.url)
    return mixin


async def _call_get_comments_tool(fetcher: CommentsMixin) -> list[dict]:
    from fastmcp import Client, FastMCP
    from fastmcp.client import FastMCPTransport

    from mcp_atlassian.servers import confluence as confluence_tools

    mcp = FastMCP("comments-test")
    mcp.add_tool(confluence_tools.get_comments)
    with patch.object(
        confluence_tools, "get_confluence_fetcher", AsyncMock(return_value=fetcher)
    ):
        async with Client(transport=FastMCPTransport(mcp)) as client:
            result = await client.call_tool("get_comments", {"page_id": "1"})
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_get_comments_tool_bounds_comments_and_requests():
    """A page with many threads costs a bounded number of requests."""
    from mcp_atlassian.confluence.v2_adapter import (
        MAX_COMMENT_REQUESTS_PER_READ,
        MAX_COMMENTS_PER_READ,
    )

    session = _RecordingV2Session(roots=500)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    # Footer and inline collections are each one bounded read.
    assert len(comments) <= 2 * MAX_COMMENTS_PER_READ
    comment_requests = [u for u in session.urls if "comments" in u]
    assert len(comment_requests) <= 2 * MAX_COMMENT_REQUESTS_PER_READ
    assert comments, "the first comments are still returned"


@pytest.mark.anyio
async def test_get_comments_tool_small_page_is_complete():
    """Pages under the limits return every comment and reply."""
    session = _RecordingV2Session(roots=3)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    assert len(comments) == 12  # 3 roots + 3 replies, footer and inline


@pytest.mark.anyio
async def test_get_comments_tool_stops_runaway_cursor():
    """A cursor that never ends stops at the request limit."""
    from mcp_atlassian.confluence.v2_adapter import MAX_COMMENT_REQUESTS_PER_READ

    session = _RecordingV2Session(roots=1, runaway=True)
    await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    comment_requests = [u for u in session.urls if "comments" in u]
    assert len(comment_requests) <= 2 * MAX_COMMENT_REQUESTS_PER_READ


def test_v1_comment_listing_stops_at_item_limit():
    """The Server/DC listing stops paging once the item limit is reached."""
    from mcp_atlassian.confluence.v2_adapter import MAX_COMMENTS_PER_READ

    mixin = CommentsMixin.__new__(CommentsMixin)
    mixin.confluence = MagicMock()
    calls: list[int] = []

    def page(**kwargs: Any) -> dict:
        start = int(kwargs.get("start", 0) or 0)
        calls.append(start)
        if len(calls) > 1000:
            raise AssertionError("unbounded read")
        return {
            "results": [{"id": str(start + i)} for i in range(25)],
            "start": start,
            "size": 25,
            "limit": 25,
            "_links": {"next": "/next"},
        }

    mixin.confluence.get_page_comments.side_effect = page
    results = mixin._get_all_v1_page_comments("1", expand="body.view.value")

    assert len(results) == MAX_COMMENTS_PER_READ
    assert len(calls) == -(-MAX_COMMENTS_PER_READ // 25)


@pytest.mark.anyio
async def test_get_comments_tool_marks_truncated_list():
    """A cut-short read ends the list with one truncation marker item."""
    session = _RecordingV2Session(roots=500)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    assert comments[-1]["truncated"] is True
    assert comments[-1]["message"]
    assert all("truncated" not in c for c in comments[:-1])


@pytest.mark.anyio
async def test_get_comments_tool_complete_list_has_no_marker():
    session = _RecordingV2Session(roots=3)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    assert all("truncated" not in c for c in comments)


@pytest.mark.anyio
@pytest.mark.parametrize(("roots", "truncated"), [(500, True), (3, False)])
async def test_get_inline_comments_tool_reports_truncation(roots, truncated):
    from fastmcp import Client, FastMCP
    from fastmcp.client import FastMCPTransport

    from mcp_atlassian.servers import confluence as confluence_tools

    fetcher = _cloud_oauth_comments_mixin(_RecordingV2Session(roots=roots))
    mcp = FastMCP("inline-comments-test")
    mcp.add_tool(confluence_tools.get_inline_comments)
    with patch.object(
        confluence_tools, "get_confluence_fetcher", AsyncMock(return_value=fetcher)
    ):
        async with Client(transport=FastMCPTransport(mcp)) as client:
            result = await client.call_tool("get_inline_comments", {"page_id": "1"})
    body = json.loads(result.content[0].text)

    assert body["success"] is True
    assert body.get("truncated", False) is truncated
    assert ("hint" in body) is truncated


@pytest.mark.parametrize(
    ("total", "endless", "truncated"),
    [
        (200, False, False),
        (200, True, True),
        (199, False, False),
    ],
)
def test_v1_comment_listing_marks_more_comments(total, endless, truncated):
    """Stopping exactly at the item limit is truncation only if more remain."""
    from mcp_atlassian.utils.truncation import is_truncated

    mixin = CommentsMixin.__new__(CommentsMixin)
    mixin.confluence = MagicMock()

    def page(**kwargs: Any) -> dict:
        start = int(kwargs.get("start", 0) or 0)
        if start > 10_000:
            raise AssertionError("unbounded read")
        count = 25 if endless else max(0, min(25, total - start))
        more = endless or start + count < total
        response = {
            "results": [{"id": str(start + i)} for i in range(count)],
            "start": start,
            "size": count,
            "limit": 25,
            "_links": {"next": "/next"} if more else {},
        }
        return response

    mixin.confluence.get_page_comments.side_effect = page
    results = mixin._get_all_v1_page_comments("1", expand="body.view.value")

    assert len(results) == min(total, 200)
    assert is_truncated(results) is truncated


class _ConfigurableV2Session(_RecordingV2Session):
    """Like _RecordingV2Session, with a page size, replies and a stuck cursor."""

    def __init__(
        self,
        roots: int,
        *,
        page_size: int = 2,
        replies: bool = True,
        stuck_cursor: bool = False,
    ) -> None:
        super().__init__(roots)
        self.PAGE_SIZE = page_size
        self.replies = replies
        self.stuck_cursor = stuck_cursor

    def _items(self, url: str) -> list[dict]:
        if url.endswith("/children") and not self.replies:
            return []
        return super()._items(url)

    def get(self, url: str, params: dict | None = None, **_: object) -> MagicMock:
        if self.stuck_cursor and "footer-comments" in url and "/children" not in url:
            self.urls.append(url)
            if len(self.urls) > 2000:
                raise AssertionError("unbounded read")
            response = MagicMock()
            response.links = {}
            response.json.return_value = {
                "results": [],
                "_links": {"next": f"{url}?cursor=stuck"},
            }
            return response
        return super().get(url, params)


@pytest.mark.anyio
async def test_get_comments_tool_reports_repeated_cursor():
    """A stuck cursor ends the list with a 'may have more' marker."""
    session = _ConfigurableV2Session(roots=0, stuck_cursor=True)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    assert comments[-1]["truncated"] is True
    assert "may" in comments[-1]["message"]


@pytest.mark.anyio
async def test_get_comments_tool_unchecked_replies_say_may():
    """Replies left unchecked are reported as possible, not certain."""
    session = _ConfigurableV2Session(roots=200, page_size=250, replies=False)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    assert comments[-1]["truncated"] is True
    assert "may" in comments[-1]["message"]


@pytest.mark.anyio
async def test_get_comments_tool_certain_truncation_says_more():
    """Comments seen past the limit are reported as certainly missing."""
    session = _ConfigurableV2Session(roots=250, page_size=250, replies=False)
    comments = await _call_get_comments_tool(_cloud_oauth_comments_mixin(session))

    assert comments[-1]["truncated"] is True
    assert "may" not in comments[-1]["message"]
    assert "has more" in comments[-1]["message"]


def _mentions_body(users: range) -> dict[str, Any]:
    links = "".join(
        f'<ac:link><ri:user ri:account-id="acct-{i}" /></ac:link> ' for i in users
    )
    return {"storage": {"value": f"<p>{links}</p>"}}


def _counting_dc_comments_mixin(comments: list[dict[str, Any]]) -> CommentsMixin:
    with patch(
        "mcp_atlassian.confluence.comments.ConfluenceClient.__init__",
        return_value=None,
    ):
        mixin = CommentsMixin()
    mixin.config = ConfluenceConfig(
        url="https://confluence.example.com",
        auth_type="pat",
        personal_token="dummy",
    )
    client = MagicMock(
        spec_set=[
            "get_page_by_id",
            "get_page_comments",
            "get_user_details_by_accountid",
            "get_user_details_by_userkey",
            "get_user_details_by_username",
        ]
    )
    client.get_page_by_id.return_value = {"space": {"key": "TEST"}}
    client.get_page_comments.return_value = {"results": comments}
    client.get_user_details_by_accountid.side_effect = lambda ident: {
        "displayName": f"Name {ident}"
    }
    mixin.confluence = client
    mixin.preprocessor = ConfluencePreprocessor(base_url=mixin.config.url)
    return mixin


@pytest.mark.security_regression
@pytest.mark.parametrize("method", ["get_page_comments", "get_inline_comments"])
def test_user_lookups_are_capped_per_call_across_comments(method):
    """All comments of one call share one lookup budget and one cache."""
    from mcp_atlassian.preprocessing.base import MAX_USER_LOOKUPS_PER_CALL

    comments = [
        {
            "id": str(n),
            "type": "comment",
            "body": _mentions_body(range(n * 40, n * 40 + 40)),
            "extensions": {"location": "inline"},
        }
        for n in range(10)
    ]
    # Every comment also mentions acct-0, which must be looked up only once.
    for comment in comments:
        comment["body"]["storage"]["value"] += (
            '<p><ac:link><ri:user ri:account-id="acct-0" /></ac:link></p>'
        )
    mixin = _counting_dc_comments_mixin(comments)

    result = getattr(mixin, method)("12345")

    lookups = mixin.confluence.get_user_details_by_accountid
    assert lookups.call_count == MAX_USER_LOOKUPS_PER_CALL
    assert [c.args for c in lookups.call_args_list].count(("acct-0",)) == 1
    assert len(result) == 10
    assert all("@Name acct-0" in c.body for c in result)
    assert "@user\\_acct-399" in result[-1].body


class TestCommentContentFormat:
    """Comment bodies are Markdown unless the caller says storage."""

    MARKDOWN_BODY = "<b>bold</b> and **more**"

    @pytest.fixture
    def mixin(self, comments_mixin_dc):
        mixin = comments_mixin_dc
        mixin.confluence.get_page_by_id.side_effect = None
        mixin.confluence.get_page_by_id.return_value = {
            "id": "12345",
            "space": {"key": "TEST"},
            "container": {"id": "12345", "type": "page"},
        }
        mixin._resolve_page_id_for_parent_comment = MagicMock(return_value="12345")
        mixin.confluence.add_comment.return_value = {"id": "1"}
        mixin.confluence.post.return_value = {"id": "1"}
        mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            "<p>converted</p>"
        )
        mixin.preprocessor.process_html_content.return_value = ("<p/>", "")
        return mixin

    @staticmethod
    def _call(mixin, tool, body, **kwargs):
        if tool == "add_comment":
            return mixin.add_comment("12345", body, **kwargs)
        if tool == "reply_to_comment":
            return mixin.reply_to_comment("999", body, **kwargs)
        return mixin.add_inline_comment("12345", body, "some text", **kwargs)

    @staticmethod
    def _sent_body(mixin, tool):
        if tool == "add_comment":
            return mixin.confluence.add_comment.call_args.args[1]
        data = (
            mixin.confluence.post.call_args.kwargs.get("data")
            or (mixin.confluence.post.call_args.args[1])
        )
        return data["body"]["storage"]["value"]

    TOOLS = ["add_comment", "reply_to_comment", "add_inline_comment"]

    @pytest.mark.parametrize("tool", TOOLS)
    def test_markdown_starting_with_angle_bracket_is_converted(self, mixin, tool):
        assert self._call(mixin, tool, self.MARKDOWN_BODY) is not None
        mixin.preprocessor.markdown_to_confluence_storage.assert_called_once_with(
            self.MARKDOWN_BODY
        )
        assert self._sent_body(mixin, tool) == "<p>converted</p>"

    @pytest.mark.parametrize("tool", TOOLS)
    def test_storage_is_sent_unchanged(self, mixin, tool):
        body = '<ac:structured-macro ac:name="info"/>'
        assert self._call(mixin, tool, body, content_format="storage") is not None
        mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()
        assert self._sent_body(mixin, tool) == body

    @pytest.mark.parametrize("tool", TOOLS)
    def test_unknown_format_is_rejected(self, mixin, tool):
        with pytest.raises(ValueError, match="Invalid content_format 'wiki'"):
            self._call(mixin, tool, "x", content_format="wiki")
        mixin.confluence.add_comment.assert_not_called()
        mixin.confluence.post.assert_not_called()
