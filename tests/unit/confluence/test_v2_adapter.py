"""Unit tests for ConfluenceV2Adapter class."""

from unittest.mock import MagicMock, Mock, call

import pytest
import requests
from requests.exceptions import HTTPError

from mcp_atlassian.confluence.v2_adapter import ConfluenceV2Adapter


class TestConfluenceV2Adapter:
    """Test cases for ConfluenceV2Adapter."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        return MagicMock(spec=requests.Session)

    @pytest.fixture
    def v2_adapter(self, mock_session):
        """Create a ConfluenceV2Adapter instance."""
        return ConfluenceV2Adapter(
            session=mock_session, base_url="https://example.atlassian.net/wiki"
        )

    def test_get_page_success(self, v2_adapter, mock_session):
        """Test successful page retrieval."""
        # Mock the v2 API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "123456",
            "status": "current",
            "title": "Test Page",
            "spaceId": "789",
            "authorId": "creator-account-id",
            "createdAt": "2024-01-01T09:00:00.000Z",
            "version": {
                "number": 5,
                "createdAt": "2024-01-02T10:00:00.000Z",
                "authorId": "updater-account-id",
                "message": "Updated page content",
            },
            "body": {
                "storage": {"value": "<p>Test content</p>", "representation": "storage"}
            },
            "_links": {"webui": "/pages/viewpage.action?pageId=123456"},
        }
        mock_session.get.return_value = mock_response

        # Mock space key lookup
        space_response = Mock()
        space_response.status_code = 200
        space_response.json.return_value = {"key": "TEST"}
        mock_session.get.side_effect = [mock_response, space_response]

        # Call the method
        result = v2_adapter.get_page("123456")

        # Verify the API call
        assert mock_session.get.call_count == 2
        mock_session.get.assert_any_call(
            "https://example.atlassian.net/wiki/api/v2/pages/123456",
            params={"body-format": "storage"},
        )

        # Verify the response format
        assert result["id"] == "123456"
        assert result["type"] == "page"
        assert result["title"] == "Test Page"
        assert result["space"]["key"] == "TEST"
        assert result["space"]["id"] == "789"
        assert result["version"]["number"] == 5
        assert result["version"]["when"] == "2024-01-02T10:00:00.000Z"
        assert result["version"]["by"]["accountId"] == "updater-account-id"
        assert result["history"]["createdDate"] == "2024-01-01T09:00:00.000Z"
        assert result["history"]["createdBy"]["accountId"] == "creator-account-id"
        assert result["history"]["lastUpdated"]["when"] == "2024-01-02T10:00:00.000Z"
        assert result["body"]["storage"]["value"] == "<p>Test content</p>"
        assert result["body"]["storage"]["representation"] == "storage"

    def test_get_page_not_found(self, v2_adapter, mock_session):
        """Test page retrieval when page doesn't exist."""
        # Mock a 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Page not found"
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_session.get.return_value = mock_response

        # Call the method and expect an exception
        with pytest.raises(ValueError, match="Failed to get page '999999'"):
            v2_adapter.get_page("999999")

    def test_get_page_with_minimal_response(self, v2_adapter, mock_session):
        """Test page retrieval with minimal v2 response."""
        # Mock the v2 API response without optional fields
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "123456",
            "status": "current",
            "title": "Minimal Page",
        }
        mock_session.get.return_value = mock_response

        # Call the method
        result = v2_adapter.get_page("123456")

        # Verify the response handles missing fields gracefully
        assert result["id"] == "123456"
        assert result["type"] == "page"
        assert result["title"] == "Minimal Page"
        assert result["space"]["key"] == "unknown"  # Fallback when no spaceId
        assert result["version"]["number"] == 1  # Default version

    def test_get_page_network_error(self, v2_adapter, mock_session):
        """Test page retrieval with network error."""
        # Mock a network error
        mock_session.get.side_effect = requests.RequestException("Network error")

        # Call the method and expect an exception
        with pytest.raises(ValueError, match="Failed to get page '123456'"):
            v2_adapter.get_page("123456")

    def test_create_page_with_live_subtype(self, v2_adapter, mock_session):
        """Test creating a Live Doc page passes subtype to the v2 API."""
        space_response = Mock()
        space_response.json.return_value = {"results": [{"id": "space-123"}]}
        create_response = Mock()
        create_response.json.return_value = {
            "id": "page-123",
            "status": "current",
            "title": "Live Agenda",
            "spaceId": "space-123",
            "subtype": "live",
            "version": {"number": 1},
        }
        mock_session.get.return_value = space_response
        mock_session.post.return_value = create_response

        result = v2_adapter.create_page(
            space_key="TEAM",
            title="Live Agenda",
            body="<p>Agenda</p>",
            parent_id="parent-123",
            subtype="live",
        )

        mock_session.post.assert_called_once_with(
            "https://example.atlassian.net/wiki/api/v2/pages",
            json={
                "spaceId": "space-123",
                "status": "current",
                "title": "Live Agenda",
                "body": {
                    "representation": "storage",
                    "value": "<p>Agenda</p>",
                },
                "parentId": "parent-123",
                "subtype": "live",
            },
        )
        assert result["id"] == "page-123"
        assert result["subtype"] == "live"

    def test_get_page_with_expand_parameter(self, v2_adapter, mock_session):
        """Test that expand parameter is accepted but not used."""
        # Mock the v2 API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "123456",
            "status": "current",
            "title": "Test Page",
        }
        mock_session.get.return_value = mock_response

        # Call with expand parameter
        result = v2_adapter.get_page("123456", expand="body.storage,version")

        # Verify the API call doesn't include expand in params
        mock_session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/api/v2/pages/123456",
            params={"body-format": "storage"},
        )

        # Verify we still get a result
        assert result["id"] == "123456"

    def test_get_page_direct_children_resolves_space_key(
        self, v2_adapter, mock_session
    ):
        """Test v2 direct children are normalized with space metadata."""
        children_response = Mock()
        children_response.status_code = 200
        children_response.json.return_value = {
            "results": [
                {
                    "id": "123456",
                    "status": "current",
                    "title": "Child Page",
                    "type": "page",
                    "spaceId": "789",
                }
            ]
        }

        space_response = Mock()
        space_response.status_code = 200
        space_response.json.return_value = {"key": "TEST", "name": "Test Space"}

        mock_session.get.side_effect = [children_response, space_response]

        result = v2_adapter.get_page_direct_children("999")

        assert result["results"][0]["space"] == {
            "id": "789",
            "key": "TEST",
            "name": "Test Space",
        }
        assert mock_session.get.call_count == 2

    def test_get_page_direct_children_handles_repeated_space_ids(
        self, v2_adapter, mock_session
    ):
        """Test v2 direct children resolve each space ID once."""
        children_response = Mock()
        children_response.status_code = 200
        children_response.json.return_value = {
            "results": [
                {"id": "1", "title": "A", "type": "page", "spaceId": "789"},
                {"id": "2", "title": "B", "type": "folder", "spaceId": "789"},
            ]
        }

        space_response = Mock()
        space_response.status_code = 200
        space_response.json.return_value = {"key": "TEST", "name": "Test Space"}

        mock_session.get.side_effect = [children_response, space_response]

        result = v2_adapter.get_page_direct_children("999")

        assert result["results"][0]["space"]["key"] == "TEST"
        assert result["results"][1]["space"]["key"] == "TEST"
        assert result["results"][0]["space"]["name"] == "Test Space"
        assert mock_session.get.call_count == 2

    def test_get_page_direct_children_handles_numeric_space_id(
        self, v2_adapter, mock_session
    ):
        """Test numeric space IDs are normalized before lookup."""
        children_response = Mock()
        children_response.status_code = 200
        children_response.json.return_value = {
            "results": [
                {
                    "id": "123456",
                    "status": "current",
                    "title": "Child Page",
                    "type": "page",
                    "spaceId": 789,
                }
            ]
        }

        space_response = Mock()
        space_response.status_code = 200
        space_response.json.return_value = {"key": "TEST", "name": "Test Space"}

        mock_session.get.side_effect = [children_response, space_response]

        result = v2_adapter.get_page_direct_children("999")

        assert result["results"][0]["space"] == {
            "id": "789",
            "key": "TEST",
            "name": "Test Space",
        }
        assert mock_session.get.call_args_list[1][0][0].endswith("/api/v2/spaces/789")

    def test_get_page_direct_children_preserves_next_link_header(
        self, v2_adapter, mock_session
    ):
        """Test v2 pagination can use the response Link header."""
        children_response = Mock()
        children_response.status_code = 200
        children_response.links = {
            "next": {
                "url": (
                    "https://example.atlassian.net/wiki/api/v2/pages/999/"
                    "direct-children?cursor=next-token"
                )
            }
        }
        children_response.json.return_value = {
            "results": [{"id": "123456", "status": "current", "title": "Child Page"}]
        }

        mock_session.get.return_value = children_response

        result = v2_adapter.get_page_direct_children("999")

        assert result["_links"]["next"].endswith("cursor=next-token")

    @pytest.mark.parametrize(
        "method,call_kwargs,expected_path",
        [
            (
                "get_page_views",
                {"page_id": "123"},
                "/rest/api/analytics/content/123/views",
            ),
            (
                "get_page_attachments",
                {"page_id": "123"},
                "/api/v2/pages/123/attachments",
            ),
            (
                "get_attachment_by_id",
                {"attachment_id": "att-1"},
                "/api/v2/attachments/att-1",
            ),
            (
                "delete_attachment",
                {"attachment_id": "att-1"},
                "/api/v2/attachments/att-1",
            ),
        ],
        ids=["analytics", "page_attachments", "get_attachment", "delete_attachment"],
    )
    def test_no_double_wiki_prefix(
        self, v2_adapter, mock_session, method, call_kwargs, expected_path
    ):
        """Regression: URLs must not duplicate /wiki (issue #962)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"count": 0, "results": []}
        mock_session.get.return_value = mock_response
        mock_session.delete.return_value = mock_response

        getattr(v2_adapter, method)(**call_kwargs)

        # Grab the URL from whichever HTTP method was called
        if method == "delete_attachment":
            url = mock_session.delete.call_args[0][0]
        else:
            url = mock_session.get.call_args[0][0]

        assert "/wiki/wiki/" not in url, f"Double /wiki in URL: {url}"
        assert url.endswith(expected_path), f"Expected {expected_path}, got {url}"


class TestConfluenceV2AdapterComments:
    """Tests for v2 adapter comment operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        return MagicMock(spec=requests.Session)

    @pytest.fixture
    def v2_adapter(self, mock_session):
        """Create a ConfluenceV2Adapter instance."""
        return ConfluenceV2Adapter(
            session=mock_session, base_url="https://example.atlassian.net/wiki"
        )

    def test_get_inline_comments_includes_nested_replies(
        self, v2_adapter, mock_session
    ):
        """Cloud inline reads traverse descendants without duplicating cycles."""

        def comment(comment_id: str) -> dict:
            return {
                "id": comment_id,
                "status": "current",
                "body": {
                    "storage": {
                        "value": f"<p>{comment_id}</p>",
                        "representation": "storage",
                    }
                },
                "version": {"number": 1},
                "_links": {},
            }

        root_response = Mock()
        root_response.json.return_value = {"results": [comment("root")]}
        child_response = Mock()
        child_response.json.return_value = {"results": [comment("child")]}
        grandchild_response = Mock()
        grandchild_response.json.return_value = {"results": [comment("grandchild")]}
        cycle_response = Mock()
        cycle_response.json.return_value = {"results": [comment("root")]}
        mock_session.get.side_effect = [
            root_response,
            child_response,
            grandchild_response,
            cycle_response,
        ]

        result = v2_adapter.get_inline_comments("page-1")

        assert [item["id"] for item in result] == ["root", "child", "grandchild"]
        assert result[1]["parentCommentId"] == "root"
        assert result[2]["parentCommentId"] == "child"
        assert mock_session.get.call_args_list == [
            call(
                "https://example.atlassian.net/wiki/api/v2/pages/page-1/inline-comments",
                params={"body-format": "storage"},
            ),
            call(
                "https://example.atlassian.net/wiki/api/v2/inline-comments/root/children",
                params={"body-format": "storage"},
            ),
            call(
                "https://example.atlassian.net/wiki/api/v2/inline-comments/child/children",
                params={"body-format": "storage"},
            ),
            call(
                "https://example.atlassian.net/wiki/api/v2/inline-comments/"
                "grandchild/children",
                params={"body-format": "storage"},
            ),
        ]

    def test_get_inline_comments_paginates_roots_and_replies(
        self, v2_adapter, mock_session
    ):
        """Cloud root and child collections follow both next-link shapes."""

        def response(results: list[dict], next_url: str | None = None) -> Mock:
            item = Mock()
            item.links = {}
            item.json.return_value = {
                "results": results,
                "_links": {"next": next_url} if next_url else {},
            }
            return item

        def get(url: str, params: dict) -> Mock:
            cursor = params.get("cursor")
            if url.endswith("/pages/page-1/inline-comments"):
                if cursor == "root-next":
                    return response([{"id": "root-2"}])
                return response(
                    [{"id": "root-1"}],
                    "/wiki/api/v2/pages/page-1/inline-comments?cursor=root-next",
                )
            if url.endswith("/inline-comments/root-1/children"):
                if cursor == "child-next":
                    return response([{"id": "child-2"}])
                item = response([{"id": "child-1"}])
                item.links = {
                    "next": {
                        "url": (
                            "https://example.atlassian.net/wiki/api/v2/"
                            "inline-comments/root-1/children?cursor=child-next"
                        )
                    }
                }
                return item
            return response([])

        mock_session.get.side_effect = get

        result = v2_adapter.get_inline_comments("page-1", status="resolved")

        assert [item["id"] for item in result] == [
            "root-1",
            "root-2",
            "child-1",
            "child-2",
        ]
        assert result[2]["parentCommentId"] == "root-1"
        assert result[3]["parentCommentId"] == "root-1"
        assert (
            call(
                "https://example.atlassian.net/wiki/api/v2/pages/page-1/inline-comments",
                params={
                    "body-format": "storage",
                    "status": "resolved",
                    "cursor": "root-next",
                },
            )
            in mock_session.get.call_args_list
        )
        assert (
            call(
                "https://example.atlassian.net/wiki/api/v2/inline-comments/"
                "root-1/children",
                params={"body-format": "storage", "cursor": "child-next"},
            )
            in mock_session.get.call_args_list
        )

    def test_get_inline_comments_fails_when_child_read_fails(
        self, v2_adapter, mock_session
    ):
        """A failed child request does not return a misleading partial tree."""
        root_response = Mock()
        root_response.json.return_value = {"results": [{"id": "root"}]}
        error_response = Mock(status_code=500, text="server error")
        error_response.raise_for_status.side_effect = HTTPError(response=error_response)
        mock_session.get.side_effect = [root_response, error_response]

        with pytest.raises(ValueError, match="Failed to get inline comments"):
            v2_adapter.get_inline_comments("page-1")

    def test_create_footer_comment_both_params_raises(self, v2_adapter):
        """T11a: Passing both page_id and parent_comment_id raises ValueError."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            v2_adapter.create_footer_comment(
                page_id="12345",
                parent_comment_id="67890",
                body="<p>Test</p>",
            )

    def test_get_inline_comments_preserves_review_metadata(
        self, v2_adapter, mock_session
    ):
        """Cloud v2 anchor, resolution, and thread fields survive conversion."""
        root_response = Mock()
        root_response.json.return_value = {
            "results": [
                {
                    "id": "comment-1",
                    "status": "current",
                    "properties": {
                        "inlineMarkerRef": "marker-ref-123",
                        "inlineOriginalSelection": "selected text",
                    },
                    "resolutionStatus": "open",
                    "body": {
                        "storage": {
                            "value": "<p>Review comment</p>",
                            "representation": "storage",
                        }
                    },
                    "version": {"createdAt": "2024-01-03T10:00:00.000Z"},
                }
            ]
        }
        child_response = Mock()
        child_response.json.return_value = {
            "results": [
                {
                    "id": "comment-2",
                    "status": "current",
                    "parentCommentId": "comment-1",
                    "body": {"storage": {"value": "<p>Reply</p>"}},
                }
            ]
        }
        empty_response = Mock()
        empty_response.json.return_value = {"results": []}
        mock_session.get.side_effect = [
            root_response,
            child_response,
            empty_response,
        ]

        result = v2_adapter.get_inline_comments("12345")

        assert [comment["id"] for comment in result] == ["comment-1", "comment-2"]
        assert result[0]["properties"]["inlineMarkerRef"] == "marker-ref-123"
        assert result[0]["resolutionStatus"] == "open"
        assert result[1]["parentCommentId"] == "comment-1"

    def test_create_footer_comment_neither_param_raises(self, v2_adapter):
        """T11b: Passing neither page_id nor parent_comment_id raises ValueError."""
        with pytest.raises(ValueError, match="Either"):
            v2_adapter.create_footer_comment(body="<p>Test</p>")

    def test_create_footer_comment_reply(self, v2_adapter, mock_session):
        """T12: Create reply with parentCommentId sends correct POST payload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "222333444",
            "status": "current",
            "title": "Re: Comment",
            "parentCommentId": "456789123",
            "pageId": "12345",
            "body": {
                "storage": {
                    "value": "<p>Reply content</p>",
                    "representation": "storage",
                },
            },
            "version": {"number": 1},
            "_links": {},
        }
        mock_session.post.return_value = mock_response

        result = v2_adapter.create_footer_comment(
            parent_comment_id="456789123",
            body="<p>Reply content</p>",
        )

        # Verify POST was called with correct URL and payload
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == (
            "https://example.atlassian.net/wiki/api/v2/footer-comments"
        )
        payload = call_args[1]["json"]
        assert payload["parentCommentId"] == "456789123"
        assert "pageId" not in payload

        # Verify the result is in v1-compatible format with body.view
        assert result["id"] == "222333444"
        assert result["body"]["view"]["value"] == "<p>Reply content</p>"
        assert result["extensions"]["location"] == "footer"
        mock_session.get.assert_not_called()

    def test_create_footer_comment_refreshes_missing_body(
        self, v2_adapter, mock_session
    ):
        """A create response without body content is refreshed once."""
        create_response = Mock()
        create_response.json.return_value = {
            "id": "222333444",
            "status": "current",
            "title": "Re: Comment",
            "parentCommentId": "456789123",
            "version": {"number": 1},
            "_links": {},
        }
        refresh_response = Mock()
        refresh_response.json.return_value = {
            "id": "222333444",
            "status": "current",
            "title": "Re: Comment",
            "parentCommentId": "456789123",
            "body": {
                "storage": {
                    "value": "<p>Refreshed reply</p>",
                    "representation": "storage",
                },
            },
            "version": {"number": 1},
            "_links": {},
        }
        mock_session.post.return_value = create_response
        mock_session.get.return_value = refresh_response

        result = v2_adapter.create_footer_comment(
            parent_comment_id="456789123",
            body="<p>Reply content</p>",
        )

        mock_session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/api/v2/footer-comments/222333444",
            params={"body-format": "storage"},
        )
        assert result["body"]["view"]["value"] == "<p>Refreshed reply</p>"

    def test_create_footer_comment_keeps_create_response_when_refresh_fails(
        self, v2_adapter, mock_session
    ):
        """A refresh failure doesn't discard a successful create response."""
        create_response = Mock()
        create_response.json.return_value = {
            "id": "222333444",
            "status": "current",
            "title": "Re: Comment",
            "parentCommentId": "456789123",
            "version": {"number": 1},
            "_links": {},
        }
        mock_session.post.return_value = create_response
        mock_session.get.side_effect = requests.RequestException("refresh failed")

        result = v2_adapter.create_footer_comment(
            parent_comment_id="456789123",
            body="<p>Reply content</p>",
        )

        assert result["id"] == "222333444"
        assert result["body"]["view"]["value"] == ""
        mock_session.get.assert_called_once()

    def test_create_footer_comment_top_level(self, v2_adapter, mock_session):
        """Create top-level comment with pageId sends correct payload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "333444555",
            "status": "current",
            "title": "New Comment",
            "pageId": "12345",
            "body": {
                "storage": {
                    "value": "<p>Top-level comment</p>",
                    "representation": "storage",
                },
            },
            "version": {"number": 1},
            "_links": {},
        }
        mock_session.post.return_value = mock_response

        result = v2_adapter.create_footer_comment(
            page_id="12345",
            body="<p>Top-level comment</p>",
        )

        # Verify payload
        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        assert payload["pageId"] == "12345"
        assert "parentCommentId" not in payload
        assert result["id"] == "333444555"


class TestConfluenceV2AdapterPageVersion:
    """`get_page_by_version` must ask the page endpoint for the version (#1373)."""

    @pytest.fixture
    def mock_session(self):
        return MagicMock(spec=requests.Session)

    @pytest.fixture
    def v2_adapter(self, mock_session):
        return ConfluenceV2Adapter(
            session=mock_session, base_url="https://example.atlassian.net/wiki"
        )

    def _page_response(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "id": "123456",
            "status": "current",
            "title": "Test Page",
            "spaceId": "789",
            "version": {
                "number": 3,
                "createdAt": "2024-01-02T10:00:00.000Z",
                "authorId": "author-id",
                "message": "third revision",
            },
            "body": {
                "storage": {"value": "<p>v3 content</p>", "representation": "storage"}
            },
        }
        return response

    def _space_response(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"key": "TEST"}
        return response

    def test_requests_version_from_page_endpoint(self, v2_adapter, mock_session):
        mock_session.get.side_effect = [self._page_response(), self._space_response()]

        result = v2_adapter.get_page_by_version("123456", 3)

        url, kwargs = (
            mock_session.get.call_args_list[0][0],
            mock_session.get.call_args_list[0][1],
        )
        assert url[0] == "https://example.atlassian.net/wiki/api/v2/pages/123456"
        assert kwargs["params"]["version"] == 3
        assert kwargs["params"]["body-format"] == "storage"
        assert result["body"]["storage"]["value"] == "<p>v3 content</p>"
        assert result["version"]["number"] == 3

    def test_does_not_call_the_versions_endpoints(self, v2_adapter, mock_session):
        """PageVersion objects carry no id, so the two-step lookup can never work."""
        mock_session.get.side_effect = [self._page_response(), self._space_response()]

        v2_adapter.get_page_by_version("123456", 3)

        requested = [call[0][0] for call in mock_session.get.call_args_list]
        assert not any("/versions" in url for url in requested)
