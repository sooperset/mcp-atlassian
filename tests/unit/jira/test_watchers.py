"""Tests for Jira watchers functionality."""

from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.watchers import WatchersMixin


class TestWatchersMixin:
    """Test cases for WatchersMixin."""

    @pytest.fixture
    def watchers_mixin(self, mock_config, mock_atlassian_jira):
        """Create a WatchersMixin instance with mocked jira client."""
        mixin = WatchersMixin(config=mock_config)
        mixin.jira = mock_atlassian_jira
        return mixin

    def test_add_watcher_success(self, watchers_mixin):
        """Test successful addition of a watcher."""
        watchers_mixin.jira.post.return_value = None
        result = watchers_mixin.add_watcher("TEST-1", "user1")
        
        assert result["success"] is True
        assert result["issue_key"] == "TEST-1"
        assert result["user"] == "user1"
        assert "Watcher 'user1' added to issue TEST-1" in result["message"]
        watchers_mixin.jira.post.assert_called_once_with(
            "rest/api/3/issue/TEST-1/watchers", json="user1"
        )

    def test_add_watcher_missing_issue_key(self, watchers_mixin):
        """Test error when issue key is missing."""
        with pytest.raises(ValueError, match="Issue key is required"):
            watchers_mixin.add_watcher("", "user1")

    def test_add_watcher_missing_user(self, watchers_mixin):
        """Test error when user is missing."""
        with pytest.raises(ValueError, match="User is required"):
            watchers_mixin.add_watcher("TEST-1", "")

    def test_add_watcher_authentication_error(self, watchers_mixin):
        """Test authentication error when adding a watcher."""
        error = HTTPError(response=Mock(status_code=401))
        watchers_mixin.jira.post.side_effect = error

        with pytest.raises(MCPAtlassianAuthenticationError):
            watchers_mixin.add_watcher("TEST-1", "user1")

    def test_add_watcher_generic_error(self, watchers_mixin):
        """Test generic error when adding a watcher."""
        watchers_mixin.jira.post.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            watchers_mixin.add_watcher("TEST-1", "user1")

    def test_remove_watcher_success(self, watchers_mixin):
        """Test successful removal of a watcher."""
        watchers_mixin.jira.delete.return_value = None
        result = watchers_mixin.remove_watcher("TEST-1", "user1")
        
        assert result["success"] is True
        assert result["issue_key"] == "TEST-1"
        assert result["user"] == "user1"
        assert "Watcher 'user1' removed from issue TEST-1" in result["message"]
        watchers_mixin.jira.delete.assert_called_once_with(
            "rest/api/3/issue/TEST-1/watchers", params={"accountId": "user1"}
        )

    def test_remove_watcher_missing_issue_key(self, watchers_mixin):
        """Test error when issue key is missing."""
        with pytest.raises(ValueError, match="Issue key is required"):
            watchers_mixin.remove_watcher("", "user1")

    def test_remove_watcher_missing_user(self, watchers_mixin):
        """Test error when user is missing."""
        with pytest.raises(ValueError, match="User is required"):
            watchers_mixin.remove_watcher("TEST-1", "")

    def test_remove_watcher_authentication_error(self, watchers_mixin):
        """Test authentication error when removing a watcher."""
        error = HTTPError(response=Mock(status_code=401))
        watchers_mixin.jira.delete.side_effect = error

        with pytest.raises(MCPAtlassianAuthenticationError):
            watchers_mixin.remove_watcher("TEST-1", "user1")

    def test_remove_watcher_generic_error(self, watchers_mixin):
        """Test generic error when removing a watcher."""
        watchers_mixin.jira.delete.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            watchers_mixin.remove_watcher("TEST-1", "user1") 