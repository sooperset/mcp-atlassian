"""Tests for the Jira users module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

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

        # Mock the requests.get method to bypass atlassian-python-api
        with patch("requests.get") as mock_get:
            # Configure the mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"accountId": "test-account-id"}'
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin.get_current_user_account_id()

            # Verify result
            assert account_id == "test-account-id"
            # Verify requests.get was called with the correct URL
            mock_get.assert_called_once()
            assert "/rest/api/2/myself" in mock_get.call_args[0][0]

    def test_get_current_user_account_id_data_center_timestamp_issue(self, users_mixin):
        """Test that get_current_user_account_id handles Jira Data Center with problematic timestamps."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the requests.get method to bypass atlassian-python-api
        with patch("requests.get") as mock_get:
            # Configure the mock response with a JSON that would cause timestamp issues
            # but our solution should properly handle it by using direct JSON parsing
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = (
                '{"key": "jira-dc-user", "name": "DC User", '
                '"created": "9999-12-31T23:59:59.999+0000", '  # Problematic timestamp
                '"lastLogin": "0000-01-01T00:00:00.000+0000"}'  # Another problematic timestamp
            )
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin.get_current_user_account_id()

            # Verify result - should extract key without timestamp parsing issues
            assert account_id == "jira-dc-user"
            # Verify requests.get was called
            mock_get.assert_called_once()

    def test_get_current_user_account_id_error(self, users_mixin):
        """Test that get_current_user_account_id handles errors."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the requests.get method to raise an exception
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("API error")

            # Call the method and verify it raises the expected exception
            with pytest.raises(
                Exception, match="Unable to get current user account ID: API error"
            ):
                users_mixin.get_current_user_account_id()

            # Verify requests.get was called
            mock_get.assert_called_once()

    def test_get_current_user_account_id_jira_data_center_key(self, users_mixin):
        """Test that get_current_user_account_id falls back to 'key' for Jira Data Center."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the requests.get response with a Jira Data Center response
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"key": "jira-data-center-key", "name": "Test User"}'
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin.get_current_user_account_id()

            # Verify result
            assert account_id == "jira-data-center-key"
            # Verify requests.get was called
            mock_get.assert_called_once()

    def test_get_current_user_account_id_jira_data_center_name(self, users_mixin):
        """Test that get_current_user_account_id falls back to 'name' when no 'key' or 'accountId'."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the requests.get response with a Jira Data Center response
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"name": "jira-data-center-name"}'
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin.get_current_user_account_id()

            # Verify result
            assert account_id == "jira-data-center-name"
            # Verify requests.get was called
            mock_get.assert_called_once()

    def test_get_current_user_account_id_no_identifiers(self, users_mixin):
        """Test that get_current_user_account_id raises error when no identifiers are found."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the requests.get response with no identifiers
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"someField": "someValue"}'
            mock_get.return_value = mock_response

            # Call the method and verify it raises the expected exception
            with pytest.raises(
                Exception,
                match="Unable to get current user account ID: Could not find accountId, key, or name in user data",
            ):
                users_mixin.get_current_user_account_id()

            # Verify requests.get was called
            mock_get.assert_called_once()

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

    def test_lookup_user_directly_jira_data_center_key(self, users_mixin):
        """Test _lookup_user_directly when only 'key' is available (Data Center)."""
        # Mock the API response for Jira Data Center (has key but no accountId)
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "key": "data-center-key",
                "displayName": "Test User",
                "emailAddress": "test@example.com",
            }
        ]

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result
        assert account_id == "data-center-key"
        # Verify API call
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            query="Test User", start=0, limit=1
        )

    def test_lookup_user_directly_jira_data_center_name(self, users_mixin):
        """Test _lookup_user_directly when only 'name' is available (Data Center)."""
        # Mock the API response for Jira Data Center (has name but no accountId or key)
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "name": "data-center-name",
                "displayName": "Test User",
                "emailAddress": "test@example.com",
            }
        ]

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result
        assert account_id == "data-center-name"
        # Verify API call
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            query="Test User", start=0, limit=1
        )

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

    def test_lookup_user_by_permissions_jira_data_center_key(self, users_mixin):
        """Test _lookup_user_by_permissions when only 'key' is available (Data Center)."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "users": [{"key": "data-center-permissions-key"}]
            }
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("username")

            # Verify result
            assert account_id == "data-center-permissions-key"
            # Verify API call
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0].endswith("/user/permission/search")
            assert mock_get.call_args[1]["params"] == {
                "query": "username",
                "permissions": "BROWSE",
            }

    def test_lookup_user_by_permissions_jira_data_center_name(self, users_mixin):
        """Test _lookup_user_by_permissions when only 'name' is available (Data Center)."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "users": [{"name": "data-center-permissions-name"}]
            }
            mock_get.return_value = mock_response

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("username")

            # Verify result
            assert account_id == "data-center-permissions-name"
            # Verify API call
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0].endswith("/user/permission/search")
            assert mock_get.call_args[1]["params"] == {
                "query": "username",
                "permissions": "BROWSE",
            }

    def test_lookup_user_by_permissions_error(self, users_mixin):
        """Test _lookup_user_by_permissions when API call fails."""
        # Mock requests.get to raise exception
        with patch("requests.get", side_effect=Exception("API error")):
            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("error")

            # Verify result
            assert account_id is None
