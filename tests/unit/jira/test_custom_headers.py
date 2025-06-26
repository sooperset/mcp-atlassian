"""Tests for JIRA custom headers functionality."""

import os
from unittest.mock import MagicMock, patch

from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig


class TestJiraConfigCustomHeaders:
    """Test JiraConfig parsing of custom headers."""

    def test_no_custom_headers(self):
        """Test JiraConfig when no custom headers are configured."""
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "test_user",
                "JIRA_API_TOKEN": "test_token",
            },
            clear=True,
        ):
            config = JiraConfig.from_env()
            assert config.custom_headers == {}

    def test_service_specific_headers_only(self):
        """Test JiraConfig parsing of service-specific headers only."""
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "test_user",
                "JIRA_API_TOKEN": "test_token",
                "JIRA_CUSTOM_HEADERS": "X-Jira-Specific=jira_value,X-Service=service_value",
            },
            clear=True,
        ):
            config = JiraConfig.from_env()
            expected = {"X-Jira-Specific": "jira_value", "X-Service": "service_value"}
            assert config.custom_headers == expected

    def test_malformed_headers_are_ignored(self):
        """Test that malformed headers are ignored gracefully."""
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "test_user",
                "JIRA_API_TOKEN": "test_token",
                "JIRA_CUSTOM_HEADERS": "malformed-header,X-Valid=valid_value,another-malformed",
            },
            clear=True,
        ):
            config = JiraConfig.from_env()
            expected = {"X-Valid": "valid_value"}
            assert config.custom_headers == expected

    def test_empty_header_strings(self):
        """Test handling of empty header strings."""
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "https://test.atlassian.net",
                "JIRA_USERNAME": "test_user",
                "JIRA_API_TOKEN": "test_token",
                "JIRA_CUSTOM_HEADERS": "   ",
            },
            clear=True,
        ):
            config = JiraConfig.from_env()
            assert config.custom_headers == {}


class TestJiraClientCustomHeaders:
    """Test JiraClient custom headers application."""

    def test_no_custom_headers_applied(self, monkeypatch):
        """Test that no headers are applied when none are configured."""
        # Mock Jira and related dependencies
        mock_jira = MagicMock()
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_jira._session = mock_session

        monkeypatch.setattr(
            "mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira
        )
        monkeypatch.setattr(
            "mcp_atlassian.jira.client.configure_ssl_verification",
            lambda **kwargs: None,
        )

        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="test_user",
            api_token="test_token",
            custom_headers={},
        )

        client = JiraClient(config=config)

        # Verify no custom headers were applied
        assert mock_session.headers == {}

    def test_custom_headers_applied_to_session(self, monkeypatch):
        """Test that custom headers are applied to the JIRA session."""
        # Mock Jira and related dependencies
        mock_jira = MagicMock()
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_jira._session = mock_session

        monkeypatch.setattr(
            "mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira
        )
        monkeypatch.setattr(
            "mcp_atlassian.jira.client.configure_ssl_verification",
            lambda **kwargs: None,
        )

        custom_headers = {
            "X-Corp-Auth": "token123",
            "X-Dept": "engineering",
            "User-Agent": "CustomJiraClient/1.0",
        }

        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="test_user",
            api_token="test_token",
            custom_headers=custom_headers,
        )

        client = JiraClient(config=config)

        # Verify custom headers were applied to session
        for header_name, header_value in custom_headers.items():
            assert mock_session.headers[header_name] == header_value
