"""Tests for Jira watcher operations."""

import pytest

from mcp_atlassian.jira.watchers import WatchersMixin


class TestGetIssueWatchers:
    """Tests for get_issue_watchers method."""

    @pytest.fixture
    def watchers_mixin(self, jira_client):
        """Create a WatchersMixin instance with mocked dependencies."""
        mixin = WatchersMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    def test_get_watchers_returns_watcher_list(self, watchers_mixin):
        """Test getting watchers for an issue."""
        mock_result = {
            "watchCount": 2,
            "isWatching": True,
            "watchers": [
                {
                    "accountId": "abc123",
                    "displayName": "Alice",
                    "emailAddress": "alice@example.com",
                    "avatarUrls": {"48x48": "https://avatar/alice"},
                },
                {
                    "accountId": "def456",
                    "displayName": "Bob",
                    "emailAddress": "bob@example.com",
                    "avatarUrls": {"48x48": "https://avatar/bob"},
                },
            ],
        }
        watchers_mixin.jira.issue_get_watchers.return_value = mock_result

        result = watchers_mixin.get_issue_watchers("TEST-123")

        watchers_mixin.jira.issue_get_watchers.assert_called_once_with("TEST-123")
        assert result["issue_key"] == "TEST-123"
        assert result["watcher_count"] == 2
        assert result["is_watching"] is True
        assert len(result["watchers"]) == 2
        assert result["watchers"][0]["display_name"] == "Alice"
        assert result["watchers"][1]["display_name"] == "Bob"

    def test_get_watchers_uses_jira_user_model(self, watchers_mixin):
        """Test that watchers are processed through JiraUser model."""
        mock_result = {
            "watchCount": 1,
            "isWatching": False,
            "watchers": [
                {
                    "accountId": "abc123",
                    "name": "alice",
                    "displayName": "Alice Smith",
                    "emailAddress": "alice@example.com",
                    "avatarUrls": {"48x48": "https://avatar/alice"},
                },
            ],
        }
        watchers_mixin.jira.issue_get_watchers.return_value = mock_result

        result = watchers_mixin.get_issue_watchers("TEST-123")

        watcher = result["watchers"][0]
        assert watcher["display_name"] == "Alice Smith"
        assert watcher["name"] == "alice"
        assert watcher["email"] == "alice@example.com"
        assert watcher["avatar_url"] == "https://avatar/alice"

    def test_get_watchers_empty_list(self, watchers_mixin):
        """Test getting watchers when no one is watching."""
        mock_result = {
            "watchCount": 0,
            "isWatching": False,
            "watchers": [],
        }
        watchers_mixin.jira.issue_get_watchers.return_value = mock_result

        result = watchers_mixin.get_issue_watchers("TEST-123")

        assert result["issue_key"] == "TEST-123"
        assert result["watcher_count"] == 0
        assert result["is_watching"] is False
        assert result["watchers"] == []

    def test_get_watchers_invalid_response(self, watchers_mixin):
        """Test graceful handling of unexpected response type."""
        watchers_mixin.jira.issue_get_watchers.return_value = "unexpected string"

        result = watchers_mixin.get_issue_watchers("TEST-123")

        assert result["issue_key"] == "TEST-123"
        assert result["watcher_count"] == 0
        assert result["is_watching"] is False
        assert result["watchers"] == []

    def test_get_watchers_count_fallback(self, watchers_mixin):
        """Test that watcher count falls back to len(watchers)."""
        mock_result = {
            "isWatching": False,
            "watchers": [
                {"displayName": "Alice"},
                {"displayName": "Bob"},
            ],
        }
        watchers_mixin.jira.issue_get_watchers.return_value = mock_result

        result = watchers_mixin.get_issue_watchers("TEST-123")

        assert result["watcher_count"] == 2


class TestAddWatcher:
    """Tests for add_watcher method."""

    @pytest.fixture
    def watchers_mixin(self, jira_client):
        """Create a WatchersMixin instance with mocked dependencies."""
        mixin = WatchersMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    def test_add_watcher_success(self, watchers_mixin):
        """Test adding a watcher to an issue."""
        watchers_mixin.jira.issue_add_watcher.return_value = None

        result = watchers_mixin.add_watcher("TEST-123", "abc123")

        assert result["success"] is True
        assert result["issue_key"] == "TEST-123"
        assert result["user"] == "abc123"
        assert "abc123" in result["message"]

    def test_add_watcher_calls_correct_api(self, watchers_mixin):
        """Test that issue_add_watcher is called with correct args."""
        watchers_mixin.jira.issue_add_watcher.return_value = None

        watchers_mixin.add_watcher("PROJ-456", "user-id-789")

        watchers_mixin.jira.issue_add_watcher.assert_called_once_with(
            "PROJ-456", "user-id-789"
        )


class TestRemoveWatcher:
    """Tests for remove_watcher method."""

    @pytest.fixture
    def watchers_mixin(self, jira_client):
        """Create a WatchersMixin instance with mocked dependencies."""
        mixin = WatchersMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    def test_remove_watcher_with_account_id(self, watchers_mixin):
        """Test removing a watcher using account ID (Cloud)."""
        watchers_mixin.jira.issue_delete_watcher.return_value = None

        result = watchers_mixin.remove_watcher("TEST-123", account_id="abc123")

        assert result["success"] is True
        assert result["issue_key"] == "TEST-123"
        assert result["user"] == "abc123"
        watchers_mixin.jira.issue_delete_watcher.assert_called_once_with(
            "TEST-123", user=None, account_id="abc123"
        )

    def test_remove_watcher_with_username(self, watchers_mixin):
        """Test removing a watcher using username (Server/DC)."""
        watchers_mixin.jira.issue_delete_watcher.return_value = None

        result = watchers_mixin.remove_watcher("TEST-123", username="jdoe")

        assert result["success"] is True
        assert result["issue_key"] == "TEST-123"
        assert result["user"] == "jdoe"
        watchers_mixin.jira.issue_delete_watcher.assert_called_once_with(
            "TEST-123", user="jdoe", account_id=None
        )

    def test_remove_watcher_no_identifier_raises_error(self, watchers_mixin):
        """Test that ValueError is raised when no identifier provided."""
        with pytest.raises(
            ValueError, match="Either username or account_id must be provided"
        ):
            watchers_mixin.remove_watcher("TEST-123")

    def test_remove_watcher_prefers_account_id_display(self, watchers_mixin):
        """Test that account_id is used for display when both provided."""
        watchers_mixin.jira.issue_delete_watcher.return_value = None

        result = watchers_mixin.remove_watcher(
            "TEST-123", username="jdoe", account_id="abc123"
        )

        assert result["user"] == "abc123"
