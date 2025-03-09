"""Unit tests for the ConfluenceClient class."""

from unittest.mock import MagicMock, patch

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig


def test_init_with_config():
    """Test initializing the client with a provided config."""
    # Arrange
    config = ConfluenceConfig(
        url="https://test.atlassian.net/wiki",
        username="test_user",
        api_token="test_token",
    )

    # Mock the Confluence class and TextPreprocessor
    with (
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
        patch("mcp_atlassian.preprocessing.TextPreprocessor") as mock_preprocessor,
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


def test_init_from_env():
    """Test initializing the client from environment variables."""
    # Arrange
    with (
        patch(
            "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
        ) as mock_from_env,
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
        patch("mcp_atlassian.preprocessing.TextPreprocessor"),
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
            "mcp_atlassian.preprocessing.TextPreprocessor"
        ) as mock_preprocessor_class,
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
