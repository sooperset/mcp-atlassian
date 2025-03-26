"""Integration tests for SSL verification functionality."""

import os
from unittest.mock import patch

import pytest
from requests.sessions import Session

from mcp_atlassian.utils.ssl import SSLIgnoreAdapter, configure_ssl_verification


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
