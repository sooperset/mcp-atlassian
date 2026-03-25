"""Unit tests for Confluence template operations."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.templates import TemplatesMixin


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


# ---------------------------------------------------------------------------
# list_page_templates
# ---------------------------------------------------------------------------


class TestListPageTemplates:
    def test_returns_list_from_api(self, templates_mixin):
        """list_page_templates returns the raw list from the API."""
        templates_mixin.confluence.get_content_templates.return_value = [
            _TEMPLATE_SUMMARY,
            _TEMPLATE_SUMMARY_2,
        ]

        result = templates_mixin.list_page_templates()

        templates_mixin.confluence.get_content_templates.assert_called_once_with(
            space=None,
            limit=25,
        )
        assert len(result) == 2
        assert result[0]["templateId"] == "tpl-001"
        assert result[1]["name"] == "Project Charter"

    def test_passes_space_key_and_limit(self, templates_mixin):
        """list_page_templates forwards space_key and limit to the API."""
        templates_mixin.confluence.get_content_templates.return_value = []

        templates_mixin.list_page_templates(space_key="ENG", limit=50)

        templates_mixin.confluence.get_content_templates.assert_called_once_with(
            space="ENG",
            limit=50,
        )

    def test_empty_result(self, templates_mixin):
        """list_page_templates handles an empty result gracefully."""
        templates_mixin.confluence.get_content_templates.return_value = []

        result = templates_mixin.list_page_templates()

        assert result == []

    def test_api_error_raises(self, templates_mixin):
        """list_page_templates wraps API errors with a descriptive message."""
        templates_mixin.confluence.get_content_templates.side_effect = Exception(
            "network error"
        )

        with pytest.raises(Exception, match="Failed to list page templates"):
            templates_mixin.list_page_templates()


# ---------------------------------------------------------------------------
# get_page_template
# ---------------------------------------------------------------------------


class TestGetPageTemplate:
    def test_returns_template_with_body(self, templates_mixin):
        """get_page_template returns the full template dict including body."""
        templates_mixin.confluence.get_content_template.return_value = _TEMPLATE_SUMMARY

        result = templates_mixin.get_page_template("tpl-001")

        templates_mixin.confluence.get_content_template.assert_called_once_with(
            "tpl-001"
        )
        assert result["templateId"] == "tpl-001"
        assert result["body"]["storage"]["value"] == "<h1>Meeting Notes</h1>"

    def test_api_error_raises(self, templates_mixin):
        """get_page_template wraps API errors with a descriptive message."""
        templates_mixin.confluence.get_content_template.side_effect = Exception(
            "not found"
        )

        with pytest.raises(Exception, match="Failed to get template tpl-999"):
            templates_mixin.get_page_template("tpl-999")


# ---------------------------------------------------------------------------
# create_page_from_template
# ---------------------------------------------------------------------------


class TestCreatePageFromTemplate:
    def test_creates_page_with_template_body(self, templates_mixin):
        """create_page_from_template fetches template then calls create_page."""
        templates_mixin.confluence.get_content_template.return_value = _TEMPLATE_SUMMARY
        templates_mixin.confluence.create_page = MagicMock(
            return_value={"id": "999", "title": "My Meeting Notes"}
        )

        result = templates_mixin.create_page_from_template(
            space_key="ENG",
            title="My Meeting Notes",
            template_id="tpl-001",
        )

        templates_mixin.confluence.get_content_template.assert_called_once_with(
            "tpl-001"
        )
        templates_mixin.confluence.create_page.assert_called_once_with(
            space="ENG",
            title="My Meeting Notes",
            body="<h1>Meeting Notes</h1>",
            parent_id=None,
            representation="storage",
        )
        assert result["id"] == "999"
        assert result["space_key"] == "ENG"

    def test_passes_parent_id(self, templates_mixin):
        """create_page_from_template forwards parent_id to create_page."""
        templates_mixin.confluence.get_content_template.return_value = _TEMPLATE_SUMMARY
        templates_mixin.confluence.create_page = MagicMock(
            return_value={"id": "888", "title": "Child Page"}
        )

        templates_mixin.create_page_from_template(
            space_key="ENG",
            title="Child Page",
            template_id="tpl-001",
            parent_id="777",
        )

        call_kwargs = templates_mixin.confluence.create_page.call_args[1]
        assert call_kwargs["parent_id"] == "777"

    def test_url_built_from_config(self, templates_mixin):
        """create_page_from_template constructs the page URL from config.url."""
        templates_mixin.confluence.get_content_template.return_value = _TEMPLATE_SUMMARY
        templates_mixin.confluence.create_page = MagicMock(
            return_value={"id": "123", "title": "Test"}
        )

        result = templates_mixin.create_page_from_template(
            space_key="ENG",
            title="Test",
            template_id="tpl-001",
        )

        assert "123" in result["url"]
        assert "ENG" in result["url"]

    def test_empty_template_body(self, templates_mixin):
        """create_page_from_template handles a template with no body gracefully."""
        templates_mixin.confluence.get_content_template.return_value = {
            "templateId": "tpl-empty",
            "name": "Empty",
            "body": {},
        }
        templates_mixin.confluence.create_page = MagicMock(
            return_value={"id": "500", "title": "Empty Page"}
        )

        templates_mixin.create_page_from_template(
            space_key="ENG",
            title="Empty Page",
            template_id="tpl-empty",
        )

        call_kwargs = templates_mixin.confluence.create_page.call_args[1]
        assert call_kwargs["body"] == ""

    def test_api_error_raises(self, templates_mixin):
        """create_page_from_template raises when template fetch fails."""
        templates_mixin.confluence.get_content_template.side_effect = Exception(
            "not found"
        )

        with pytest.raises(
            Exception, match="Failed to create page from template tpl-bad"
        ):
            templates_mixin.create_page_from_template(
                space_key="ENG",
                title="Whatever",
                template_id="tpl-bad",
            )
