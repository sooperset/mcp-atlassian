"""Unit tests for authentication utilities."""

import pytest
from requests import Session

from mcp_atlassian.utils.auth import configure_server_pat_auth


class TestAuthUtils:
    """Test authentication utility functions."""

    def test_configure_server_pat_auth(self):
        """Test Bearer authentication configuration for Server/DC PATs."""
        session = Session()
        pat_token = "test-personal-access-token"
        
        # Configure Bearer auth
        configure_server_pat_auth(session, pat_token)
        
        # Verify Bearer header is set
        assert session.headers["Authorization"] == f"Bearer {pat_token}"
    
    def test_configure_server_pat_auth_overwrites_existing(self):
        """Test that Bearer auth overwrites any existing Authorization header."""
        session = Session()
        # Set an existing auth header
        session.headers["Authorization"] = "Basic existing-auth"
        
        pat_token = "new-pat-token"
        configure_server_pat_auth(session, pat_token)
        
        # Verify Bearer header replaced the old one
        assert session.headers["Authorization"] == f"Bearer {pat_token}"


class TestCloudVsServerPAT:
    """Test PAT authentication differences between Cloud and Server/DC."""

    @pytest.mark.parametrize(
        "url,expected_is_cloud",
        [
            ("https://example.atlassian.net", True),
            ("https://jira.company.com", False),
            ("https://confluence.internal.org", False),
            ("http://localhost:8080", False),
            ("https://test-instance.atlassian.net/wiki", True),
        ],
    )
    def test_cloud_detection(self, url, expected_is_cloud):
        """Test that Cloud vs Server/DC detection works correctly."""
        from mcp_atlassian.utils.urls import is_atlassian_cloud_url
        
        assert is_atlassian_cloud_url(url) == expected_is_cloud
