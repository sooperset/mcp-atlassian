"""Tests for Basic Authentication in user config creation."""

import unittest
from unittest.mock import MagicMock, patch

from mcp_atlassian.confluence import ConfluenceConfig
from mcp_atlassian.jira import JiraConfig
from mcp_atlassian.servers.dependencies import _create_user_config_for_fetcher


class TestBasicAuthConfig(unittest.TestCase):
    """Test cases for Basic Authentication in user config creation."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock JiraConfig
        self.jira_config = MagicMock(spec=JiraConfig)
        self.jira_config.url = "https://jira.example.com"
        self.jira_config.ssl_verify = True
        self.jira_config.http_proxy = None
        self.jira_config.https_proxy = None
        self.jira_config.no_proxy = None
        self.jira_config.socks_proxy = None
        self.jira_config.projects_filter = ["TEST"]

        # Create mock ConfluenceConfig
        self.confluence_config = MagicMock(spec=ConfluenceConfig)
        self.confluence_config.url = "https://confluence.example.com"
        self.confluence_config.ssl_verify = True
        self.confluence_config.http_proxy = None
        self.confluence_config.https_proxy = None
        self.confluence_config.no_proxy = None
        self.confluence_config.socks_proxy = None
        self.confluence_config.spaces_filter = ["TEST"]

    @patch("mcp_atlassian.servers.dependencies.logger")
    def test_create_jira_config_with_basic_auth(self, mock_logger):
        """Test creating JiraConfig with Basic Authentication."""
        username = "test@example.com"
        password = "password123"
        credentials = {
            "username": username,
            "password": password,
            "user_email_context": username,
        }

        # Create user config with Basic Authentication
        user_config = _create_user_config_for_fetcher(
            base_config=self.jira_config, auth_type="basic", credentials=credentials
        )

        # Verify the config was created correctly
        self.assertEqual(user_config.auth_type, "basic")
        self.assertEqual(user_config.username, username)
        self.assertEqual(user_config.api_token, password)
        self.assertIsNone(user_config.personal_token)
        self.assertIsNone(user_config.oauth_config)
        self.assertEqual(user_config.url, self.jira_config.url)
        self.assertEqual(user_config.projects_filter, self.jira_config.projects_filter)

    @patch("mcp_atlassian.servers.dependencies.logger")
    def test_create_confluence_config_with_basic_auth(self, mock_logger):
        """Test creating ConfluenceConfig with Basic Authentication."""
        username = "test@example.com"
        password = "password123"
        credentials = {
            "username": username,
            "password": password,
            "user_email_context": username,
        }

        # Create user config with Basic Authentication
        user_config = _create_user_config_for_fetcher(
            base_config=self.confluence_config,
            auth_type="basic",
            credentials=credentials,
        )

        # Verify the config was created correctly
        self.assertEqual(user_config.auth_type, "basic")
        self.assertEqual(user_config.username, username)
        self.assertEqual(user_config.api_token, password)
        self.assertIsNone(user_config.personal_token)
        self.assertIsNone(user_config.oauth_config)
        self.assertEqual(user_config.url, self.confluence_config.url)
        self.assertEqual(
            user_config.spaces_filter, self.confluence_config.spaces_filter
        )

    @patch("mcp_atlassian.servers.dependencies.logger")
    def test_basic_auth_missing_username(self, mock_logger):
        """Test error handling when username is missing for Basic Authentication."""
        credentials = {"password": "password123", "user_email_context": None}

        # Attempt to create user config with missing username
        with self.assertRaises(ValueError) as context:
            _create_user_config_for_fetcher(
                base_config=self.jira_config, auth_type="basic", credentials=credentials
            )

        self.assertIn("Username missing", str(context.exception))

    @patch("mcp_atlassian.servers.dependencies.logger")
    def test_basic_auth_missing_password(self, mock_logger):
        """Test error handling when password is missing for Basic Authentication."""
        credentials = {
            "username": "test@example.com",
            "user_email_context": "test@example.com",
        }

        # Attempt to create user config with missing password
        with self.assertRaises(ValueError) as context:
            _create_user_config_for_fetcher(
                base_config=self.jira_config, auth_type="basic", credentials=credentials
            )

        self.assertIn("Password missing", str(context.exception))

    @patch("mcp_atlassian.servers.dependencies.logger")
    def test_basic_auth_with_cloud_id_warning(self, mock_logger):
        """Test warning when cloud_id is provided with Basic Authentication."""
        username = "test@example.com"
        password = "password123"
        credentials = {
            "username": username,
            "password": password,
            "user_email_context": username,
        }

        # Create user config with Basic Authentication and cloud_id
        _create_user_config_for_fetcher(
            base_config=self.jira_config,
            auth_type="basic",
            credentials=credentials,
            cloud_id="cloud-123",
        )

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        warning_message = mock_logger.warning.call_args[0][0]
        self.assertIn("Cloud ID", warning_message)
        self.assertIn("Basic authentication", warning_message)
