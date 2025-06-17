"""Shared fixtures for Confluence unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the root tests directory to PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent.parent))

from fixtures.confluence_mocks import (
    MOCK_COMMENTS_RESPONSE,
    MOCK_CQL_SEARCH_RESPONSE,
    MOCK_LABELS_RESPONSE,
    MOCK_PAGE_RESPONSE,
    MOCK_PAGES_FROM_SPACE_RESPONSE,
    MOCK_SPACES_RESPONSE,
)

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    with patch.dict(
        "os.environ",
        {
            "CONFLUENCE_URL": "https://example.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test_user",
            "CONFLUENCE_API_TOKEN": "test_token",
        },
    ):
        yield


@pytest.fixture
def mock_config():
    """Return a mock ConfluenceConfig instance."""
    return ConfluenceConfig(
        url="https://example.atlassian.net/wiki",
        auth_type="basic",
        username="test_user",
        api_token="test_token",
    )


@pytest.fixture
def mock_oauth_config():
    """Return a mock ConfluenceConfig instance with OAuth authentication."""
    from mcp_atlassian.utils.oauth import OAuthConfig

    oauth_config = OAuthConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost:8080/callback",
        scope="read:confluence-content.all",
        cloud_id="test_cloud_id",
    )

    return ConfluenceConfig(
        url="https://test-domain.atlassian.net/wiki",
        auth_type="oauth",
        oauth_config=oauth_config,
    )


@pytest.fixture
def mock_atlassian_confluence():
    """Mock the Atlassian Confluence client."""
    with patch("mcp_atlassian.confluence.client.Confluence") as mock:
        confluence_instance = mock.return_value

        # Set up common return values
        confluence_instance.get_all_spaces.return_value = MOCK_SPACES_RESPONSE
        confluence_instance.get_page_by_id.return_value = MOCK_PAGE_RESPONSE
        confluence_instance.get_page_by_title.return_value = MOCK_PAGE_RESPONSE
        confluence_instance.get_all_pages_from_space.return_value = (
            MOCK_PAGES_FROM_SPACE_RESPONSE
        )
        confluence_instance.get_page_comments.return_value = MOCK_COMMENTS_RESPONSE
        confluence_instance.get_page_labels.return_value = MOCK_LABELS_RESPONSE
        confluence_instance.cql.return_value = MOCK_CQL_SEARCH_RESPONSE

        # Mock create_page to return a page with the given title
        confluence_instance.create_page.return_value = {
            "id": "123456789",
            "title": "New Test Page",
        }

        # Mock update_page to return None (as the actual method does)
        confluence_instance.update_page.return_value = None

        yield confluence_instance


@pytest.fixture
def mock_preprocessor():
    """Mock the TextPreprocessor."""
    preprocessor_instance = MagicMock()
    preprocessor_instance.process_html_content.return_value = (
        "<p>Processed HTML</p>",
        "Processed Markdown",
    )
    yield preprocessor_instance


@pytest.fixture
def confluence_client(mock_config, mock_atlassian_confluence, mock_preprocessor):
    """Create a ConfluenceClient instance with mocked dependencies."""
    # Create a client with a mocked configuration
    with patch(
        "mcp_atlassian.preprocessing.TextPreprocessor"
    ) as mock_text_preprocessor:
        mock_text_preprocessor.return_value = mock_preprocessor

        client = ConfluenceClient(config=mock_config)
        # Replace the actual Confluence instance with our mock
        client.confluence = mock_atlassian_confluence
        # Replace the actual preprocessor with our mock
        client.preprocessor = mock_preprocessor
        yield client


@pytest.fixture
def oauth_confluence_client(
    mock_oauth_config, mock_atlassian_confluence, mock_preprocessor
):
    """Create a ConfluenceClient instance with OAuth configuration and mocked dependencies."""
    # Create a client with OAuth configuration
    with (
        patch("mcp_atlassian.preprocessing.TextPreprocessor") as mock_text_preprocessor,
        patch(
            "mcp_atlassian.confluence.client.configure_oauth_session"
        ) as mock_configure_oauth,
        patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence_class,
    ):
        mock_text_preprocessor.return_value = mock_preprocessor
        mock_configure_oauth.return_value = True  # Mock successful OAuth configuration
        mock_confluence_class.return_value = mock_atlassian_confluence

        client = ConfluenceClient(config=mock_oauth_config)
        # Replace the actual Confluence instance with our mock
        client.confluence = mock_atlassian_confluence
        # Mock session for v2 adapter
        client.confluence._session = MagicMock()
        # OAuth clients use api.atlassian.com URL format
        client.confluence.url = f"https://api.atlassian.com/ex/confluence/{mock_oauth_config.oauth_config.cloud_id}"
        # Replace the actual preprocessor with our mock
        client.preprocessor = mock_preprocessor
        yield client
