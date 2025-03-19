"""Unit tests for the ConfluenceClient class."""

from unittest.mock import MagicMock, patch

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig


def test_init_with_basic_auth():
    """Test initializing the client with basic auth configuration."""
    # Arrange
    config = ConfluenceConfig(
        url="https://test.atlassian.net/wiki",
        auth_type="basic",
        username="test_user",
        api_token="test_token",
    )

    # Mock the Confluence class, ConfluencePreprocessor, and configure_ssl_verification
    with (
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
        patch(
            "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor"
        ) as mock_preprocessor,
        patch(
            "mcp_atlassian.confluence.client.configure_ssl_verification"
        ) as mock_configure_ssl,
    ):
        # Act
        client = ConfluenceClient(config=config)

        # Assert
        mock_confluence.assert_called_once_with(
            url="https://test.atlassian.net/wiki",
            username="test_user",
            password="test_token",
            cloud=True,
        )
        assert client.config == config
        assert client.confluence == mock_confluence.return_value
        assert client.preprocessor == mock_preprocessor.return_value

        # Verify SSL verification was configured
        mock_configure_ssl.assert_called_once_with(
            service_name="Confluence",
            url="https://test.atlassian.net/wiki",
            session=mock_confluence.return_value._session,
            ssl_verify=True,
        )


def test_init_with_token_auth():
    """Test initializing the client with token auth configuration."""
    # Arrange
    config = ConfluenceConfig(
        url="https://confluence.example.com",
        auth_type="token",
        personal_token="test_personal_token",
        ssl_verify=False,
    )

    # Mock the Confluence class, ConfluencePreprocessor, and configure_ssl_verification
    with (
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
        patch(
            "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor"
        ) as mock_preprocessor,
        patch(
            "mcp_atlassian.confluence.client.configure_ssl_verification"
        ) as mock_configure_ssl,
    ):
        # Act
        client = ConfluenceClient(config=config)

        # Assert
        mock_confluence.assert_called_once_with(
            url="https://confluence.example.com",
            token="test_personal_token",
            cloud=False,
            verify_ssl=False,
        )
        assert client.config == config
        assert client.confluence == mock_confluence.return_value
        assert client.preprocessor == mock_preprocessor.return_value

        # Verify SSL verification was configured with ssl_verify=False
        mock_configure_ssl.assert_called_once_with(
            service_name="Confluence",
            url="https://confluence.example.com",
            session=mock_confluence.return_value._session,
            ssl_verify=False,
        )


def test_init_from_env():
    """Test initializing the client from environment variables."""
    # Arrange
    with (
        patch(
            "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
        ) as mock_from_env,
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
        patch("mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor"),
        patch("mcp_atlassian.confluence.client.configure_ssl_verification"),
    ):
        mock_config = MagicMock()
        mock_from_env.return_value = mock_config

        # Act
        client = ConfluenceClient()

        # Assert
        mock_from_env.assert_called_once()
        assert client.config == mock_config


def test_process_html_content():
    """Test the _process_html_content method."""
    # Arrange
    with (
        patch("mcp_atlassian.confluence.client.ConfluenceConfig.from_env"),
        patch("mcp_atlassian.confluence.client.Confluence"),
        patch(
            "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor"
        ) as mock_preprocessor_class,
        patch("mcp_atlassian.confluence.client.configure_ssl_verification"),
    ):
        mock_preprocessor = mock_preprocessor_class.return_value
        mock_preprocessor.process_html_content.return_value = (
            "<p>HTML</p>",
            "Markdown",
        )

        client = ConfluenceClient()

        # Act
        html, markdown = client._process_html_content("<p>Test</p>", "TEST")

        # Assert
        mock_preprocessor.process_html_content.assert_called_once_with(
            "<p>Test</p>", "TEST"
        )
        assert html == "<p>HTML</p>"
        assert markdown == "Markdown"


def test_get_user_details_by_accountid():
    """Test the get_user_details_by_accountid method."""
    # Arrange
    with (
        patch("mcp_atlassian.confluence.client.ConfluenceConfig.from_env"),
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence_class,
        patch("mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor"),
        patch("mcp_atlassian.confluence.client.configure_ssl_verification"),
    ):
        mock_confluence = mock_confluence_class.return_value
        mock_confluence.get_user_details_by_accountid.return_value = {
            "displayName": "Test User",
            "accountId": "123456",
            "emailAddress": "test@example.com",
            "active": True,
        }

        client = ConfluenceClient()

        # Act
        user_details = client.get_user_details_by_accountid("123456")

        # Assert
        mock_confluence.get_user_details_by_accountid.assert_called_once_with(
            "123456", None
        )
        assert user_details["displayName"] == "Test User"
        assert user_details["accountId"] == "123456"
        assert user_details["emailAddress"] == "test@example.com"
        assert user_details["active"] is True

        # Test with expand parameter
        mock_confluence.get_user_details_by_accountid.reset_mock()
        mock_confluence.get_user_details_by_accountid.return_value = {
            "displayName": "Test User",
            "accountId": "123456",
            "status": "active",
        }

        user_details = client.get_user_details_by_accountid("123456", expand="status")

        mock_confluence.get_user_details_by_accountid.assert_called_once_with(
            "123456", "status"
        )
        assert user_details["status"] == "active"
