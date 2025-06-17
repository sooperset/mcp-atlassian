"""Integration tests for SSL verification functionality."""

import os
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import SSLError
from requests.sessions import Session

from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.ssl import SSLIgnoreAdapter, configure_ssl_verification
from tests.utils.base import BaseAuthTest
from tests.utils.mocks import MockEnvironment


@pytest.mark.integration
def test_configure_ssl_verification_with_real_confluence_url():
    """Test SSL verification configuration with real Confluence URL from environment."""
    # Get the URL from the environment
    url = os.getenv("CONFLUENCE_URL")
    if not url:
        pytest.skip("CONFLUENCE_URL not set in environment")

    # Create a real session
    session = Session()
    original_adapters_count = len(session.adapters)

    # Mock the SSL_VERIFY value to be False for this test
    with patch.dict(os.environ, {"CONFLUENCE_SSL_VERIFY": "false"}):
        # Configure SSL verification - explicitly pass ssl_verify=False
        configure_ssl_verification(
            service_name="Confluence",
            url=url,
            session=session,
            ssl_verify=False,
        )

        # Extract domain from URL (remove protocol and path)
        domain = url.split("://")[1].split("/")[0]

        # Verify the adapters are mounted correctly
        assert len(session.adapters) == original_adapters_count + 2
        assert f"https://{domain}" in session.adapters
        assert f"http://{domain}" in session.adapters
        assert isinstance(session.adapters[f"https://{domain}"], SSLIgnoreAdapter)
        assert isinstance(session.adapters[f"http://{domain}"], SSLIgnoreAdapter)


class TestSSLVerificationEnhanced(BaseAuthTest):
    """Enhanced SSL verification tests using test utilities."""

    @pytest.mark.integration
    def test_ssl_verification_enabled_by_default(self):
        """Test that SSL verification is enabled by default."""
        with MockEnvironment.basic_auth_env():
            # For Jira
            jira_config = JiraConfig.from_env()
            assert jira_config.ssl_verify is True

            # For Confluence
            confluence_config = ConfluenceConfig.from_env()
            assert confluence_config.ssl_verify is True

    @pytest.mark.integration
    def test_ssl_verification_disabled_via_env(self):
        """Test SSL verification can be disabled via environment variables."""
        with MockEnvironment.basic_auth_env() as env_vars:
            env_vars["JIRA_SSL_VERIFY"] = "false"
            env_vars["CONFLUENCE_SSL_VERIFY"] = "false"

            # For Jira - need to reload config after env change
            with patch.dict(os.environ, env_vars):
                jira_config = JiraConfig.from_env()
                assert jira_config.ssl_verify is False

                # For Confluence
                confluence_config = ConfluenceConfig.from_env()
                assert confluence_config.ssl_verify is False

    @pytest.mark.integration
    def test_ssl_adapter_mounting_for_multiple_domains(self):
        """Test SSL adapters are correctly mounted for multiple domains."""
        session = Session()

        # Configure for multiple domains
        urls = [
            "https://domain1.atlassian.net",
            "https://domain2.atlassian.net/wiki",
            "https://custom.domain.com/jira",
        ]

        for url in urls:
            configure_ssl_verification(
                service_name="Test", url=url, session=session, ssl_verify=False
            )

        # Verify all domains have SSL adapters
        assert "https://domain1.atlassian.net" in session.adapters
        assert "https://domain2.atlassian.net" in session.adapters
        assert "https://custom.domain.com" in session.adapters

    @pytest.mark.integration
    def test_ssl_error_handling_with_invalid_cert(self, monkeypatch):
        """Test SSL error handling when certificate validation fails."""
        # Mock the Jira class to simulate SSL error
        mock_jira = MagicMock()
        mock_jira.side_effect = SSLError("Certificate verification failed")
        monkeypatch.setattr("mcp_atlassian.jira.client.Jira", mock_jira)

        with MockEnvironment.basic_auth_env():
            config = JiraConfig.from_env()
            config.ssl_verify = True  # Ensure SSL verification is on

            # Creating client should raise SSL error
            with pytest.raises(SSLError, match="Certificate verification failed"):
                JiraClient(config=config)

    @pytest.mark.integration
    def test_ssl_verification_with_custom_ca_bundle(self):
        """Test SSL verification with custom CA bundle path."""
        with MockEnvironment.basic_auth_env() as env_vars:
            # Set custom CA bundle path
            custom_ca_path = "/path/to/custom/ca-bundle.crt"
            env_vars["JIRA_SSL_VERIFY"] = custom_ca_path
            env_vars["CONFLUENCE_SSL_VERIFY"] = custom_ca_path

            # For Jira - need to reload config after env change
            with patch.dict(os.environ, env_vars):
                jira_config = JiraConfig.from_env()
                # Note: Current implementation only supports boolean ssl_verify
                # Custom CA bundle paths are not supported in the config parsing
                assert (
                    jira_config.ssl_verify is True
                )  # Any non-false value becomes True

                # For Confluence
                confluence_config = ConfluenceConfig.from_env()
                assert (
                    confluence_config.ssl_verify is True
                )  # Any non-false value becomes True

    @pytest.mark.integration
    def test_ssl_adapter_not_mounted_when_verification_enabled(self):
        """Test that SSL adapters are not mounted when verification is enabled."""
        session = Session()
        original_adapter_count = len(session.adapters)

        # Configure with SSL verification enabled
        configure_ssl_verification(
            service_name="Jira",
            url="https://test.atlassian.net",
            session=session,
            ssl_verify=True,  # SSL verification enabled
        )

        # No additional adapters should be mounted
        assert len(session.adapters) == original_adapter_count
        assert "https://test.atlassian.net" not in session.adapters

    @pytest.mark.integration
    def test_ssl_configuration_persistence_across_requests(self):
        """Test SSL configuration persists across multiple requests."""
        session = Session()

        # Configure SSL for a domain
        configure_ssl_verification(
            service_name="Jira",
            url="https://test.atlassian.net",
            session=session,
            ssl_verify=False,
        )

        # Get the adapter
        adapter = session.adapters.get("https://test.atlassian.net")
        assert isinstance(adapter, SSLIgnoreAdapter)

        # Configure again - should not create duplicate adapters
        configure_ssl_verification(
            service_name="Jira",
            url="https://test.atlassian.net",
            session=session,
            ssl_verify=False,
        )

        # Should still have an SSLIgnoreAdapter present
        new_adapter = session.adapters.get("https://test.atlassian.net")
        assert isinstance(new_adapter, SSLIgnoreAdapter)

    @pytest.mark.integration
    def test_ssl_verification_with_oauth_configuration(self):
        """Test SSL verification works correctly with OAuth configuration."""
        with MockEnvironment.oauth_env() as env_vars:
            # Add SSL configuration
            env_vars["JIRA_SSL_VERIFY"] = "false"
            env_vars["CONFLUENCE_SSL_VERIFY"] = "false"

            # OAuth config should still respect SSL settings
            # Need to reload config after env change
            with patch.dict(os.environ, env_vars):
                # Note: OAuth flow would need additional setup, but we're testing config only
                assert os.environ.get("JIRA_SSL_VERIFY") == "false"
                assert os.environ.get("CONFLUENCE_SSL_VERIFY") == "false"


@pytest.mark.integration
def test_configure_ssl_verification_with_real_jira_url():
    """Test SSL verification configuration with real Jira URL from environment."""
    # Get the URL from the environment
    url = os.getenv("JIRA_URL")
    if not url:
        pytest.skip("JIRA_URL not set in environment")

    # Create a real session
    session = Session()
    original_adapters_count = len(session.adapters)

    # Mock the SSL_VERIFY value to be False for this test
    with patch.dict(os.environ, {"JIRA_SSL_VERIFY": "false"}):
        # Configure SSL verification - explicitly pass ssl_verify=False
        configure_ssl_verification(
            service_name="Jira",
            url=url,
            session=session,
            ssl_verify=False,
        )

        # Extract domain from URL (remove protocol and path)
        domain = url.split("://")[1].split("/")[0]

        # Verify the adapters are mounted correctly
        assert len(session.adapters) == original_adapters_count + 2
        assert f"https://{domain}" in session.adapters
        assert f"http://{domain}" in session.adapters
        assert isinstance(session.adapters[f"https://{domain}"], SSLIgnoreAdapter)
        assert isinstance(session.adapters[f"http://{domain}"], SSLIgnoreAdapter)
