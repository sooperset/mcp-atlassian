"""Tests for the Jira users module."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.jira.users import UsersMixin


class TestUsersMixin:
    """Tests for the UsersMixin class."""

    @pytest.fixture
    def users_mixin(self, jira_client):
        """Create a UsersMixin instance with mocked dependencies."""
        mixin = UsersMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    def test_get_current_user_account_id_cached(self, users_mixin):
        """Test that get_current_user_account_id returns cached value if available."""
        # Set cached value
        users_mixin._current_user_account_id = "cached-account-id"

        # Call the method
        account_id = users_mixin.get_current_user_account_id()

        # Verify result
        assert account_id == "cached-account-id"
        # Verify the API wasn't called
        users_mixin.jira.myself.assert_not_called()

    def test_get_current_user_account_id_from_api(self, users_mixin):
        """Test that get_current_user_account_id calls the API if no cached value."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Call the method
        account_id = users_mixin.get_current_user_account_id()

        # Verify result
        assert account_id == "test-account-id"  # From mock_atlassian_jira fixture
        # Verify the API was called
        users_mixin.jira.myself.assert_called_once()

    def test_get_current_user_account_id_error(self, users_mixin):
        """Test that get_current_user_account_id handles errors."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None
        # Make the API call raise an exception
        users_mixin.jira.myself.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Unable to get current user account ID: API error"
        ):
            users_mixin.get_current_user_account_id()

    def test_get_account_id_already_account_id(self, users_mixin):
        """Test that _get_account_id returns the input if it looks like an account ID."""
        # Call the method with a string that looks like an account ID
        account_id = users_mixin._get_account_id("5abcdef1234567890")

        # Verify result
        assert account_id == "5abcdef1234567890"
        # Verify no lookups were performed
        users_mixin.jira.user_find_by_user_string.assert_not_called()

    def test_get_account_id_direct_lookup(self, users_mixin):
        """Test that _get_account_id uses direct lookup."""
        # Mock both methods to avoid AttributeError
        with (
            patch.object(
                users_mixin, "_lookup_user_directly", return_value="direct-account-id"
            ) as mock_direct,
            patch.object(
                users_mixin, "_lookup_user_by_permissions"
            ) as mock_permissions,
        ):
            # Call the method
            account_id = users_mixin._get_account_id("username")

            # Verify result
            assert account_id == "direct-account-id"
            # Verify direct lookup was called
            mock_direct.assert_called_once_with("username")
            # Verify permissions lookup wasn't called
            mock_permissions.assert_not_called()

    def test_get_account_id_permissions_lookup(self, users_mixin):
        """Test that _get_account_id falls back to permissions lookup."""
        # Mock direct lookup to return None
        with (
            patch.object(
                users_mixin, "_lookup_user_directly", return_value=None
            ) as mock_direct,
            patch.object(
                users_mixin,
                "_lookup_user_by_permissions",
                return_value="permissions-account-id",
            ) as mock_permissions,
        ):
            # Call the method
            account_id = users_mixin._get_account_id("username")

            # Verify result
            assert account_id == "permissions-account-id"
            # Verify both lookups were called
            mock_direct.assert_called_once_with("username")
            mock_permissions.assert_called_once_with("username")

    def test_get_account_id_not_found(self, users_mixin):
        """Test that _get_account_id raises ValueError if user not found."""
        # Mock both lookups to return None
        with (
            patch.object(users_mixin, "_lookup_user_directly", return_value=None),
            patch.object(users_mixin, "_lookup_user_by_permissions", return_value=None),
        ):
            # Call the method and verify it raises the expected exception
            with pytest.raises(
                ValueError, match="Could not find account ID for user: testuser"
            ):
                users_mixin._get_account_id("testuser")

    def test_lookup_user_directly(self, users_mixin):
        """Test _lookup_user_directly when user is found."""
        # Mock the API response
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "accountId": "direct-account-id",
                "displayName": "Test User",
                "emailAddress": "test@example.com",
            }
        ]

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result
        assert account_id == "direct-account-id"
        # Verify API call
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            query="Test User", start=0, limit=1
        )

    def test_lookup_user_directly_not_found(self, users_mixin):
        """Test _lookup_user_directly when user is not found."""
        # Mock empty API response
        users_mixin.jira.user_find_by_user_string.return_value = []

        # Call the method
        account_id = users_mixin._lookup_user_directly("nonexistent")

        # Verify result
        assert account_id is None

    def test_lookup_user_directly_error(self, users_mixin):
        """Test _lookup_user_directly when API call fails."""
        # Mock API call to raise exception
        users_mixin.jira.user_find_by_user_string.side_effect = Exception("API error")

        # Call the method
        account_id = users_mixin._lookup_user_directly("error")

        # Verify result
        assert account_id is None

    def test_lookup_user_by_permissions(self, users_mixin):
        """Test _lookup_user_by_permissions when user is found."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "users": [{"accountId": "permissions-account-id"}]
            }
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("username")

            # Verify result
            assert account_id == "permissions-account-id"
            # Verify API call
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0].endswith("/user/permission/search")
            assert mock_get.call_args[1]["params"] == {
                "query": "username",
                "permissions": "BROWSE",
            }

    def test_lookup_user_by_permissions_not_found(self, users_mixin):
        """Test _lookup_user_by_permissions when user is not found."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"users": []}
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("nonexistent")

            # Verify result
            assert account_id is None

    def test_lookup_user_by_permissions_error(self, users_mixin):
        """Test _lookup_user_by_permissions when API call fails."""
        # Mock requests.get to raise exception
        with patch("requests.get", side_effect=Exception("API error")):
            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("error")

            # Verify result
            assert account_id is None
