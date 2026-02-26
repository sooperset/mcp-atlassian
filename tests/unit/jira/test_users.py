"""Tests for the Jira users module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.users import UsersMixin, normalize_text


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

        # Mock the self.jira.myself() method
        users_mixin.jira.myself = MagicMock(
            return_value={"accountId": "test-account-id"}
        )

        # Call the method
        account_id = users_mixin.get_current_user_account_id()

        # Verify result
        assert account_id == "test-account-id"
        # Verify self.jira.myself was called
        users_mixin.jira.myself.assert_called_once()

    def test_get_current_user_account_id_data_center_timestamp_issue(self, users_mixin):
        """Test that get_current_user_account_id handles Jira Data Center with problematic timestamps."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the self.jira.myself() method
        users_mixin.jira.myself = MagicMock(
            return_value={
                "key": "jira-dc-user",
                "name": "DC User",
                "created": "9999-12-31T23:59:59.999+0000",
                "lastLogin": "0000-01-01T00:00:00.000+0000",
            }
        )

        # Call the method
        account_id = users_mixin.get_current_user_account_id()

        # Verify result - should extract key without timestamp parsing issues
        assert account_id == "jira-dc-user"
        # Verify self.jira.myself was called
        users_mixin.jira.myself.assert_called_once()

    def test_get_current_user_account_id_error(self, users_mixin):
        """Test that get_current_user_account_id handles errors."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the self.jira.myself() method to raise an exception
        users_mixin.jira.myself = MagicMock(
            side_effect=requests.RequestException("API error")
        )

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Unable to get current user account ID: API error"
        ):
            users_mixin.get_current_user_account_id()

        # Verify self.jira.myself was called
        users_mixin.jira.myself.assert_called_once()

    def test_get_current_user_account_id_jira_data_center_key(self, users_mixin):
        """Test that get_current_user_account_id falls back to 'key' for Jira Data Center."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the self.jira.myself() response with a Jira Data Center response
        users_mixin.jira.myself = MagicMock(
            return_value={"key": "jira-data-center-key", "name": "Test User"}
        )

        # Call the method
        account_id = users_mixin.get_current_user_account_id()

        # Verify result
        assert account_id == "jira-data-center-key"
        # Verify self.jira.myself was called
        users_mixin.jira.myself.assert_called_once()

    def test_get_current_user_account_id_jira_data_center_name(self, users_mixin):
        """Test that get_current_user_account_id falls back to 'name' when no 'key' or 'accountId'."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the self.jira.myself() response with a Jira Data Center response
        users_mixin.jira.myself = MagicMock(
            return_value={"name": "jira-data-center-name"}
        )

        # Call the method
        account_id = users_mixin.get_current_user_account_id()

        # Verify result
        assert account_id == "jira-data-center-name"
        # Verify self.jira.myself was called
        users_mixin.jira.myself.assert_called_once()

    def test_get_current_user_account_id_no_identifiers(self, users_mixin):
        """Test that get_current_user_account_id raises error when no identifiers are found."""
        # Ensure no cached value
        users_mixin._current_user_account_id = None

        # Mock the self.jira.myself() response with no identifiers
        users_mixin.jira.myself = MagicMock(return_value={"someField": "someValue"})

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception,
            match="Unable to get current user account ID: Could not find accountId, key, or name in user data",
        ):
            users_mixin.get_current_user_account_id()

        # Verify self.jira.myself was called
        users_mixin.jira.myself.assert_called_once()

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

        # Mock config.is_cloud to return True
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = True

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result
        assert account_id == "direct-account-id"
        # Verify API call with query parameter for Cloud
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            query="Test User", start=0, limit=1
        )

    def test_lookup_user_directly_server_dc(self, users_mixin):
        """Test _lookup_user_directly for Server/DC when user is found."""
        # Mock the API response
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "key": "server-user-key",
                "name": "server-user-name",
                "displayName": "Test User",
                "emailAddress": "test@example.com",
            }
        ]

        # Mock config.is_cloud to return False for Server/DC
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = False

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result - should now return name instead of key for Server/DC
        assert account_id == "server-user-name"
        # Verify API call with username parameter for Server/DC
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            username="Test User", start=0, limit=1
        )

    def test_lookup_user_directly_server_dc_key_fallback(self, users_mixin):
        """Test _lookup_user_directly for Server/DC falls back to key when name is not available."""
        # Mock the API response
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "key": "server-user-key",  # Only key, no name
                "displayName": "Test User",
                "emailAddress": "test@example.com",
            }
        ]

        # Mock config.is_cloud to return False for Server/DC
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = False

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result - should fallback to key when name is missing
        assert account_id == "server-user-key"
        # Verify API call with username parameter for Server/DC
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            username="Test User", start=0, limit=1
        )

    def test_lookup_user_directly_not_found(self, users_mixin):
        """Test _lookup_user_directly when user is not found."""
        # Mock empty API response
        users_mixin.jira.user_find_by_user_string.return_value = []

        # Mock config.is_cloud to return True (default case)
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = True

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

        # Mock config.is_cloud to return False for Server/DC
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = False

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result
        assert account_id == "data-center-key"
        # Verify API call
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            username="Test User", start=0, limit=1
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

        # Mock config.is_cloud to return False for Server/DC
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = False

        # Call the method
        account_id = users_mixin._lookup_user_directly("Test User")

        # Verify result
        assert account_id == "data-center-name"
        # Verify API call
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            username="Test User", start=0, limit=1
        )

    def test_lookup_user_directly_error(self, users_mixin):
        """Test _lookup_user_directly when API call fails."""
        # Mock API call to raise exception
        users_mixin.jira.user_find_by_user_string.side_effect = Exception("API error")

        # Call the method
        account_id = users_mixin._lookup_user_directly("error")

        # Verify result
        assert account_id is None

    def test_resolve_server_dc_user_params_returns_username(self, users_mixin):
        """Test _resolve_server_dc_user_params returns username dict when name is available."""
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "name": "jnovak",
                "displayName": "Jan Novák",
                "emailAddress": "jnovak@firma.cz",
            }
        ]
        result = users_mixin._resolve_server_dc_user_params("jnovak@firma.cz")
        assert result == {"username": "jnovak"}
        users_mixin.jira.user_find_by_user_string.assert_called_once_with(
            username="jnovak@firma.cz", start=0, limit=1
        )

    def test_resolve_server_dc_user_params_returns_key(self, users_mixin):
        """Test _resolve_server_dc_user_params returns key dict when only key is available."""
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "key": "JIRAUSER-12345",
                "displayName": "Jan Novák",
                "emailAddress": "jnovak@firma.cz",
            }
        ]
        result = users_mixin._resolve_server_dc_user_params("jnovak@firma.cz")
        assert result == {"key": "JIRAUSER-12345"}

    def test_resolve_server_dc_user_params_no_match(self, users_mixin):
        """Test _resolve_server_dc_user_params returns None when no user matches."""
        users_mixin.jira.user_find_by_user_string.return_value = []
        result = users_mixin._resolve_server_dc_user_params("nobody@firma.cz")
        assert result is None

    def test_resolve_server_dc_user_params_skips_empty_name(self, users_mixin):
        """Test _resolve_server_dc_user_params skips empty name and falls back to key."""
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "name": "",
                "key": "JIRAUSER-99999",
                "displayName": "Jan Novák",
                "emailAddress": "jnovak@firma.cz",
            }
        ]
        result = users_mixin._resolve_server_dc_user_params("jnovak@firma.cz")
        assert result == {"key": "JIRAUSER-99999"}

    def test_resolve_server_dc_user_params_error(self, users_mixin):
        """Test _resolve_server_dc_user_params returns None on API error."""
        users_mixin.jira.user_find_by_user_string.side_effect = Exception("API error")
        result = users_mixin._resolve_server_dc_user_params("jnovak@firma.cz")
        assert result is None

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

    def test_lookup_user_by_permissions_jira_data_center(self, users_mixin):
        """Test _lookup_user_by_permissions when both 'key' and 'name' are available (Data Center)."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "users": [
                    {
                        "key": "data-center-permissions-key",
                        "name": "data-center-permissions-name",
                    }
                ]
            }
            mock_get.return_value = mock_response

            # Mock config.is_cloud to return False for Server/DC
            users_mixin.config = MagicMock()
            users_mixin.config.is_cloud = False

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("username")

            # Verify result - should prioritize name for Server/DC
            assert account_id == "data-center-permissions-name"
            # Verify API call
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0].endswith("/user/permission/search")
            assert mock_get.call_args[1]["params"] == {
                "query": "username",
                "permissions": "BROWSE",
            }

    def test_lookup_user_by_permissions_jira_data_center_key_fallback(
        self, users_mixin
    ):
        """Test _lookup_user_by_permissions when only 'key' is available (Data Center)."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "users": [{"key": "data-center-permissions-key"}]
            }
            mock_get.return_value = mock_response

            # Mock config.is_cloud to return False for Server/DC
            users_mixin.config = MagicMock()
            users_mixin.config.is_cloud = False

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("username")

            # Verify result - should fallback to key when name is missing
            assert account_id == "data-center-permissions-key"
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

    def test_lookup_user_by_permissions_jira_data_center_name_only(self, users_mixin):
        """Test _lookup_user_by_permissions when only 'name' is available (Data Center)."""
        # Mock requests.get
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "users": [{"name": "data-center-permissions-name"}]
            }
            mock_get.return_value = mock_response

            # Mock config.is_cloud to return False for Server/DC
            users_mixin.config = MagicMock()
            users_mixin.config.is_cloud = False

            # Call the method
            account_id = users_mixin._lookup_user_by_permissions("username")

            # Verify result - should use name when that's all that's available
            assert account_id == "data-center-permissions-name"
            # Verify API call
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0].endswith("/user/permission/search")
            assert mock_get.call_args[1]["params"] == {
                "query": "username",
                "permissions": "BROWSE",
            }

    def test_determine_user_api_params_server_dc_email_resolved_to_username(
        self, users_mixin
    ):
        """Test Server/DC email is resolved via search, not passed directly as username."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = False
        users_mixin._resolve_server_dc_user_params = MagicMock(
            return_value={"username": "jnovak"}
        )

        params = users_mixin._determine_user_api_params("jnovak@firma.cz")

        assert params == {"username": "jnovak"}
        users_mixin._resolve_server_dc_user_params.assert_called_once_with(
            "jnovak@firma.cz"
        )

    def test_determine_user_api_params_server_dc_email_resolved_to_key(
        self, users_mixin
    ):
        """Test Server/DC email resolving to a key-style identifier."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = False
        users_mixin._resolve_server_dc_user_params = MagicMock(
            return_value={"key": "JIRAUSER-12345"}
        )

        params = users_mixin._determine_user_api_params("jnovak@firma.cz")

        assert params == {"key": "JIRAUSER-12345"}

    def test_determine_user_api_params_server_dc_email_lookup_fails_fallback(
        self, users_mixin
    ):
        """Test Server/DC email falls back to direct username when lookup returns None."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = False
        users_mixin._resolve_server_dc_user_params = MagicMock(return_value=None)

        params = users_mixin._determine_user_api_params("login@example.com")

        # Fallback: email used as username directly (e.g., when login IS the email)
        assert params == {"username": "login@example.com"}

    def test_determine_user_api_params_server_dc_non_email_uses_username(
        self, users_mixin
    ):
        """Test Server/DC non-email identifiers always use username= param."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = False

        # Even key-like identifiers should use username= (safe default for Server/DC)
        params = users_mixin._determine_user_api_params("JIRAUSER-12345")
        assert params == {"username": "JIRAUSER-12345"}

        params = users_mixin._determine_user_api_params("j-smith2")
        assert params == {"username": "j-smith2"}

        params = users_mixin._determine_user_api_params("jnovak")
        assert params == {"username": "jnovak"}

    def test_get_user_profile_by_identifier_server_dc_email(self, users_mixin):
        """Regression: Server/DC email lookup must search first, not pass email as username."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = False
        users_mixin._resolve_server_dc_user_params = MagicMock(
            return_value={"username": "jnovak"}
        )

        with patch(
            "src.mcp_atlassian.jira.users.JiraUser.from_api_response"
        ) as mock_from_api_response:
            mock_user_instance = MagicMock()
            mock_from_api_response.return_value = mock_user_instance
            mock_response_data = {
                "name": "jnovak",
                "displayName": "Jan Novák",
                "emailAddress": "jnovak@firma.cz",
                "active": True,
            }
            users_mixin.jira.user = MagicMock(return_value=mock_response_data)

            user = users_mixin.get_user_profile_by_identifier("jnovak@firma.cz")

            assert user == mock_user_instance
            # Must resolve email via _resolve_server_dc_user_params
            users_mixin._resolve_server_dc_user_params.assert_called_once_with(
                "jnovak@firma.cz"
            )
            # Must call user() with resolved username, NOT the raw email
            users_mixin.jira.user.assert_called_once_with(username="jnovak")

    @pytest.mark.parametrize(
        "is_cloud, id_key, identifier, api_kwarg",
        [
            pytest.param(
                True,
                "accountId",
                "5b10ac8d82e05b22cc7d4ef5",
                {"account_id": "5b10ac8d82e05b22cc7d4ef5"},
                id="cloud-account-id",
            ),
            pytest.param(
                False,
                "name",
                "server_user",
                {"username": "server_user"},
                id="server-username",
            ),
        ],
    )
    def test_get_user_profile_by_identifier_direct(
        self,
        users_mixin,
        is_cloud: bool,
        id_key: str,
        identifier: str,
        api_kwarg: dict,
    ):
        """Test get_user_profile_by_identifier with direct ID/username."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = is_cloud

        with patch(
            "src.mcp_atlassian.jira.users.JiraUser.from_api_response"
        ) as mock_from_api_response:
            mock_user_instance = MagicMock()
            mock_from_api_response.return_value = mock_user_instance
            mock_response_data = {
                id_key: identifier,
                "displayName": "Test User",
                "emailAddress": "user@example.com",
                "active": True,
            }
            users_mixin.jira.user = MagicMock(return_value=mock_response_data)
            user = users_mixin.get_user_profile_by_identifier(identifier)
            assert user == mock_user_instance
            users_mixin.jira.user.assert_called_once_with(**api_kwarg)
            mock_from_api_response.assert_called_once_with(mock_response_data)

    def test_get_user_profile_by_identifier_cloud_email(self, users_mixin):
        """Test get_user_profile_by_identifier with Cloud and email."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = True
        users_mixin._lookup_user_directly = MagicMock(
            return_value="5b10ac8d82e05b22cc7d4ef5"
        )
        with patch(
            "src.mcp_atlassian.jira.users.JiraUser.from_api_response"
        ) as mock_from_api_response:
            mock_user_instance = MagicMock()
            mock_from_api_response.return_value = mock_user_instance
            mock_response_data = {
                "accountId": "5b10ac8d82e05b22cc7d4ef5",
                "displayName": "Email User",
                "emailAddress": "email@example.com",
                "active": True,
            }
            users_mixin.jira.user = MagicMock(return_value=mock_response_data)
            user = users_mixin.get_user_profile_by_identifier("email@example.com")
            assert user == mock_user_instance
            users_mixin.jira.user.assert_called_once_with(
                account_id="5b10ac8d82e05b22cc7d4ef5"
            )
            users_mixin._lookup_user_directly.assert_called_once_with(
                "email@example.com"
            )
            mock_from_api_response.assert_called_once_with(mock_response_data)

    def test_get_user_profile_by_identifier_not_found(self, users_mixin):
        """Test get_user_profile_by_identifier when user is not found (404 or cannot resolve)."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = True
        users_mixin._lookup_user_directly = MagicMock(return_value=None)
        users_mixin._lookup_user_by_permissions = MagicMock(return_value=None)
        # Simulate the identifier cannot be resolved to an account ID
        with pytest.raises(
            ValueError, match="Could not determine how to look up user 'nonexistent'."
        ):
            users_mixin.get_user_profile_by_identifier("nonexistent")

    def test_get_user_profile_by_identifier_permission_error(self, users_mixin):
        """Test get_user_profile_by_identifier with a permission error (403)."""
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = True
        users_mixin._get_account_id = MagicMock(
            return_value="account-id-for-restricted"
        )
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 403
        http_error = requests.exceptions.HTTPError(response=mock_response)
        users_mixin.jira.user = MagicMock(side_effect=http_error)
        from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Permission denied accessing user 'restricted_user'.",
        ):
            users_mixin.get_user_profile_by_identifier("restricted_user")

    def test_get_user_profile_by_identifier_api_error(self, users_mixin):
        """Test get_user_profile_by_identifier with a generic API error."""
        # Mock config
        users_mixin.config = MagicMock(spec=JiraConfig)
        users_mixin.config.is_cloud = True
        # Mock resolution methods to succeed
        users_mixin._get_account_id = MagicMock(return_value="account-id-for-error")

        # Mock API to raise a generic exception
        users_mixin.jira.user = MagicMock(side_effect=Exception("Network Timeout"))

        # Call method and assert generic Exception
        with pytest.raises(
            Exception, match="Error processing user profile for 'error_user'"
        ):
            users_mixin.get_user_profile_by_identifier("error_user")


class TestNormalizeText:
    """Tests for the normalize_text helper function."""

    def test_normalize_text_empty_string(self):
        """Test normalize_text with empty string."""
        assert normalize_text("") == ""

    def test_normalize_text_none_returns_empty(self):
        """Test normalize_text with None returns empty string."""
        assert normalize_text(None) == ""

    def test_normalize_text_ascii(self):
        """Test normalize_text with ASCII text."""
        assert normalize_text("Test User") == "test user"
        assert normalize_text("test user") == "test user"
        assert normalize_text("TEST USER") == "test user"

    def test_normalize_text_polish_characters(self):
        """Test normalize_text with Polish characters like ł and ó."""
        # Polish "Kowalczyk" with ł should match ASCII "Kowalczyk" after normalization
        # unidecode converts ł to l, and ó to o
        normalized_polish = normalize_text("Pawełł")
        normalized_ascii = normalize_text("Pawell")
        # With unidecode, Polish characters are transliterated to ASCII
        assert normalized_polish == normalized_ascii

    def test_normalize_text_german_characters(self):
        """Test normalize_text with German characters like ß and ü."""
        # German ß should casefold to ss
        assert normalize_text("Müller") == normalize_text("müller")
        assert "ss" in normalize_text("Strauß")


class TestUnicodeLookup:
    """Tests for Unicode handling in user lookup."""

    @pytest.fixture
    def users_mixin(self, jira_client):
        """Create a UsersMixin instance with mocked dependencies."""
        mixin = UsersMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    def test_lookup_user_directly_unicode_displayname(self, users_mixin):
        """Test _lookup_user_directly matches Unicode display names."""
        # Mock the API response with a Polish name
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "accountId": "unicode-account-id",
                "displayName": "Paweł Kowalczyk",
                "emailAddress": "pawel@example.com",
            }
        ]

        # Mock config.is_cloud to return True
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = True

        # Searching with the exact Unicode name should match
        account_id = users_mixin._lookup_user_directly("Paweł Kowalczyk")
        assert account_id == "unicode-account-id"

    def test_lookup_user_directly_case_insensitive_unicode(self, users_mixin):
        """Test _lookup_user_directly is case-insensitive for Unicode names."""
        # Mock the API response with a Polish name
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "accountId": "unicode-account-id",
                "displayName": "Paweł Kowalczyk",
                "emailAddress": "pawel@example.com",
            }
        ]

        # Mock config.is_cloud to return True
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = True

        # Searching with different case should still match
        account_id = users_mixin._lookup_user_directly("paweł kowalczyk")
        assert account_id == "unicode-account-id"

    def test_lookup_user_directly_ascii_still_works(self, users_mixin):
        """Test _lookup_user_directly still works for ASCII names."""
        # Mock the API response with an ASCII name
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "accountId": "ascii-account-id",
                "displayName": "John Smith",
                "emailAddress": "john@example.com",
            }
        ]

        # Mock config.is_cloud to return True
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = True

        # Searching with the ASCII name should match
        account_id = users_mixin._lookup_user_directly("John Smith")
        assert account_id == "ascii-account-id"

        # Case insensitive should also work
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "accountId": "ascii-account-id",
                "displayName": "John Smith",
                "emailAddress": "john@example.com",
            }
        ]
        account_id = users_mixin._lookup_user_directly("john smith")
        assert account_id == "ascii-account-id"

    def test_lookup_user_directly_email_with_unicode(self, users_mixin):
        """Test _lookup_user_directly matches email addresses correctly."""
        # Mock the API response
        users_mixin.jira.user_find_by_user_string.return_value = [
            {
                "accountId": "email-account-id",
                "displayName": "Test User",
                "emailAddress": "tëst@example.com",
            }
        ]

        # Mock config.is_cloud to return True
        users_mixin.config = MagicMock()
        users_mixin.config.is_cloud = True

        # Searching with the email should match (case insensitive)
        account_id = users_mixin._lookup_user_directly("TËST@EXAMPLE.COM")
        assert account_id == "email-account-id"
