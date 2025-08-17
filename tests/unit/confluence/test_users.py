"""Unit tests for the Confluence users module."""

from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.confluence.users import UsersMixin
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError


class TestUsersMixin:
    """Tests for the UsersMixin class."""

    @pytest.fixture
    def users_mixin(self, confluence_client):
        """Create a UsersMixin instance for testing."""
        # UsersMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.users.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = UsersMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            return mixin

    # Mock user data for different scenarios
    @pytest.fixture
    def mock_user_data_cloud(self):
        """Mock user data for Confluence Cloud."""
        return {
            "accountId": "5b10ac8d82e05b22cc7d4ef5",
            "accountType": "atlassian",
            "email": "user@example.com",
            "publicName": "Test User",
            "displayName": "Test User",
            "profilePicture": {
                "path": "/wiki/aa-avatar/5b10ac8d82e05b22cc7d4ef5",
                "width": 48,
                "height": 48,
                "isDefault": False,
            },
            "isExternalCollaborator": False,
            "accountStatus": "active",
        }

    @pytest.fixture
    def mock_user_data_server(self):
        """Mock user data for Confluence Server/DC."""
        return {
            "username": "testuser",
            "userKey": "testuser-key-12345",
            "displayName": "Test User",
            "fullName": "Test User Full Name",
            "email": "testuser@example.com",
            "status": "active",
        }

    @pytest.fixture
    def mock_user_data_with_status(self):
        """Mock user data with status expansion."""
        return {
            "accountId": "5b10ac8d82e05b22cc7d4ef5",
            "accountType": "atlassian",
            "email": "user@example.com",
            "publicName": "Test User",
            "displayName": "Test User",
            "accountStatus": "active",
            "status": "Active",  # Expanded status field
        }

    @pytest.fixture
    def mock_current_user_data(self):
        """Mock current user data for get_current_user_info."""
        return {
            "accountId": "5b10ac8d82e05b22cc7d4ef5",
            "type": "known",
            "accountType": "atlassian",
            "email": "current@example.com",
            "publicName": "Current User",
            "displayName": "Current User",
            "profilePicture": {
                "path": "/wiki/aa-avatar/5b10ac8d82e05b22cc7d4ef5",
                "width": 48,
                "height": 48,
                "isDefault": False,
            },
            "isExternalCollaborator": False,
            "isGuest": False,
            "locale": "en_US",
            "accountStatus": "active",
        }

    def test_get_user_details_by_accountid_success(
        self, users_mixin, mock_user_data_cloud
    ):
        """Test successfully getting user details by account ID."""
        # Arrange
        account_id = "5b10ac8d82e05b22cc7d4ef5"
        users_mixin.confluence.get_user_details_by_accountid.return_value = (
            mock_user_data_cloud
        )

        # Act
        result = users_mixin.get_user_details_by_accountid(account_id)

        # Assert
        users_mixin.confluence.get_user_details_by_accountid.assert_called_once_with(
            account_id, None
        )
        assert result == mock_user_data_cloud
        assert result["accountId"] == account_id
        assert result["displayName"] == "Test User"

    def test_get_user_details_by_accountid_with_expand(
        self, users_mixin, mock_user_data_with_status
    ):
        """Test getting user details by account ID with status expansion."""
        # Arrange
        account_id = "5b10ac8d82e05b22cc7d4ef5"
        expand = "status"
        users_mixin.confluence.get_user_details_by_accountid.return_value = (
            mock_user_data_with_status
        )

        # Act
        result = users_mixin.get_user_details_by_accountid(account_id, expand=expand)

        # Assert
        users_mixin.confluence.get_user_details_by_accountid.assert_called_once_with(
            account_id, expand
        )
        assert result == mock_user_data_with_status
        assert result["status"] == "Active"
        assert result["accountStatus"] == "active"

    def test_get_user_details_by_accountid_invalid_account_id(self, users_mixin):
        """Test getting user details with invalid account ID."""
        # Arrange
        invalid_account_id = "invalid-account-id"
        users_mixin.confluence.get_user_details_by_accountid.side_effect = Exception(
            "User not found"
        )

        # Act/Assert
        with pytest.raises(Exception, match="User not found"):
            users_mixin.get_user_details_by_accountid(invalid_account_id)

    def test_get_user_details_by_username_success(
        self, users_mixin, mock_user_data_server
    ):
        """Test successfully getting user details by username."""
        # Arrange
        username = "testuser"
        users_mixin.confluence.get_user_details_by_username.return_value = (
            mock_user_data_server
        )

        # Act
        result = users_mixin.get_user_details_by_username(username)

        # Assert
        users_mixin.confluence.get_user_details_by_username.assert_called_once_with(
            username, None
        )
        assert result == mock_user_data_server
        assert result["username"] == username
        assert result["displayName"] == "Test User"

    def test_get_user_details_by_username_with_expand(
        self, users_mixin, mock_user_data_server
    ):
        """Test getting user details by username with status expansion."""
        # Arrange
        username = "testuser"
        expand = "status"
        mock_data_with_status = mock_user_data_server.copy()
        mock_data_with_status["status"] = "Active"
        users_mixin.confluence.get_user_details_by_username.return_value = (
            mock_data_with_status
        )

        # Act
        result = users_mixin.get_user_details_by_username(username, expand=expand)

        # Assert
        users_mixin.confluence.get_user_details_by_username.assert_called_once_with(
            username, expand
        )
        assert result == mock_data_with_status
        assert result["status"] == "Active"

    def test_get_user_details_by_username_invalid_username(self, users_mixin):
        """Test getting user details with invalid username."""
        # Arrange
        invalid_username = "nonexistent-user"
        users_mixin.confluence.get_user_details_by_username.side_effect = Exception(
            "User not found"
        )

        # Act/Assert
        with pytest.raises(Exception, match="User not found"):
            users_mixin.get_user_details_by_username(invalid_username)

    def test_get_user_details_by_username_server_dc_pattern(
        self, users_mixin, mock_user_data_server
    ):
        """Test that username lookup follows Server/DC patterns."""
        # Arrange
        username = "dc.user@example.com"  # Email-like username common in DC
        users_mixin.confluence.get_user_details_by_username.return_value = (
            mock_user_data_server
        )

        # Act
        result = users_mixin.get_user_details_by_username(username)

        # Assert
        users_mixin.confluence.get_user_details_by_username.assert_called_once_with(
            username, None
        )
        assert result == mock_user_data_server

    def test_get_current_user_info_success(self, users_mixin, mock_current_user_data):
        """Test successfully getting current user info."""
        # Arrange
        users_mixin.confluence.get.return_value = mock_current_user_data

        # Act
        result = users_mixin.get_current_user_info()

        # Assert
        users_mixin.confluence.get.assert_called_once_with("rest/api/user/current")
        assert result == mock_current_user_data
        assert result["accountId"] == "5b10ac8d82e05b22cc7d4ef5"
        assert result["displayName"] == "Current User"

    def test_get_current_user_info_returns_non_dict(self, users_mixin):
        """Test get_current_user_info when API returns non-dict data."""
        # Arrange
        users_mixin.confluence.get.return_value = "Invalid response"

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed: Did not receive valid JSON user data",
        ):
            users_mixin.get_current_user_info()

        users_mixin.confluence.get.assert_called_once_with("rest/api/user/current")

    def test_get_current_user_info_returns_none(self, users_mixin):
        """Test get_current_user_info when API returns None."""
        # Arrange
        users_mixin.confluence.get.return_value = None

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed: Did not receive valid JSON user data",
        ):
            users_mixin.get_current_user_info()

    def test_get_current_user_info_http_error_401(self, users_mixin):
        """Test get_current_user_info with 401 authentication error."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = HTTPError(response=mock_response)
        users_mixin.confluence.get.side_effect = http_error

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed: 401 from /rest/api/user/current",
        ):
            users_mixin.get_current_user_info()

    def test_get_current_user_info_http_error_403(self, users_mixin):
        """Test get_current_user_info with 403 forbidden error."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 403
        http_error = HTTPError(response=mock_response)
        users_mixin.confluence.get.side_effect = http_error

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed: 403 from /rest/api/user/current",
        ):
            users_mixin.get_current_user_info()

    def test_get_current_user_info_http_error_other(self, users_mixin):
        """Test get_current_user_info with other HTTP error codes."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = HTTPError(response=mock_response)
        users_mixin.confluence.get.side_effect = http_error

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed with HTTPError",
        ):
            users_mixin.get_current_user_info()

    def test_get_current_user_info_http_error_no_response(self, users_mixin):
        """Test get_current_user_info with HTTPError but no response object."""
        # Arrange
        http_error = HTTPError()
        http_error.response = None
        users_mixin.confluence.get.side_effect = http_error

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed with HTTPError",
        ):
            users_mixin.get_current_user_info()

    def test_get_current_user_info_generic_exception(self, users_mixin):
        """Test get_current_user_info with generic exception."""
        # Arrange
        users_mixin.confluence.get.side_effect = ConnectionError("Network error")

        # Act/Assert
        with pytest.raises(
            MCPAtlassianAuthenticationError,
            match="Confluence token validation failed: Network error",
        ):
            users_mixin.get_current_user_info()

    @pytest.mark.parametrize(
        "expand_param",
        [
            None,
            "status",
            "",  # Empty string
        ],
    )
    def test_get_user_details_by_accountid_expand_parameter_handling(
        self, users_mixin, mock_user_data_cloud, expand_param
    ):
        """Test that expand parameter is properly handled for account ID lookup."""
        # Arrange
        account_id = "5b10ac8d82e05b22cc7d4ef5"
        expected_data = mock_user_data_cloud.copy()
        if expand_param == "status":
            expected_data["status"] = "Active"

        users_mixin.confluence.get_user_details_by_accountid.return_value = (
            expected_data
        )

        # Act
        result = users_mixin.get_user_details_by_accountid(account_id, expand_param)

        # Assert
        users_mixin.confluence.get_user_details_by_accountid.assert_called_once_with(
            account_id, expand_param
        )
        assert result == expected_data

    @pytest.mark.parametrize(
        "expand_param",
        [
            None,
            "status",
            "",  # Empty string
        ],
    )
    def test_get_user_details_by_username_expand_parameter_handling(
        self, users_mixin, mock_user_data_server, expand_param
    ):
        """Test that expand parameter is properly handled for username lookup."""
        # Arrange
        username = "testuser"
        expected_data = mock_user_data_server.copy()
        if expand_param == "status":
            expected_data["status"] = "Active"

        users_mixin.confluence.get_user_details_by_username.return_value = expected_data

        # Act
        result = users_mixin.get_user_details_by_username(username, expand_param)

        # Assert
        users_mixin.confluence.get_user_details_by_username.assert_called_once_with(
            username, expand_param
        )
        assert result == expected_data

    def test_users_mixin_inheritance(self, users_mixin):
        """Test that UsersMixin properly inherits from ConfluenceClient."""
        # Verify that UsersMixin is indeed a ConfluenceClient
        from mcp_atlassian.confluence.client import ConfluenceClient

        assert isinstance(users_mixin, ConfluenceClient)

        # Verify it has the expected attributes from ConfluenceClient
        assert hasattr(users_mixin, "confluence")
        assert hasattr(users_mixin, "config")

    def test_users_mixin_has_required_methods(self):
        """Test that UsersMixin has all required methods."""
        # Verify the mixin has the expected methods
        assert hasattr(UsersMixin, "get_user_details_by_accountid")
        assert hasattr(UsersMixin, "get_user_details_by_username")
        assert hasattr(UsersMixin, "get_current_user_info")

        # Verify method signatures
        import inspect

        # Check get_user_details_by_accountid signature
        sig = inspect.signature(UsersMixin.get_user_details_by_accountid)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "account_id" in params
        assert "expand" in params
        assert sig.parameters["expand"].default is None

        # Check get_user_details_by_username signature
        sig = inspect.signature(UsersMixin.get_user_details_by_username)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "username" in params
        assert "expand" in params
        assert sig.parameters["expand"].default is None

        # Check get_current_user_info signature
        sig = inspect.signature(UsersMixin.get_current_user_info)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert len(params) == 1  # Only self parameter

    def test_user_permission_scenarios(self, users_mixin):
        """Test various permission error scenarios."""
        # Test 401 Unauthorized
        mock_response_401 = MagicMock()
        mock_response_401.status_code = 401
        http_error_401 = HTTPError(response=mock_response_401)
        users_mixin.confluence.get_user_details_by_accountid.side_effect = (
            http_error_401
        )

        with pytest.raises(Exception):  # Should propagate the original exception
            users_mixin.get_user_details_by_accountid("test-account-id")

        # Test 403 Forbidden
        mock_response_403 = MagicMock()
        mock_response_403.status_code = 403
        http_error_403 = HTTPError(response=mock_response_403)
        users_mixin.confluence.get_user_details_by_username.side_effect = http_error_403

        with pytest.raises(Exception):  # Should propagate the original exception
            users_mixin.get_user_details_by_username("testuser")

    def test_cloud_vs_server_authentication_patterns(self, users_mixin):
        """Test that different authentication patterns work for Cloud vs Server/DC."""
        # Mock Cloud response (account ID based)
        cloud_user_data = {
            "accountId": "5b10ac8d82e05b22cc7d4ef5",
            "accountType": "atlassian",
            "displayName": "Cloud User",
            "accountStatus": "active",
        }

        # Mock Server/DC response (username based)
        server_user_data = {
            "username": "serveruser",
            "userKey": "serveruser-key-12345",
            "displayName": "Server User",
            "status": "active",
        }

        # Test Cloud pattern
        users_mixin.confluence.get_user_details_by_accountid.return_value = (
            cloud_user_data
        )
        cloud_result = users_mixin.get_user_details_by_accountid(
            "5b10ac8d82e05b22cc7d4ef5"
        )
        assert cloud_result["accountId"] == "5b10ac8d82e05b22cc7d4ef5"
        assert "accountType" in cloud_result

        # Test Server/DC pattern
        users_mixin.confluence.get_user_details_by_username.return_value = (
            server_user_data
        )
        server_result = users_mixin.get_user_details_by_username("serveruser")
        assert server_result["username"] == "serveruser"
        assert "userKey" in server_result

    def test_response_data_validation_and_transformation(
        self, users_mixin, mock_user_data_cloud
    ):
        """Test that response data is properly validated and returned as-is."""
        # Arrange
        account_id = "5b10ac8d82e05b22cc7d4ef5"
        users_mixin.confluence.get_user_details_by_accountid.return_value = (
            mock_user_data_cloud
        )

        # Act
        result = users_mixin.get_user_details_by_accountid(account_id)

        # Assert - should return the data exactly as received from the API
        assert result is mock_user_data_cloud  # Same object reference
        assert isinstance(result, dict)
        assert all(
            key in result
            for key in ["accountId", "displayName", "email", "accountStatus"]
        )

    def test_deactivated_user_status_handling(self, users_mixin):
        """Test handling of deactivated users with status expansion."""
        # Arrange
        deactivated_user_data = {
            "accountId": "5b10ac8d82e05b22cc7d4ef5",
            "displayName": "Deactivated User",
            "accountStatus": "inactive",
            "status": "Deactivated",  # Expanded status
        }
        users_mixin.confluence.get_user_details_by_accountid.return_value = (
            deactivated_user_data
        )

        # Act
        result = users_mixin.get_user_details_by_accountid(
            "5b10ac8d82e05b22cc7d4ef5", expand="status"
        )

        # Assert
        assert result["accountStatus"] == "inactive"
        assert result["status"] == "Deactivated"
        users_mixin.confluence.get_user_details_by_accountid.assert_called_once_with(
            "5b10ac8d82e05b22cc7d4ef5", "status"
        )

    def test_method_delegation_to_confluence_client(
        self, users_mixin, mock_current_user_data
    ):
        """Test that methods properly delegate to the underlying confluence client."""
        # Test that the methods are thin wrappers around confluence client methods
        account_id = "test-account-id"
        username = "testuser"
        expand = "status"

        # Test account ID method delegation
        users_mixin.get_user_details_by_accountid(account_id, expand)
        users_mixin.confluence.get_user_details_by_accountid.assert_called_with(
            account_id, expand
        )

        # Test username method delegation
        users_mixin.get_user_details_by_username(username, expand)
        users_mixin.confluence.get_user_details_by_username.assert_called_with(
            username, expand
        )

        # Test current user method delegation - need to mock the return value
        users_mixin.confluence.get.return_value = mock_current_user_data
        users_mixin.get_current_user_info()
        users_mixin.confluence.get.assert_called_with("rest/api/user/current")
