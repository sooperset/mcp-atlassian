"""Unit tests for the PropertiesMixin class."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.properties import PropertiesMixin


def _make_response(status_code: int, json_data: object) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        from requests.exceptions import HTTPError

        resp.raise_for_status.side_effect = HTTPError(
            response=resp, request=MagicMock()
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestPropertiesMixin:
    """Tests for PropertiesMixin."""

    @pytest.fixture
    def properties_mixin(self, confluence_client):
        """Create a PropertiesMixin instance backed by the shared mock client."""
        with patch(
            "mcp_atlassian.confluence.properties.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = PropertiesMixin()
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            # Attach a mock session with a recognisable base URL
            mixin.confluence.url = "https://example.atlassian.net/wiki"
            mixin.confluence._session = MagicMock()
            return mixin

    # ------------------------------------------------------------------
    # get_content_properties — all properties
    # ------------------------------------------------------------------

    def test_get_all_properties_success(self, properties_mixin):
        page_id = "123456789"
        api_response = {
            "results": [
                {"key": "content-appearance-published", "value": "full-width"},
                {"key": "content-appearance-draft", "value": "fixed-width"},
            ]
        }
        properties_mixin.confluence._session.get.return_value = _make_response(
            200, api_response
        )

        result = properties_mixin.get_content_properties(page_id)

        properties_mixin.confluence._session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/rest/api/content/123456789/property",
            params={"expand": "version"},
        )
        assert result == {
            "content-appearance-published": "full-width",
            "content-appearance-draft": "fixed-width",
        }

    def test_get_all_properties_empty(self, properties_mixin):
        properties_mixin.confluence._session.get.return_value = _make_response(
            200, {"results": []}
        )

        result = properties_mixin.get_content_properties("123456789")

        assert result == {}

    # ------------------------------------------------------------------
    # get_content_properties — single key
    # ------------------------------------------------------------------

    def test_get_single_property_success(self, properties_mixin):
        page_id = "123456789"
        key = "content-appearance-published"
        api_response = {
            "key": key,
            "value": "full-width",
            "version": {"number": 2},
        }
        properties_mixin.confluence._session.get.return_value = _make_response(
            200, api_response
        )

        result = properties_mixin.get_content_properties(page_id, key=key)

        properties_mixin.confluence._session.get.assert_called_once_with(
            f"https://example.atlassian.net/wiki/rest/api/content/{page_id}/property/{key}"
        )
        assert result == {key: "full-width"}

    def test_get_single_property_api_error(self, properties_mixin):
        properties_mixin.confluence._session.get.return_value = _make_response(
            500, {"message": "Internal Server Error"}
        )

        with pytest.raises(Exception, match="Failed to get content properties"):
            properties_mixin.get_content_properties("123456789", key="some-key")

    # ------------------------------------------------------------------
    # set_content_property — create (404 on GET)
    # ------------------------------------------------------------------

    def test_set_property_creates_when_not_exists(self, properties_mixin):
        page_id = "123456789"
        key = "content-appearance-published"
        value = "full-width"

        get_resp = _make_response(404, {"message": "Not found"})
        post_resp = _make_response(200, {"key": key, "value": value})
        properties_mixin.confluence._session.get.return_value = get_resp
        properties_mixin.confluence._session.post.return_value = post_resp

        result = properties_mixin.set_content_property(page_id, key, value)

        properties_mixin.confluence._session.post.assert_called_once_with(
            f"https://example.atlassian.net/wiki/rest/api/content/{page_id}/property",
            json={"key": key, "value": value},
        )
        assert result == {key: value}

    # ------------------------------------------------------------------
    # set_content_property — update (200 on GET, auto-version)
    # ------------------------------------------------------------------

    def test_set_property_updates_existing(self, properties_mixin):
        page_id = "123456789"
        key = "content-appearance-published"
        old_value = "fixed-width"
        new_value = "full-width"

        get_resp = _make_response(
            200,
            {"key": key, "value": old_value, "version": {"number": 2}},
        )
        put_resp = _make_response(200, {"key": key, "value": new_value})
        properties_mixin.confluence._session.get.return_value = get_resp
        properties_mixin.confluence._session.put.return_value = put_resp

        result = properties_mixin.set_content_property(page_id, key, new_value)

        properties_mixin.confluence._session.put.assert_called_once_with(
            f"https://example.atlassian.net/wiki/rest/api/content/{page_id}/property/{key}",
            json={"key": key, "value": new_value, "version": {"number": 3}},
        )
        assert result == {key: new_value}

    def test_set_property_version_starts_at_1_when_missing(self, properties_mixin):
        """If the existing property has no version info, version should default to 1."""
        page_id = "123456789"
        key = "custom-key"

        get_resp = _make_response(200, {"key": key, "value": "old"})
        put_resp = _make_response(200, {"key": key, "value": "new"})
        properties_mixin.confluence._session.get.return_value = get_resp
        properties_mixin.confluence._session.put.return_value = put_resp

        properties_mixin.set_content_property(page_id, key, "new")

        call_kwargs = properties_mixin.confluence._session.put.call_args
        assert call_kwargs.kwargs["json"]["version"]["number"] == 1

    def test_set_property_api_error_on_put(self, properties_mixin):
        page_id = "123456789"
        key = "content-appearance-published"

        get_resp = _make_response(
            200, {"key": key, "value": "fixed-width", "version": {"number": 1}}
        )
        put_resp = _make_response(409, {"message": "Version conflict"})
        properties_mixin.confluence._session.get.return_value = get_resp
        properties_mixin.confluence._session.put.return_value = put_resp

        with pytest.raises(Exception, match="Failed to set content property"):
            properties_mixin.set_content_property(page_id, key, "full-width")

    def test_set_property_api_error_on_post(self, properties_mixin):
        page_id = "123456789"
        key = "new-key"

        get_resp = _make_response(404, {"message": "Not found"})
        post_resp = _make_response(400, {"message": "Bad request"})
        properties_mixin.confluence._session.get.return_value = get_resp
        properties_mixin.confluence._session.post.return_value = post_resp

        with pytest.raises(Exception, match="Failed to set content property"):
            properties_mixin.set_content_property(page_id, key, "some-value")
