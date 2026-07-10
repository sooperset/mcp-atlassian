"""Unit tests for Confluence template operations."""

from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.confluence.templates import TemplatesMixin
from mcp_atlassian.models.confluence import ConfluencePage


@pytest.fixture
def templates_mixin(confluence_client):
    """Return a TemplatesMixin with a mocked Confluence client."""
    with patch(
        "mcp_atlassian.confluence.templates.ConfluenceClient.__init__"
    ) as mock_init:
        mock_init.return_value = None
        mixin = TemplatesMixin()
        mixin.confluence = confluence_client.confluence
        mixin.config = confluence_client.config
        mixin.preprocessor = confluence_client.preprocessor
        return mixin


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_TEMPLATE_SUMMARY = {
    "templateId": "tpl-001",
    "name": "Meeting Notes",
    "templateType": "page",
    "description": {"value": "Standard meeting notes template"},
    "body": {"storage": {"value": "<h1>Meeting Notes</h1>"}},
}

_TEMPLATE_SUMMARY_2 = {
    "templateId": "tpl-002",
    "name": "Project Charter",
    "templateType": "page",
    "description": {"value": ""},
    "body": {"storage": {"value": "<h1>Project Charter</h1>"}},
}


def _set_api_response(
    templates_mixin: TemplatesMixin,
    data: object,
) -> MagicMock:
    """Configure and return the mocked template API response."""
    response = MagicMock()
    response.json.return_value = data
    templates_mixin.confluence._session.get.return_value = response
    return response


def _created_page(title: str = "My Meeting Notes") -> ConfluencePage:
    """Return a page model produced by the shared page-creation path."""
    return ConfluencePage(
        id="999",
        title=title,
        url="https://example.atlassian.net/wiki/spaces/ENG/pages/999",
    )


# ---------------------------------------------------------------------------
# list_page_templates
# ---------------------------------------------------------------------------


class TestListPageTemplates:
    def test_requires_cloud(self, templates_mixin):
        """Template endpoints fail clearly on Server/Data Center."""
        templates_mixin.config = MagicMock(is_cloud=False)

        with pytest.raises(ValueError, match="only available for Confluence Cloud"):
            templates_mixin.list_page_templates()

    def test_returns_list_from_api(self, templates_mixin):
        """list_page_templates returns the raw list from the API."""
        response = _set_api_response(
            templates_mixin,
            {"results": [_TEMPLATE_SUMMARY, _TEMPLATE_SUMMARY_2]},
        )

        result = templates_mixin.list_page_templates()

        templates_mixin.confluence._session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/rest/api/template/page",
            params={"limit": 25},
        )
        response.raise_for_status.assert_called_once_with()
        assert len(result) == 2
        assert result[0]["templateId"] == "tpl-001"
        assert result[1]["name"] == "Project Charter"

    def test_passes_space_key_and_limit(self, templates_mixin):
        """list_page_templates forwards space_key and limit to the API."""
        _set_api_response(templates_mixin, {"results": []})

        templates_mixin.list_page_templates(space_key="ENG", limit=50)

        templates_mixin.confluence._session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/rest/api/template/page",
            params={"limit": 50, "spaceKey": "ENG"},
        )

    def test_cloud_oauth_uses_gateway_wiki_prefix(self, templates_mixin):
        """Cloud OAuth template calls include the API gateway product prefix."""
        templates_mixin.config = MagicMock(auth_type="oauth", is_cloud=True)
        templates_mixin.confluence.url = (
            "https://api.atlassian.com/ex/confluence/cloud-id"
        )
        _set_api_response(templates_mixin, {"results": []})

        templates_mixin.list_page_templates()

        templates_mixin.confluence._session.get.assert_called_once_with(
            "https://api.atlassian.com/ex/confluence/cloud-id/wiki/rest/api/"
            "template/page",
            params={"limit": 25},
        )

    def test_empty_result(self, templates_mixin):
        """list_page_templates handles an empty result gracefully."""
        _set_api_response(templates_mixin, {"results": []})

        result = templates_mixin.list_page_templates()

        assert result == []

    def test_api_error_raises(self, templates_mixin):
        """list_page_templates propagates non-authentication API errors."""
        response = _set_api_response(templates_mixin, {})
        response.raise_for_status.side_effect = HTTPError("network error")

        with pytest.raises(HTTPError, match="network error"):
            templates_mixin.list_page_templates()

    def test_invalid_results_raise_value_error(self, templates_mixin):
        """list_page_templates rejects malformed result collections."""
        _set_api_response(templates_mixin, {"results": "not-a-list"})

        with pytest.raises(ValueError, match="invalid results"):
            templates_mixin.list_page_templates()


# ---------------------------------------------------------------------------
# get_page_template
# ---------------------------------------------------------------------------


class TestGetPageTemplate:
    def test_returns_template_with_body(self, templates_mixin):
        """get_page_template returns the full template dict including body."""
        _set_api_response(templates_mixin, _TEMPLATE_SUMMARY)

        result = templates_mixin.get_page_template("tpl-001")

        templates_mixin.confluence._session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/rest/api/template/tpl-001",
            params=None,
        )
        assert result["templateId"] == "tpl-001"
        assert result["body"]["storage"]["value"] == "<h1>Meeting Notes</h1>"

    def test_api_error_raises(self, templates_mixin):
        """get_page_template propagates non-authentication API errors."""
        response = _set_api_response(templates_mixin, {})
        response.raise_for_status.side_effect = HTTPError("not found")

        with pytest.raises(HTTPError, match="not found"):
            templates_mixin.get_page_template("tpl-999")

    def test_template_id_is_url_encoded(self, templates_mixin):
        """get_page_template cannot escape the template endpoint path."""
        _set_api_response(templates_mixin, _TEMPLATE_SUMMARY)

        templates_mixin.get_page_template("folder/id")

        templates_mixin.confluence._session.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/rest/api/template/folder%2Fid",
            params=None,
        )


# ---------------------------------------------------------------------------
# create_page_from_template
# ---------------------------------------------------------------------------


class TestCreatePageFromTemplate:
    def test_creates_page_with_template_body(self, templates_mixin):
        """create_page_from_template uses the shared page creation path."""
        _set_api_response(templates_mixin, _TEMPLATE_SUMMARY)
        with patch(
            "mcp_atlassian.confluence.templates.PagesMixin.create_page",
            return_value=_created_page(),
        ) as create_page:
            result = templates_mixin.create_page_from_template(
                space_key="ENG",
                title="My Meeting Notes",
                template_id="tpl-001",
            )

        create_page.assert_called_once_with(
            templates_mixin,
            space_key="ENG",
            title="My Meeting Notes",
            body="<h1>Meeting Notes</h1>",
            parent_id=None,
            is_markdown=False,
            content_representation="storage",
        )
        assert result["id"] == "999"
        assert result["space_key"] == "ENG"

    def test_passes_parent_id(self, templates_mixin):
        """create_page_from_template forwards parent_id to create_page."""
        _set_api_response(templates_mixin, _TEMPLATE_SUMMARY)
        with patch(
            "mcp_atlassian.confluence.templates.PagesMixin.create_page",
            return_value=_created_page("Child Page"),
        ) as create_page:
            templates_mixin.create_page_from_template(
                space_key="ENG",
                title="Child Page",
                template_id="tpl-001",
                parent_id="777",
            )

        assert create_page.call_args.kwargs["parent_id"] == "777"

    def test_returns_url_from_created_page(self, templates_mixin):
        """create_page_from_template preserves the edition-aware page URL."""
        _set_api_response(templates_mixin, _TEMPLATE_SUMMARY)
        page = _created_page()
        with patch(
            "mcp_atlassian.confluence.templates.PagesMixin.create_page",
            return_value=page,
        ):
            result = templates_mixin.create_page_from_template(
                space_key="ENG",
                title="Test",
                template_id="tpl-001",
            )

        assert result["url"] == page.url

    def test_empty_template_body(self, templates_mixin):
        """create_page_from_template permits an explicitly empty template body."""
        _set_api_response(
            templates_mixin,
            {
                "templateId": "tpl-empty",
                "name": "Empty",
                "body": {"storage": {"value": ""}},
            },
        )
        with patch(
            "mcp_atlassian.confluence.templates.PagesMixin.create_page",
            return_value=_created_page("Empty Page"),
        ) as create_page:
            templates_mixin.create_page_from_template(
                space_key="ENG",
                title="Empty Page",
                template_id="tpl-empty",
            )

        assert create_page.call_args.kwargs["body"] == ""

    def test_missing_template_body_raises(self, templates_mixin):
        """create_page_from_template does not silently create a blank page."""
        _set_api_response(
            templates_mixin,
            {"templateId": "tpl-bad", "name": "Missing body"},
        )

        with pytest.raises(ValueError, match="has no storage-format body"):
            templates_mixin.create_page_from_template(
                space_key="ENG",
                title="Whatever",
                template_id="tpl-bad",
            )
