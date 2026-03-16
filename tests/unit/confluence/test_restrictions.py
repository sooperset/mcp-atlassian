"""Unit tests for Confluence page restriction operations."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.restrictions import RestrictionsMixin


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


class TestGetPageRestrictions:
    def test_get_restrictions_parses_users_and_groups(self, restrictions_mixin):
        """get_page_restrictions extracts user account IDs and group names."""
        restrictions_mixin.confluence.get_all_restrictions_for_content.return_value = {
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

        assert result["read"]["users"] == ["user-111", "user-222"]
        assert result["read"]["groups"] == ["developers"]
        assert result["update"]["users"] == ["user-111"]
        assert result["update"]["groups"] == []

    def test_get_restrictions_empty_response(self, restrictions_mixin):
        """get_page_restrictions handles an empty / unrestricted page gracefully."""
        restrictions_mixin.confluence.get_all_restrictions_for_content.return_value = {}

        result = restrictions_mixin.get_page_restrictions("456")

        assert result == {
            "read": {"users": [], "groups": []},
            "update": {"users": [], "groups": []},
        }

    def test_get_restrictions_api_error(self, restrictions_mixin):
        """get_page_restrictions raises on API failure."""
        restrictions_mixin.confluence.get_all_restrictions_for_content.side_effect = (
            Exception("API error")
        )

        with pytest.raises(Exception, match="Failed to get restrictions for page 789"):
            restrictions_mixin.get_page_restrictions("789")


class TestSetPageRestrictions:
    def test_set_restrictions_calls_put_with_correct_payload(self, restrictions_mixin):
        """set_page_restrictions sends a correctly structured PUT payload."""
        restrictions_mixin.confluence.put = MagicMock()

        result = restrictions_mixin.set_page_restrictions(
            "123",
            read_users=["user-aaa"],
            read_groups=["viewers"],
            edit_users=["user-bbb"],
            edit_groups=["editors"],
        )

        call_args = restrictions_mixin.confluence.put.call_args
        assert call_args[0][0] == "rest/api/content/123/restriction"
        # data is serialised as a JSON string
        import json as _json

        payload = _json.loads(call_args[1]["data"])

        read_op = next(o for o in payload if o["operation"] == "read")
        update_op = next(o for o in payload if o["operation"] == "update")

        assert read_op["restrictions"]["user"][0]["accountId"] == "user-aaa"
        assert read_op["restrictions"]["group"][0]["name"] == "viewers"
        assert update_op["restrictions"]["user"][0]["accountId"] == "user-bbb"
        assert update_op["restrictions"]["group"][0]["name"] == "editors"

        assert result["read"]["users"] == ["user-aaa"]
        assert result["update"]["groups"] == ["editors"]

    def test_set_restrictions_empty_clears_all(self, restrictions_mixin):
        """set_page_restrictions with no args sends empty restriction lists."""
        import json as _json

        restrictions_mixin.confluence.put = MagicMock()

        result = restrictions_mixin.set_page_restrictions("123")

        payload = _json.loads(restrictions_mixin.confluence.put.call_args[1]["data"])
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
        import json as _json

        restrictions_mixin = restrictions_mixin_server_dc
        restrictions_mixin.confluence.put = MagicMock()

        restrictions_mixin.set_page_restrictions("123", edit_users=["jdoe"])

        payload = _json.loads(restrictions_mixin.confluence.put.call_args[1]["data"])
        update_op = next(o for o in payload if o["operation"] == "update")
        user_entry = update_op["restrictions"]["user"][0]
        assert "username" in user_entry
        assert "accountId" not in user_entry
        assert user_entry["username"] == "jdoe"

    def test_set_restrictions_api_error(self, restrictions_mixin):
        """set_page_restrictions raises on PUT failure."""
        restrictions_mixin.confluence.put = MagicMock(
            side_effect=Exception("network error")
        )

        with pytest.raises(Exception, match="Failed to set restrictions for page 999"):
            restrictions_mixin.set_page_restrictions("999", read_users=["u1"])
