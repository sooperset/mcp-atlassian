"""Tests for Confluence custom headers functionality."""

import os
from unittest.mock import MagicMock, patch

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig


class TestConfluenceConfigCustomHeaders:
    """Test ConfluenceConfig parsing of custom headers."""

    def test_no_custom_headers(self):
        """Test ConfluenceConfig when no custom headers are configured."""
        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "test_user",
                "CONFLUENCE_API_TOKEN": "test_token",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            assert config.custom_headers == {}

    def test_service_specific_headers_only(self):
        """Test ConfluenceConfig parsing of service-specific headers only."""
        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "test_user",
                "CONFLUENCE_API_TOKEN": "test_token",
                "CONFLUENCE_CUSTOM_HEADERS": "X-Confluence-Specific=confluence_value,X-Service=service_value",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            expected = {
                "X-Confluence-Specific": "confluence_value",
                "X-Service": "service_value",
            }
            assert config.custom_headers == expected

    def test_malformed_headers_are_ignored(self):
        """Test that malformed headers are ignored gracefully."""
        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "test_user",
                "CONFLUENCE_API_TOKEN": "test_token",
                "CONFLUENCE_CUSTOM_HEADERS": "malformed-header,X-Valid=valid_value,another-malformed",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            expected = {"X-Valid": "valid_value"}
            assert config.custom_headers == expected

    def test_empty_header_strings(self):
        """Test handling of empty header strings."""
        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "test_user",
                "CONFLUENCE_API_TOKEN": "test_token",
                "CONFLUENCE_CUSTOM_HEADERS": "   ",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            assert config.custom_headers == {}

    def test_passthrough_headers(self):
        """Test ConfluenceConfig parsing of passthrough header names."""
        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
                "CONFLUENCE_USERNAME": "test_user",
                "CONFLUENCE_API_TOKEN": "test_token",
                "CONFLUENCE_PASSTHROUGH_HEADERS": "X-SSO-User, X-Request-ID,x-sso-user",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            assert config.passthrough_headers == ["X-SSO-User", "X-Request-ID"]


class TestConfluenceClientCustomHeaders:
    """Test ConfluenceClient custom headers application."""

    def test_no_custom_headers_applied(self, monkeypatch):
        """Test that no headers are applied when none are configured."""
        # Mock Confluence and related dependencies
        mock_confluence = MagicMock()
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_confluence._session = mock_session

        monkeypatch.setattr(
            "mcp_atlassian.confluence.client.Confluence",
            lambda **kwargs: mock_confluence,
        )
        monkeypatch.setattr(
            "mcp_atlassian.confluence.client.configure_ssl_verification",
            lambda **kwargs: None,
        )
        monkeypatch.setattr(
            "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor",
            lambda **kwargs: MagicMock(),
        )

        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="basic",
            username="test_user",
            api_token="test_token",
            custom_headers={},
        )

        client = ConfluenceClient(config=config)

        # Only the default User-Agent should be present; no custom headers added.
        assert set(mock_session.headers.keys()) == {"User-Agent"}
        assert mock_session.headers["User-Agent"].startswith("mcp-atlassian/")

    def test_custom_headers_applied_to_session(self, monkeypatch):
        """Test that custom headers are applied to the Confluence session."""
        # Mock Confluence and related dependencies
        mock_confluence = MagicMock()
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_confluence._session = mock_session

        monkeypatch.setattr(
            "mcp_atlassian.confluence.client.Confluence",
            lambda **kwargs: mock_confluence,
        )
        monkeypatch.setattr(
            "mcp_atlassian.confluence.client.configure_ssl_verification",
            lambda **kwargs: None,
        )
        monkeypatch.setattr(
            "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor",
            lambda **kwargs: MagicMock(),
        )

        custom_headers = {
            "X-Corp-Auth": "token123",
            "X-Dept": "engineering",
            "User-Agent": "CustomConfluenceClient/1.0",
        }

        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="basic",
            username="test_user",
            api_token="test_token",
            custom_headers=custom_headers,
        )

        client = ConfluenceClient(config=config)

        # Verify custom headers were applied to session
        for header_name, header_value in custom_headers.items():
            assert mock_session.headers[header_name] == header_value
