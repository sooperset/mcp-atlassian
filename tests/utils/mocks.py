"""Reusable mock utilities and fixtures for MCP Atlassian tests."""

import os
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

from .factories import AuthConfigFactory, ConfluencePageFactory, JiraIssueFactory


class MockEnvironment:
    """Utility for mocking environment variables."""

    @staticmethod
    @contextmanager
    def oauth_env():
        """Context manager for OAuth environment variables."""
        oauth_vars = AuthConfigFactory.create_oauth_config()
        env_vars = {
            "ATLASSIAN_OAUTH_CLIENT_ID": oauth_vars["client_id"],
            "ATLASSIAN_OAUTH_CLIENT_SECRET": oauth_vars["client_secret"],
            "ATLASSIAN_OAUTH_REDIRECT_URI": oauth_vars["redirect_uri"],
            "ATLASSIAN_OAUTH_SCOPE": oauth_vars["scope"],
            "ATLASSIAN_OAUTH_CLOUD_ID": oauth_vars["cloud_id"],
        }
        with patch.dict(os.environ, env_vars, clear=False):
            yield env_vars

    @staticmethod
    @contextmanager
    def basic_auth_env():
        """Context manager for basic auth environment variables."""
        auth_config = AuthConfigFactory.create_basic_auth_config()
        env_vars = {
            "JIRA_URL": auth_config["url"],
            "JIRA_USERNAME": auth_config["username"],
            "JIRA_API_TOKEN": auth_config["api_token"],
            "CONFLUENCE_URL": f"{auth_config['url']}/wiki",
            "CONFLUENCE_USERNAME": auth_config["username"],
            "CONFLUENCE_API_TOKEN": auth_config["api_token"],
        }
        with patch.dict(os.environ, env_vars, clear=False):
            yield env_vars

    @staticmethod
    @contextmanager
    def clean_env():
        """Context manager with no authentication environment variables."""
        auth_vars = [
            "JIRA_URL",
            "JIRA_USERNAME",
            "JIRA_API_TOKEN",
            "CONFLUENCE_URL",
            "CONFLUENCE_USERNAME",
            "CONFLUENCE_API_TOKEN",
            "ATLASSIAN_OAUTH_CLIENT_ID",
            "ATLASSIAN_OAUTH_CLIENT_SECRET",
            "ATLASSIAN_OAUTH_REDIRECT_URI",
            "ATLASSIAN_OAUTH_SCOPE",
            "ATLASSIAN_OAUTH_CLOUD_ID",
            "ATLASSIAN_OAUTH_ENABLE",
        ]

        # Remove auth vars from environment
        with patch.dict(os.environ, {}, clear=False) as env_dict:
            for var in auth_vars:
                env_dict.pop(var, None)
            yield env_dict


class MockAtlassianClient:
    """Factory for creating mock Atlassian clients."""

    @staticmethod
    def create_jira_client(**response_overrides):
        """Create a mock Jira client with common responses."""
        client = MagicMock()

        # Default responses
        default_responses = {
            "issue": JiraIssueFactory.create(),
            "search_issues": {
                "issues": [
                    JiraIssueFactory.create("TEST-1"),
                    JiraIssueFactory.create("TEST-2"),
                ],
                "total": 2,
            },
            "projects": [{"key": "TEST", "name": "Test Project"}],
            "fields": [{"id": "summary", "name": "Summary"}],
        }

        # Merge with overrides
        responses = {**default_responses, **response_overrides}

        # Set up mock methods
        client.issue.return_value = responses["issue"]
        client.search_issues.return_value = responses["search_issues"]
        client.projects.return_value = responses["projects"]
        client.fields.return_value = responses["fields"]

        return client

    @staticmethod
    def create_confluence_client(**response_overrides):
        """Create a mock Confluence client with common responses."""
        client = MagicMock()

        # Default responses
        default_responses = {
            "get_page_by_id": ConfluencePageFactory.create(),
            "get_all_pages_from_space": {
                "results": [
                    ConfluencePageFactory.create("123"),
                    ConfluencePageFactory.create("456"),
                ]
            },
            "get_all_spaces": {"results": [{"key": "TEST", "name": "Test Space"}]},
        }

        # Merge with overrides
        responses = {**default_responses, **response_overrides}

        # Set up mock methods
        client.get_page_by_id.return_value = responses["get_page_by_id"]
        client.get_all_pages_from_space.return_value = responses[
            "get_all_pages_from_space"
        ]
        client.get_all_spaces.return_value = responses["get_all_spaces"]

        return client


class MockOAuthServer:
    """Utility for mocking OAuth server interactions."""

    @staticmethod
    @contextmanager
    def mock_oauth_flow():
        """Context manager for mocking complete OAuth flow."""
        with (
            patch("http.server.HTTPServer") as mock_server,
            patch("webbrowser.open") as mock_browser,
            patch("secrets.token_urlsafe") as mock_token,
        ):
            # Configure mocks
            mock_token.return_value = "test-state-token"
            mock_server_instance = MagicMock()
            mock_server.return_value = mock_server_instance

            yield {
                "server": mock_server,
                "server_instance": mock_server_instance,
                "browser": mock_browser,
                "token": mock_token,
            }


class MockFastMCP:
    """Utility for mocking FastMCP components."""

    @staticmethod
    def create_request(state_data: dict[str, Any] | None = None):
        """Create a mock FastMCP request."""
        request = MagicMock()
        request.state = MagicMock()

        if state_data:
            for key, value in state_data.items():
                setattr(request.state, key, value)

        return request

    @staticmethod
    def create_context():
        """Create a mock FastMCP context."""
        return MagicMock()


class MockPreprocessor:
    """Utility for mocking content preprocessors."""

    @staticmethod
    def create_html_to_markdown():
        """Create a mock HTML to Markdown preprocessor."""
        preprocessor = MagicMock()
        preprocessor.process.return_value = "# Markdown Content"
        return preprocessor

    @staticmethod
    def create_markdown_to_html():
        """Create a mock Markdown to HTML preprocessor."""
        preprocessor = MagicMock()
        preprocessor.process.return_value = "<h1>HTML Content</h1>"
        return preprocessor
