"""Startup verification that configured credentials actually authenticate.

``is_auth_configured`` only proves credentials are present. Atlassian serves
some endpoints to anonymous callers with HTTP 200 and an empty collection, so
an unusable token would otherwise surface as an empty Jira or Confluence
rather than as an error.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.main import _credentials_are_usable


@pytest.fixture
def jira_config() -> JiraConfig:
    return JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user@example.com",
        api_token="token",
    )


@pytest.fixture
def confluence_config() -> ConfluenceConfig:
    return ConfluenceConfig(
        url="https://test.atlassian.net/wiki",
        auth_type="basic",
        username="user@example.com",
        api_token="token",
    )


class TestJiraCredentialValidation:
    def test_returns_true_when_credentials_authenticate(self, jira_config):
        fetcher = MagicMock()
        with patch("mcp_atlassian.jira.JiraFetcher", return_value=fetcher):
            assert _credentials_are_usable("Jira", jira_config) is True
        fetcher._validate_authentication.assert_called_once()

    def test_returns_false_when_credentials_are_rejected(self, jira_config, caplog):
        fetcher = MagicMock()
        fetcher._validate_authentication.side_effect = Exception("401 Unauthorized")
        with patch("mcp_atlassian.jira.JiraFetcher", return_value=fetcher):
            assert _credentials_are_usable("Jira", jira_config) is False
        assert "401 Unauthorized" in caplog.text

    def test_returns_false_when_client_cannot_be_built(self, jira_config):
        with patch(
            "mcp_atlassian.jira.JiraFetcher", side_effect=Exception("unreachable")
        ):
            assert _credentials_are_usable("Jira", jira_config) is False

    def test_opt_out_skips_the_check(self, jira_config):
        with (
            patch("mcp_atlassian.jira.JiraFetcher") as mock_fetcher,
            patch.dict(os.environ, {"ATLASSIAN_SKIP_AUTH_VALIDATION": "true"}),
        ):
            assert _credentials_are_usable("Jira", jira_config) is True
        mock_fetcher.assert_not_called()


class TestConfluenceCredentialValidation:
    def test_returns_true_when_credentials_authenticate(self, confluence_config):
        fetcher = MagicMock()
        with patch("mcp_atlassian.confluence.ConfluenceFetcher", return_value=fetcher):
            assert _credentials_are_usable("Confluence", confluence_config) is True
        fetcher._validate_authentication.assert_called_once()

    def test_returns_false_when_credentials_are_rejected(self, confluence_config):
        fetcher = MagicMock()
        fetcher._validate_authentication.side_effect = Exception("401 Unauthorized")
        with patch("mcp_atlassian.confluence.ConfluenceFetcher", return_value=fetcher):
            assert _credentials_are_usable("Confluence", confluence_config) is False
