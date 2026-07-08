"""Unit tests for Confluence page restriction operations."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.confluence.restrictions import RestrictionsMixin
from mcp_atlassian.utils.oauth import OAuthConfig


@pytest.fixture
def restrictions_mixin(confluence_client):
    """Return a RestrictionsMixin with a mocked Confluence client."""
    with patch(
        "mcp_atlassian.confluence.restrictions.ConfluenceClient.__init__"
    ) as mock_init:
        mock_init.return_value = None
        mixin = RestrictionsMixin()
        mixin.confluence = confluence_client.confluence
        mixin.config = confluence_client.config
        mixin.preprocessor = confluence_client.preprocessor
        return mixin


@pytest.fixture
def restrictions_mixin_server_dc(confluence_client):
    """Return a RestrictionsMixin configured as Server/DC."""
    with patch(
        "mcp_atlassian.confluence.restrictions.ConfluenceClient.__init__"
    ) as mock_init:
        mock_init.return_value = None
        mixin = RestrictionsMixin()
        mixin.confluence = confluence_client.confluence
        # Use a MagicMock config so is_cloud can be set freely
        mixin.config = MagicMock()
        mixin.config.is_cloud = False
        mixin.preprocessor = confluence_client.preprocessor
        return mixin


@pytest.fixture
def restrictions_mixin_cloud_oauth(confluence_client):
    """Return a RestrictionsMixin configured for Confluence Cloud OAuth."""
    with patch(
        "mcp_atlassian.confluence.restrictions.ConfluenceClient.__init__"
    ) as mock_init:
        mock_init.return_value = None
        mixin = RestrictionsMixin()
        mixin.confluence = confluence_client.confluence
        mixin.confluence.url = "https://api.atlassian.com/ex/confluence/cloud-123"
        mixin.config = ConfluenceConfig(
            url="https://example.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=OAuthConfig(
                client_id="client-id",
                client_secret="client-secret",
                redirect_uri="http://localhost/callback",
                scope="read:confluence-content.all write:confluence-content",
                cloud_id="cloud-123",
            ),
        )
        mixin.preprocessor = confluence_client.preprocessor
        return mixin


class TestGetPageRestrictions:
    def test_get_restrictions_parses_users_and_groups(self, restrictions_mixin):
        """get_page_restrictions extracts user account IDs and group names."""
        restrictions_mixin.confluence.get.return_value = {
            "read": {
                "restrictions": {
                    "user": {
                        "results": [
                            {"accountId": "user-111"},
                            {"accountId": "user-222"},
                        ]
                    },
                    "group": {
                        "results": [
                            {"name": "developers"},
                        ]
                    },
                }
            },
            "update": {
                "restrictions": {
                    "user": {"results": [{"accountId": "user-111"}]},
                    "group": {"results": []},
                }
            },
        }

        result = restrictions_mixin.get_page_restrictions("123")

        restrictions_mixin.confluence.get.assert_called_once_with(
            "https://example.atlassian.net/wiki/rest/api/content/"
            "123/restriction/byOperation",
            absolute=True,
        )
        assert result["read"]["users"] == ["user-111", "user-222"]
        assert result["read"]["groups"] == ["developers"]
        assert result["update"]["users"] == ["user-111"]
        assert result["update"]["groups"] == []

    def test_get_restrictions_empty_response(self, restrictions_mixin):
        """get_page_restrictions handles an empty / unrestricted page gracefully."""
        restrictions_mixin.confluence.get.return_value = {}

        result = restrictions_mixin.get_page_restrictions("456")

        assert result == {
            "read": {"users": [], "groups": []},
            "update": {"users": [], "groups": []},
        }

    def test_get_restrictions_api_error(self, restrictions_mixin):
        """get_page_restrictions raises on API failure."""
        restrictions_mixin.confluence.get.side_effect = Exception("API error")

        with pytest.raises(Exception, match="Failed to get restrictions for page 789"):
            restrictions_mixin.get_page_restrictions("789")

    def test_get_restrictions_cloud_oauth_uses_gateway_wiki_path(
        self, restrictions_mixin_cloud_oauth
    ):
        """Cloud OAuth v1 calls include the /wiki prefix on api.atlassian.com."""
        restrictions_mixin_cloud_oauth.confluence.get.return_value = {}

        restrictions_mixin_cloud_oauth.get_page_restrictions("123")

        restrictions_mixin_cloud_oauth.confluence.get.assert_called_once_with(
            "https://api.atlassian.com/ex/confluence/cloud-123/wiki"
            "/rest/api/content/123/restriction/byOperation",
            absolute=True,
        )


class TestSetPageRestrictions:
    def test_set_restrictions_calls_put_with_correct_payload(self, restrictions_mixin):
        """set_page_restrictions sends a correctly structured PUT payload."""
        response = MagicMock()
        restrictions_mixin.confluence._session.put.return_value = response

        result = restrictions_mixin.set_page_restrictions(
            "123",
            read_users=["user-aaa"],
            read_groups=["viewers"],
            edit_users=["user-bbb"],
            edit_groups=["editors"],
        )

        call_args = restrictions_mixin.confluence._session.put.call_args
        assert (
            call_args.args[0]
            == "https://example.atlassian.net/wiki/rest/api/content/123/restriction"
        )
        payload = call_args.kwargs["json"]

        read_op = next(o for o in payload if o["operation"] == "read")
        update_op = next(o for o in payload if o["operation"] == "update")

        assert read_op["restrictions"]["user"][0]["accountId"] == "user-aaa"
        assert read_op["restrictions"]["group"][0]["name"] == "viewers"
        assert update_op["restrictions"]["user"][0]["accountId"] == "user-bbb"
        assert update_op["restrictions"]["group"][0]["name"] == "editors"

        assert result["read"]["users"] == ["user-aaa"]
        assert result["update"]["groups"] == ["editors"]
        response.raise_for_status.assert_called_once_with()

    def test_set_restrictions_empty_clears_all(self, restrictions_mixin):
        """set_page_restrictions with no args sends empty restriction lists."""
        restrictions_mixin.confluence._session.put.return_value = MagicMock()

        result = restrictions_mixin.set_page_restrictions("123")

        payload = restrictions_mixin.confluence._session.put.call_args.kwargs["json"]
        for op in payload:
            assert op["restrictions"]["user"] == []
            assert op["restrictions"]["group"] == []

        assert result == {
            "read": {"users": [], "groups": []},
            "update": {"users": [], "groups": []},
        }

    def test_set_restrictions_server_dc_uses_username(
        self, restrictions_mixin_server_dc
    ):
        """set_page_restrictions uses 'username' key for Server/DC instances."""
        restrictions_mixin = restrictions_mixin_server_dc
        restrictions_mixin.confluence._session.put.return_value = MagicMock()

        restrictions_mixin.set_page_restrictions("123", edit_users=["jdoe"])

        payload = restrictions_mixin.confluence._session.put.call_args.kwargs["json"]
        update_op = next(o for o in payload if o["operation"] == "update")
        user_entry = update_op["restrictions"]["user"][0]
        assert "username" in user_entry
        assert "accountId" not in user_entry
        assert user_entry["username"] == "jdoe"

    def test_set_restrictions_api_error(self, restrictions_mixin):
        """set_page_restrictions raises on PUT failure."""
        restrictions_mixin.confluence._session.put.side_effect = Exception(
            "network error"
        )

        with pytest.raises(Exception, match="Failed to set restrictions for page 999"):
            restrictions_mixin.set_page_restrictions("999", read_users=["u1"])

    def test_set_restrictions_cloud_oauth_uses_gateway_wiki_path(
        self, restrictions_mixin_cloud_oauth
    ):
        """Cloud OAuth restriction updates use the gateway v1 URL with /wiki."""
        restrictions_mixin_cloud_oauth.confluence._session.put.return_value = (
            MagicMock()
        )

        restrictions_mixin_cloud_oauth.set_page_restrictions("123")

        assert (
            restrictions_mixin_cloud_oauth.confluence._session.put.call_args.args[0]
            == "https://api.atlassian.com/ex/confluence/cloud-123/wiki"
            "/rest/api/content/123/restriction"
        )
