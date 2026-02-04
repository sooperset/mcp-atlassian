"""Tests for smart routing tools."""

import pytest

from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.tool_router import detect_jira_instance, extract_issue_key


class TestExtractIssueKey:
    """Test issue key extraction from URLs and text."""

    def test_extract_from_url(self):
        """Extract issue key from Jira URL."""
        url = "https://justworks-tech.atlassian.net/browse/INFRAOPS-15157"
        assert extract_issue_key(url) == "INFRAOPS-15157"

    def test_extract_from_different_domain(self):
        """Extract issue key from different Jira domain."""
        url = "https://justworks.atlassian.net/browse/PROJ-123"
        assert extract_issue_key(url) == "PROJ-123"

    def test_extract_standalone_key(self):
        """Extract standalone issue key."""
        assert extract_issue_key("INFRAOPS-15157") == "INFRAOPS-15157"
        assert extract_issue_key("PROJ-123") == "PROJ-123"
        assert extract_issue_key("ABC-1") == "ABC-1"

    def test_extract_from_text(self):
        """Extract issue key from text containing the key."""
        text = "See issue INFRAOPS-15157 for details"
        assert extract_issue_key(text) == "INFRAOPS-15157"

    def test_no_match_returns_input(self):
        """If no pattern matches, return input as-is."""
        assert extract_issue_key("not-a-key") == "not-a-key"
        assert extract_issue_key("123") == "123"


class TestDetectJiraInstance:
    """Test Jira instance detection."""

    @pytest.fixture
    def jira_configs(self):
        """Create test Jira configurations."""
        return {
            "": JiraConfig(
                url="https://justworks.atlassian.net",
                auth_type="basic",
                username="test@example.com",
                api_token="token1",
            ),
            "tech": JiraConfig(
                url="https://justworks-tech.atlassian.net",
                auth_type="basic",
                username="test@example.com",
                api_token="token2",
            ),
        }

    def test_detect_from_tech_url(self, jira_configs):
        """Detect tech instance from URL."""
        url = "https://justworks-tech.atlassian.net/browse/INFRAOPS-15157"
        assert detect_jira_instance(url, jira_configs) == "tech"

    def test_detect_from_primary_url(self, jira_configs):
        """Detect primary instance from URL."""
        url = "https://justworks.atlassian.net/browse/PROJ-123"
        assert detect_jira_instance(url, jira_configs) == ""

    def test_detect_from_infraops_key(self, jira_configs):
        """Detect tech instance from INFRAOPS issue key."""
        assert detect_jira_instance("INFRAOPS-15157", jira_configs) == "tech"
        assert detect_jira_instance("INFRAOPS-1", jira_configs) == "tech"

    def test_default_to_primary(self, jira_configs):
        """Default to primary instance for unknown patterns."""
        assert detect_jira_instance("PROJ-123", jira_configs) == ""
        assert detect_jira_instance("UNKNOWN-456", jira_configs) == ""

    def test_detect_from_partial_url(self, jira_configs):
        """Detect instance from partial URL."""
        assert (
            detect_jira_instance("justworks-tech.atlassian.net", jira_configs) == "tech"
        )

    def test_single_instance(self):
        """With single instance, always return primary."""
        single_config = {
            "": JiraConfig(
                url="https://justworks.atlassian.net",
                auth_type="basic",
                username="test@example.com",
                api_token="token1",
            )
        }
        assert detect_jira_instance("INFRAOPS-15157", single_config) == ""
        assert (
            detect_jira_instance(
                "https://justworks-tech.atlassian.net/browse/INFRAOPS-15157",
                single_config,
            )
            == ""
        )


class TestRouterToolIntegration:
    """Integration tests for router tools.

    These tests verify the router tools work correctly when registered.
    Note: Full E2E tests require running server, these test the logic.
    """

    def test_router_detects_correct_instance(self):
        """Test that router logic correctly identifies instances."""
        configs = {
            "": JiraConfig(
                url="https://justworks.atlassian.net",
                auth_type="basic",
                username="test@example.com",
                api_token="token1",
            ),
            "tech": JiraConfig(
                url="https://justworks-tech.atlassian.net",
                auth_type="basic",
                username="test@example.com",
                api_token="token2",
            ),
        }

        # Test various input patterns
        test_cases = [
            # (input, expected_instance)
            ("https://justworks-tech.atlassian.net/browse/INFRAOPS-15157", "tech"),
            ("INFRAOPS-15157", "tech"),
            ("https://justworks.atlassian.net/browse/PROJ-123", ""),
            ("PROJ-123", ""),
            ("UNKNOWN-456", ""),
        ]

        for input_text, expected_instance in test_cases:
            result = detect_jira_instance(input_text, configs)
            assert (
                result == expected_instance
            ), f"Failed for input: {input_text}, expected {expected_instance}, got {result}"

    def test_issue_key_extraction_comprehensive(self):
        """Test comprehensive issue key extraction scenarios."""
        test_cases = [
            # (input, expected_key)
            ("https://justworks-tech.atlassian.net/browse/INFRAOPS-15157", "INFRAOPS-15157"),
            ("INFRAOPS-15157", "INFRAOPS-15157"),
            ("Check PROJ-123 for details", "PROJ-123"),
            ("Multiple: ABC-1 and XYZ-999", "ABC-1"),  # Returns first match
            ("PROJ-123", "PROJ-123"),
        ]

        for input_text, expected_key in test_cases:
            result = extract_issue_key(input_text)
            assert (
                result == expected_key
            ), f"Failed for input: {input_text}, expected {expected_key}, got {result}"
