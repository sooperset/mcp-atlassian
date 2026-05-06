"""Tests for the Confluence Permissions mixin."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.confluence.permissions import PermissionsMixin


class TestPermissionsMixin:
    """Tests for the PermissionsMixin class."""

    @pytest.fixture
    def permissions_mixin(self):
        """Create a PermissionsMixin instance with mocked dependencies."""
        mixin = MagicMock(spec=PermissionsMixin)
        mixin.confluence = MagicMock()
        mixin.confluence.url = "https://company.atlassian.net/wiki"

        mixin.check_content_permissions = (
            lambda *args, **kwargs: PermissionsMixin.check_content_permissions(
                mixin, *args, **kwargs
            )
        )
        mixin.get_space_permissions = (
            lambda *args, **kwargs: PermissionsMixin.get_space_permissions(
                mixin, *args, **kwargs
            )
        )
        return mixin

    # ---- check_content_permissions ----

    def test_check_content_permissions_has_permission(self, permissions_mixin):
        """Test successful permission check returning hasPermission=True."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"hasPermission": True}
        mock_response.raise_for_status = MagicMock()
        permissions_mixin.confluence._session.post.return_value = mock_response

        result = permissions_mixin.check_content_permissions(
            content_id="123456",
            user_identifier="accountid123",
            operation="read",
        )

        assert result == {"hasPermission": True}
        permissions_mixin.confluence._session.post.assert_called_once_with(
            "https://company.atlassian.net/wiki/rest/api/content/123456/permission/check",
            json={
                "operation": {"operation": "read", "targetType": "page"},
                "subject": {"type": "user", "identifier": "accountid123"},
            },
        )

    def test_check_content_permissions_no_permission(self, permissions_mixin):
        """Test permission check returning hasPermission=False."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"hasPermission": False}
        mock_response.raise_for_status = MagicMock()
        permissions_mixin.confluence._session.post.return_value = mock_response

        result = permissions_mixin.check_content_permissions(
            content_id="999",
            user_identifier="accountid456",
            operation="delete",
        )

        assert result == {"hasPermission": False}

    def test_check_content_permissions_custom_target_and_subject(
        self, permissions_mixin
    ):
        """Test permission check with explicit target_type and subject_type."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"hasPermission": True}
        mock_response.raise_for_status = MagicMock()
        permissions_mixin.confluence._session.post.return_value = mock_response

        permissions_mixin.check_content_permissions(
            content_id="42",
            user_identifier="dev-team",
            operation="read",
            target_type="blogpost",
            subject_type="group",
        )

        _, call_kwargs = permissions_mixin.confluence._session.post.call_args
        body = call_kwargs["json"]
        assert body["operation"]["targetType"] == "blogpost"
        assert body["subject"]["type"] == "group"
        assert body["subject"]["identifier"] == "dev-team"

    def test_check_content_permissions_propagates_401(self, permissions_mixin):
        """Test that 401 HTTPError is re-raised."""
        http_err = HTTPError(response=MagicMock(status_code=401))
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_err
        permissions_mixin.confluence._session.post.return_value = mock_response

        with pytest.raises(HTTPError):
            permissions_mixin.check_content_permissions(
                content_id="1",
                user_identifier="u",
                operation="read",
            )

    def test_check_content_permissions_raises_value_error_on_http_failure(
        self, permissions_mixin
    ):
        """Test that non-auth HTTP errors are wrapped in ValueError."""
        http_err = HTTPError(response=MagicMock(status_code=500))
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_err
        permissions_mixin.confluence._session.post.return_value = mock_response

        with pytest.raises(ValueError, match="Failed to check permissions"):
            permissions_mixin.check_content_permissions(
                content_id="1",
                user_identifier="u",
                operation="read",
            )

    # ---- get_space_permissions ----

    def test_get_space_permissions_returns_results(self, permissions_mixin):
        """Test successful retrieval of space permission assignments."""
        mock_payload = {
            "results": [
                {
                    "id": "perm-1",
                    "principal": {"type": "user", "id": "accountid123"},
                    "operation": {"key": "read", "target": "space"},
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = mock_payload
        mock_response.raise_for_status = MagicMock()
        permissions_mixin.confluence._session.get.return_value = mock_response

        result = permissions_mixin.get_space_permissions(space_id="98304")

        assert result == mock_payload
        permissions_mixin.confluence._session.get.assert_called_once_with(
            "https://company.atlassian.net/wiki/api/v2/spaces/98304/permissions",
            params={"limit": 25},
        )

    def test_get_space_permissions_custom_limit(self, permissions_mixin):
        """Test that a custom limit is forwarded to the API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        permissions_mixin.confluence._session.get.return_value = mock_response

        permissions_mixin.get_space_permissions(space_id="1", limit=50)

        _, call_kwargs = permissions_mixin.confluence._session.get.call_args
        assert call_kwargs["params"] == {"limit": 50}

    def test_get_space_permissions_propagates_403(self, permissions_mixin):
        """Test that 403 HTTPError is re-raised."""
        http_err = HTTPError(response=MagicMock(status_code=403))
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_err
        permissions_mixin.confluence._session.get.return_value = mock_response

        with pytest.raises(HTTPError):
            permissions_mixin.get_space_permissions(space_id="1")

    def test_get_space_permissions_raises_value_error_on_http_failure(
        self, permissions_mixin
    ):
        """Test that non-auth HTTP errors are wrapped in ValueError."""
        http_err = HTTPError(response=MagicMock(status_code=404))
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_err
        permissions_mixin.confluence._session.get.return_value = mock_response

        with pytest.raises(ValueError, match="Failed to get permissions"):
            permissions_mixin.get_space_permissions(space_id="999")
