"""Tests for the URL utilities module."""

from mcp_atlassian.utils.urls import is_atlassian_cloud_url


def test_is_atlassian_cloud_url_empty():
    """Test that is_atlassian_cloud_url returns False for empty URL."""
    assert is_atlassian_cloud_url("") is False
    assert is_atlassian_cloud_url(None) is False


def test_is_atlassian_cloud_url_cloud():
    """Test that is_atlassian_cloud_url returns True for Atlassian Cloud URLs."""
    # Test standard Atlassian Cloud URLs
    assert is_atlassian_cloud_url("https://example.atlassian.net") is True
    assert is_atlassian_cloud_url("https://company.atlassian.net/wiki") is True
    assert is_atlassian_cloud_url("https://subdomain.atlassian.net/jira") is True
    assert is_atlassian_cloud_url("http://other.atlassian.net") is True

    # Test Jira Cloud specific domains
    assert is_atlassian_cloud_url("https://company.jira.com") is True
    assert is_atlassian_cloud_url("https://team.jira-dev.com") is True


def test_is_atlassian_cloud_url_server():
    """Test that is_atlassian_cloud_url returns False for Atlassian Server/Data Center URLs."""
    # Test with various server/data center domains
    assert is_atlassian_cloud_url("https://jira.example.com") is False
    assert is_atlassian_cloud_url("https://confluence.company.org") is False
    assert is_atlassian_cloud_url("https://jira.internal") is False


def test_is_atlassian_cloud_url_localhost():
    """Test that is_atlassian_cloud_url returns False for localhost URLs."""
    # Test with localhost
    assert is_atlassian_cloud_url("http://localhost") is False
    assert is_atlassian_cloud_url("http://localhost:8080") is False
    assert is_atlassian_cloud_url("https://localhost/jira") is False


def test_is_atlassian_cloud_url_ip_addresses():
    """Test that is_atlassian_cloud_url returns False for IP-based URLs."""
    # Test with IP addresses
    assert is_atlassian_cloud_url("http://127.0.0.1") is False
    assert is_atlassian_cloud_url("http://127.0.0.1:8080") is False
    assert is_atlassian_cloud_url("https://192.168.1.100") is False
    assert is_atlassian_cloud_url("https://10.0.0.1") is False
    assert is_atlassian_cloud_url("https://172.16.0.1") is False
    assert is_atlassian_cloud_url("https://172.31.255.254") is False


def test_is_atlassian_cloud_url_with_protocols():
    """Test that is_atlassian_cloud_url works with different protocols."""
    # Test with different protocols
    assert is_atlassian_cloud_url("https://example.atlassian.net") is True
    assert is_atlassian_cloud_url("http://example.atlassian.net") is True
    assert (
        is_atlassian_cloud_url("ftp://example.atlassian.net") is True
    )  # URL parsing still works
