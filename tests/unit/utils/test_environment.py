"""Tests for the environment utilities module."""

import logging
import os
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.environment import get_available_services


@pytest.fixture(autouse=True)
def setup_logger():
    """Ensure logger is set to INFO level for capturing log messages."""
    logger = logging.getLogger("mcp-atlassian.utils.environment")
    logger.setLevel(logging.INFO)
    yield
    # Reset to default after test
    logger.setLevel(logging.WARNING)


class TestGetAvailableServices:
    """Test cases for get_available_services function."""

    def test_no_services_configured(self, caplog):
        """Test that no services are available when no environment variables are set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}
            assert (
                "Confluence is not configured or required environment variables are missing."
                in caplog.text
            )
            assert (
                "Jira is not configured or required environment variables are missing."
                in caplog.text
            )

    def test_missing_urls(self, caplog):
        """Test that services are not available when URLs are missing."""
        env_vars = {
            "CONFLUENCE_USERNAME": "user",
            "CONFLUENCE_API_TOKEN": "token",
            "JIRA_USERNAME": "user",
            "JIRA_API_TOKEN": "token",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}
            assert (
                "Confluence is not configured or required environment variables are missing."
                in caplog.text
            )
            assert (
                "Jira is not configured or required environment variables are missing."
                in caplog.text
            )

    @pytest.mark.parametrize(
        "confluence_url,jira_url,expected_confluence,expected_jira",
        [
            (
                "https://company.atlassian.net",
                "https://company.atlassian.net",
                True,
                True,
            ),
            ("https://company.atlassian.net", None, True, False),
            (None, "https://company.atlassian.net", False, True),
            ("https://jira.company.com", "https://confluence.company.com", True, True),
        ],
    )
    def test_oauth_authentication_cloud_only(
        self, confluence_url, jira_url, expected_confluence, expected_jira, caplog
    ):
        """Test OAuth authentication detection for Cloud instances."""
        env_vars = {
            "ATLASSIAN_OAUTH_CLIENT_ID": "client_id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "client_secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:jira-user",
            "ATLASSIAN_OAUTH_CLOUD_ID": "cloud_id",
        }

        if confluence_url:
            env_vars["CONFLUENCE_URL"] = confluence_url
        if jira_url:
            env_vars["JIRA_URL"] = jira_url

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": expected_confluence, "jira": expected_jira}

            if expected_confluence:
                assert (
                    "Using Confluence OAuth 2.0 (3LO) authentication (Cloud-only features)"
                    in caplog.text
                )
            if expected_jira:
                assert (
                    "Using Jira OAuth 2.0 (3LO) authentication (Cloud-only features)"
                    in caplog.text
                )

    def test_oauth_missing_cloud_id(self, caplog):
        """Test that OAuth fails when CLOUD_ID is missing."""
        env_vars = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "JIRA_URL": "https://company.atlassian.net",
            "ATLASSIAN_OAUTH_CLIENT_ID": "client_id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "client_secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:jira-user",
            # Missing ATLASSIAN_OAUTH_CLOUD_ID
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}
            assert (
                "Confluence is not configured or required environment variables are missing."
                in caplog.text
            )
            assert (
                "Jira is not configured or required environment variables are missing."
                in caplog.text
            )

    def test_oauth_missing_required_vars(self, caplog):
        """Test that OAuth fails when any required variable is missing."""
        base_env = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "JIRA_URL": "https://company.atlassian.net",
        }

        oauth_vars = [
            "ATLASSIAN_OAUTH_CLIENT_ID",
            "ATLASSIAN_OAUTH_CLIENT_SECRET",
            "ATLASSIAN_OAUTH_REDIRECT_URI",
            "ATLASSIAN_OAUTH_SCOPE",
            "ATLASSIAN_OAUTH_CLOUD_ID",
        ]

        # Test missing each required OAuth variable
        for missing_var in oauth_vars:
            env_vars = base_env.copy()
            for var in oauth_vars:
                if var != missing_var:
                    env_vars[var] = "test_value"

            with patch.dict(os.environ, env_vars, clear=True):
                result = get_available_services()

                assert result == {"confluence": False, "jira": False}

    @pytest.mark.parametrize(
        "confluence_url,jira_url",
        [
            ("https://company.atlassian.net", "https://company.atlassian.net"),
            ("https://team.jira.com", "https://team.jira.com"),
            ("https://dev.jira-dev.com", "https://dev.jira-dev.com"),
        ],
    )
    def test_cloud_basic_auth_with_api_token(self, confluence_url, jira_url, caplog):
        """Test Cloud Basic Authentication with API tokens."""
        env_vars = {
            "CONFLUENCE_URL": confluence_url,
            "CONFLUENCE_USERNAME": "user@company.com",
            "CONFLUENCE_API_TOKEN": "api_token",
            "JIRA_URL": jira_url,
            "JIRA_USERNAME": "user@company.com",
            "JIRA_API_TOKEN": "api_token",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence Cloud Basic Authentication (API Token)" in caplog.text
            )
            assert "Using Jira Cloud Basic Authentication (API Token)" in caplog.text

    def test_cloud_basic_auth_missing_username(self, caplog):
        """Test that Cloud Basic Auth fails when username is missing."""
        env_vars = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "CONFLUENCE_API_TOKEN": "api_token",
            "JIRA_URL": "https://company.atlassian.net",
            "JIRA_API_TOKEN": "api_token",
            # Missing usernames
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}

    def test_cloud_basic_auth_missing_api_token(self, caplog):
        """Test that Cloud Basic Auth fails when API token is missing."""
        env_vars = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "CONFLUENCE_USERNAME": "user@company.com",
            "JIRA_URL": "https://company.atlassian.net",
            "JIRA_USERNAME": "user@company.com",
            # Missing API tokens
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}

    @pytest.mark.parametrize(
        "confluence_url,jira_url",
        [
            ("https://jira.company.com", "https://jira.company.com"),
            ("http://localhost:8080", "http://localhost:8080"),
            ("https://192.168.1.100", "https://192.168.1.100"),
            ("https://confluence.internal", "https://jira.internal"),
        ],
    )
    def test_server_pat_authentication(self, confluence_url, jira_url, caplog):
        """Test Server/Data Center PAT authentication."""
        env_vars = {
            "CONFLUENCE_URL": confluence_url,
            "CONFLUENCE_PERSONAL_TOKEN": "pat_token",
            "JIRA_URL": jira_url,
            "JIRA_PERSONAL_TOKEN": "pat_token",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )
            assert (
                "Using Jira Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )

    @pytest.mark.parametrize(
        "confluence_url,jira_url",
        [
            ("https://jira.company.com", "https://jira.company.com"),
            ("http://localhost:8080", "http://localhost:8080"),
            ("https://10.0.0.1", "https://172.16.0.1"),
        ],
    )
    def test_server_basic_auth(self, confluence_url, jira_url, caplog):
        """Test Server/Data Center Basic Authentication."""
        env_vars = {
            "CONFLUENCE_URL": confluence_url,
            "CONFLUENCE_USERNAME": "admin",
            "CONFLUENCE_API_TOKEN": "password",
            "JIRA_URL": jira_url,
            "JIRA_USERNAME": "admin",
            "JIRA_API_TOKEN": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )
            assert (
                "Using Jira Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )

    def test_server_auth_precedence_pat_over_basic(self, caplog):
        """Test that PAT authentication takes precedence over Basic Auth for Server/DC."""
        env_vars = {
            "CONFLUENCE_URL": "https://confluence.company.com",
            "CONFLUENCE_PERSONAL_TOKEN": "pat_token",
            "CONFLUENCE_USERNAME": "admin",
            "CONFLUENCE_API_TOKEN": "password",
            "JIRA_URL": "https://jira.company.com",
            "JIRA_PERSONAL_TOKEN": "pat_token",
            "JIRA_USERNAME": "admin",
            "JIRA_API_TOKEN": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )
            assert (
                "Using Jira Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )

    def test_server_auth_missing_username_with_api_token(self, caplog):
        """Test that Server Basic Auth fails when username is missing but API token is present."""
        env_vars = {
            "CONFLUENCE_URL": "https://confluence.company.com",
            "CONFLUENCE_API_TOKEN": "password",
            "JIRA_URL": "https://jira.company.com",
            "JIRA_API_TOKEN": "password",
            # Missing usernames
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}

    def test_server_auth_missing_api_token_with_username(self, caplog):
        """Test that Server Basic Auth fails when API token is missing but username is present."""
        env_vars = {
            "CONFLUENCE_URL": "https://confluence.company.com",
            "CONFLUENCE_USERNAME": "admin",
            "JIRA_URL": "https://jira.company.com",
            "JIRA_USERNAME": "admin",
            # Missing API tokens
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}

    def test_mixed_configurations(self, caplog):
        """Test mixed configurations where one service is configured and the other is not."""
        env_vars = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "CONFLUENCE_USERNAME": "user@company.com",
            "CONFLUENCE_API_TOKEN": "api_token",
            # Jira not configured
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": False}
            assert (
                "Using Confluence Cloud Basic Authentication (API Token)" in caplog.text
            )
            assert (
                "Jira is not configured or required environment variables are missing."
                in caplog.text
            )

    def test_oauth_precedence_over_basic_auth_cloud(self, caplog):
        """Test that OAuth takes precedence over Basic Auth for Cloud instances."""
        env_vars = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "CONFLUENCE_USERNAME": "user@company.com",
            "CONFLUENCE_API_TOKEN": "api_token",
            "JIRA_URL": "https://company.atlassian.net",
            "JIRA_USERNAME": "user@company.com",
            "JIRA_API_TOKEN": "api_token",
            # OAuth vars (should take precedence)
            "ATLASSIAN_OAUTH_CLIENT_ID": "client_id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "client_secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:jira-user",
            "ATLASSIAN_OAUTH_CLOUD_ID": "cloud_id",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence OAuth 2.0 (3LO) authentication (Cloud-only features)"
                in caplog.text
            )
            assert (
                "Using Jira OAuth 2.0 (3LO) authentication (Cloud-only features)"
                in caplog.text
            )
            # Should not see Basic Auth messages
            assert (
                "Using Confluence Cloud Basic Authentication (API Token)"
                not in caplog.text
            )
            assert (
                "Using Jira Cloud Basic Authentication (API Token)" not in caplog.text
            )

    def test_oauth_applies_to_all_instances_with_oauth_vars(self, caplog):
        """Test that OAuth configuration applies to any instance when OAuth vars are present."""
        env_vars = {
            "CONFLUENCE_URL": "https://confluence.company.com",
            "CONFLUENCE_USERNAME": "admin",
            "CONFLUENCE_API_TOKEN": "password",
            "JIRA_URL": "https://jira.company.com",
            "JIRA_USERNAME": "admin",
            "JIRA_API_TOKEN": "password",
            # OAuth vars (take precedence even for Server/DC URLs)
            "ATLASSIAN_OAUTH_CLIENT_ID": "client_id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "client_secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:jira-user",
            "ATLASSIAN_OAUTH_CLOUD_ID": "cloud_id",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence OAuth 2.0 (3LO) authentication (Cloud-only features)"
                in caplog.text
            )
            assert (
                "Using Jira OAuth 2.0 (3LO) authentication (Cloud-only features)"
                in caplog.text
            )
            # Should not see Server/DC or Basic Auth messages
            assert "Server/Data Center authentication" not in caplog.text
            assert "Basic Authentication" not in caplog.text

    def test_server_instances_without_oauth_vars(self, caplog):
        """Test that Server/DC instances use Basic Auth when OAuth vars are not present."""
        env_vars = {
            "CONFLUENCE_URL": "https://confluence.company.com",
            "CONFLUENCE_USERNAME": "admin",
            "CONFLUENCE_API_TOKEN": "password",
            "JIRA_URL": "https://jira.company.com",
            "JIRA_USERNAME": "admin",
            "JIRA_API_TOKEN": "password",
            # No OAuth vars
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": True, "jira": True}
            assert (
                "Using Confluence Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )
            assert (
                "Using Jira Server/Data Center authentication (PAT or Basic Auth)"
                in caplog.text
            )
            # Should not see OAuth messages
            assert "OAuth 2.0 (3LO) authentication" not in caplog.text

    def test_return_value_structure(self):
        """Test that the return value has the correct structure."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_available_services()

            assert isinstance(result, dict)
            assert set(result.keys()) == {"confluence", "jira"}
            assert isinstance(result["confluence"], bool)
            assert isinstance(result["jira"], bool)

    def test_logging_behavior_with_different_levels(self, caplog):
        """Test that logging messages are produced at the correct level."""
        env_vars = {
            "CONFLUENCE_URL": "https://company.atlassian.net",
            "CONFLUENCE_USERNAME": "user@company.com",
            "CONFLUENCE_API_TOKEN": "api_token",
        }

        with caplog.at_level(logging.INFO):
            with patch.dict(os.environ, env_vars, clear=True):
                result = get_available_services()

                assert result == {"confluence": True, "jira": False}
                assert (
                    len(caplog.records) == 2
                )  # One for Confluence success, one for Jira failure

                # Check log levels
                assert caplog.records[0].levelname == "INFO"
                assert caplog.records[1].levelname == "INFO"

    @pytest.mark.parametrize(
        "service_vars,expected_logs",
        [
            (
                {
                    "CONFLUENCE_URL": "https://company.atlassian.net",
                    "CONFLUENCE_USERNAME": "user",
                    "CONFLUENCE_API_TOKEN": "token",
                },
                [
                    "Using Confluence Cloud Basic Authentication (API Token)",
                    "Jira is not configured or required environment variables are missing.",
                ],
            ),
            (
                {
                    "JIRA_URL": "https://jira.company.com",
                    "JIRA_PERSONAL_TOKEN": "token",
                },
                [
                    "Confluence is not configured or required environment variables are missing.",
                    "Using Jira Server/Data Center authentication (PAT or Basic Auth)",
                ],
            ),
            (
                {},
                [
                    "Confluence is not configured or required environment variables are missing.",
                    "Jira is not configured or required environment variables are missing.",
                ],
            ),
        ],
    )
    def test_logging_messages_for_different_configurations(
        self, service_vars, expected_logs, caplog
    ):
        """Test that correct logging messages are produced for different configurations."""
        with patch.dict(os.environ, service_vars, clear=True):
            get_available_services()

            for expected_log in expected_logs:
                assert expected_log in caplog.text

    def test_edge_case_empty_environment_variables(self, caplog):
        """Test behavior with empty string environment variables."""
        env_vars = {
            "CONFLUENCE_URL": "",
            "JIRA_URL": "",
            "CONFLUENCE_USERNAME": "",
            "CONFLUENCE_API_TOKEN": "",
            "JIRA_USERNAME": "",
            "JIRA_API_TOKEN": "",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            assert result == {"confluence": False, "jira": False}
            assert (
                "Confluence is not configured or required environment variables are missing."
                in caplog.text
            )
            assert (
                "Jira is not configured or required environment variables are missing."
                in caplog.text
            )

    def test_case_sensitivity_of_environment_variables(self, caplog):
        """Test that environment variable names are case-sensitive."""
        env_vars = {
            "confluence_url": "https://company.atlassian.net",  # lowercase
            "confluence_username": "user@company.com",  # lowercase
            "confluence_api_token": "api_token",  # lowercase
            "jira_url": "https://company.atlassian.net",  # lowercase
            "jira_username": "user@company.com",  # lowercase
            "jira_api_token": "api_token",  # lowercase
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_available_services()

            # Should not be configured because environment variables are case-sensitive
            assert result == {"confluence": False, "jira": False}
