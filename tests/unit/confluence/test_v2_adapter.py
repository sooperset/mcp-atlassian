"""Unit tests for ConfluenceV2Adapter class."""

from unittest.mock import MagicMock, Mock

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
            "version": {"number": 5},
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

    def test_get_spaces_single_page(self, v2_adapter, mock_session):
        """v2 /spaces response is returned in a v1-compatible envelope
        with a single request when the first page covers the window."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "111",
                    "key": "ABC",
                    "name": "Alpha",
                    "type": "global",
                    "_links": {"webui": "/spaces/ABC"},
                },
                {
                    "id": "222",
                    "key": "DEF",
                    "name": "Delta",
                    "type": "global",
                    "_links": {"webui": "/spaces/DEF"},
                },
            ],
            "_links": {},
        }
        mock_session.get.return_value = mock_response

        result = v2_adapter.get_spaces(start=0, limit=10)

        mock_session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/api/v2/spaces",
            params={"limit": 10},
        )
        assert result["start"] == 0
        assert result["limit"] == 10
        assert result["size"] == 2
        assert [s["key"] for s in result["results"]] == ["ABC", "DEF"]
        # v1-compat shape preserved
        assert result["results"][0]["id"] == "111"
        assert result["results"][0]["name"] == "Alpha"
        assert result["results"][0]["type"] == "global"
        assert result["results"][0]["_links"] == {"webui": "/spaces/ABC"}

    def test_resolve_v2_next_link_does_not_double_wiki_prefix(self, v2_adapter):
        """A /wiki-prefixed next link must not be double-prefixed when
        the adapter's base_url already ends with /wiki."""
        resolved = v2_adapter._resolve_v2_next_link("/wiki/api/v2/spaces?cursor=abc")
        assert resolved == (
            "https://example.atlassian.net/wiki/api/v2/spaces?cursor=abc"
        )

    def test_resolve_v2_next_link_passes_absolute_urls_through(self, v2_adapter):
        """Absolute URLs are returned unchanged."""
        absolute = "https://other.example.com/wiki/api/v2/spaces?cursor=z"
        assert v2_adapter._resolve_v2_next_link(absolute) == absolute

    def test_get_spaces_walks_cursor_and_applies_start_offset(
        self, v2_adapter, mock_session
    ):
        """When the requested window spans two cursor pages, the adapter
        walks _links.next until the window is covered, then slices."""
        page1 = Mock()
        page1.status_code = 200
        page1.json.return_value = {
            "results": [
                {
                    "id": "1",
                    "key": "A",
                    "name": "A",
                    "type": "global",
                    "_links": {},
                },
                {
                    "id": "2",
                    "key": "B",
                    "name": "B",
                    "type": "global",
                    "_links": {},
                },
            ],
            "_links": {"next": "/wiki/api/v2/spaces?cursor=abc"},
        }
        page2 = Mock()
        page2.status_code = 200
        page2.json.return_value = {
            "results": [
                {
                    "id": "3",
                    "key": "C",
                    "name": "C",
                    "type": "global",
                    "_links": {},
                },
                {
                    "id": "4",
                    "key": "D",
                    "name": "D",
                    "type": "global",
                    "_links": {},
                },
            ],
            "_links": {},
        }
        mock_session.get.side_effect = [page1, page2]

        result = v2_adapter.get_spaces(start=2, limit=2)

        # Two cursor pages fetched before slicing.
        assert mock_session.get.call_count == 2
        first_call = mock_session.get.call_args_list[0]
        assert first_call.args == ("https://example.atlassian.net/wiki/api/v2/spaces",)
        assert first_call.kwargs == {"params": {"limit": 2}}
        second_call = mock_session.get.call_args_list[1]
        # Cursor URL resolved against base host; params=None on cursor hop.
        assert second_call.args[0].endswith("/wiki/api/v2/spaces?cursor=abc")
        assert second_call.kwargs == {"params": None}

        # Slice semantics: start=2, limit=2 → results[2:4] == C, D.
        assert [s["key"] for s in result["results"]] == ["C", "D"]
        assert result["start"] == 2
        assert result["limit"] == 2
        assert result["size"] == 2

    def test_get_spaces_empty_result(self, v2_adapter, mock_session):
        """Empty v2 result returns an empty v1-compatible envelope."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "_links": {}}
        mock_session.get.return_value = mock_response

        result = v2_adapter.get_spaces(start=0, limit=10)

        assert result == {
            "results": [],
            "start": 0,
            "limit": 10,
            "size": 0,
        }

    def test_get_spaces_http_error_raises_value_error(self, v2_adapter, mock_session):
        """HTTP errors surface as ValueError with context, matching the
        rest of the adapter's error-handling contract."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "boom"
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_session.get.return_value = mock_response

        with pytest.raises(ValueError, match="Failed to list spaces"):
            v2_adapter.get_spaces(start=0, limit=10)


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

    def test_create_footer_comment_both_params_raises(self, v2_adapter):
        """T11a: Passing both page_id and parent_comment_id raises ValueError."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            v2_adapter.create_footer_comment(
                page_id="12345",
                parent_comment_id="67890",
                body="<p>Test</p>",
            )

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
