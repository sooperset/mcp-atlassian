"""Tests for Jira label operations."""

import pytest

from mcp_atlassian.jira.labels import LabelsMixin


@pytest.fixture
def labels_mixin(jira_client):
    """Create a LabelsMixin instance with mocked dependencies."""
    mixin = LabelsMixin(config=jira_client.config)
    mixin.jira = jira_client.jira
    return mixin


def _issue_with_labels(labels: list[str]) -> dict:
    return {"fields": {"labels": labels}}


class TestGetIssueLabels:
    """Tests for get_issue_labels method."""

    def test_returns_labels_for_issue(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(
            ["frontend", "urgent"]
        )

        result = labels_mixin.get_issue_labels("TEST-123")

        labels_mixin.jira.get_issue.assert_called_once_with("TEST-123", fields="labels")
        assert result["issue_key"] == "TEST-123"
        assert result["labels"] == ["frontend", "urgent"]

    def test_returns_empty_list_when_no_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels([])

        result = labels_mixin.get_issue_labels("TEST-123")

        assert result["labels"] == []

    def test_handles_invalid_response_type(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = "unexpected"

        result = labels_mixin.get_issue_labels("TEST-123")

        assert result["issue_key"] == "TEST-123"
        assert result["labels"] == []


class TestAddIssueLabels:
    """Tests for add_issue_labels method."""

    def test_adds_new_labels_preserving_existing(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["existing"])

        result = labels_mixin.add_issue_labels("TEST-123", ["new"])

        assert "new" in result["labels"]
        assert "existing" in result["labels"]
        assert result["added"] == ["new"]

    def test_does_not_duplicate_existing_label(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["frontend"])

        result = labels_mixin.add_issue_labels("TEST-123", ["frontend"])

        assert result["labels"].count("frontend") == 1
        assert result["added"] == []

    def test_calls_update_with_merged_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["a"])

        labels_mixin.add_issue_labels("TEST-123", ["b"])

        labels_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"labels": ["a", "b"]}}
        )

    def test_added_shows_only_truly_new_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(
            ["frontend", "backend"]
        )

        result = labels_mixin.add_issue_labels("TEST-123", ["frontend", "urgent"])

        assert result["added"] == ["urgent"]

    def test_result_labels_are_sorted(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["zebra"])

        result = labels_mixin.add_issue_labels("TEST-123", ["apple"])

        assert result["labels"] == sorted(result["labels"])


class TestRemoveIssueLabels:
    """Tests for remove_issue_labels method."""

    def test_removes_specified_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(
            ["frontend", "urgent", "backend"]
        )

        result = labels_mixin.remove_issue_labels("TEST-123", ["urgent"])

        assert "urgent" not in result["labels"]
        assert "frontend" in result["labels"]
        assert "backend" in result["labels"]
        assert result["removed"] == ["urgent"]

    def test_calls_update_with_remaining_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["a", "b", "c"])

        labels_mixin.remove_issue_labels("TEST-123", ["b"])

        labels_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"labels": ["a", "c"]}}
        )

    def test_reports_not_found_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["frontend"])

        result = labels_mixin.remove_issue_labels(
            "TEST-123", ["frontend", "nonexistent"]
        )

        assert result["removed"] == ["frontend"]
        assert result["not_found"] == ["nonexistent"]

    def test_no_not_found_key_when_all_present(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["frontend"])

        result = labels_mixin.remove_issue_labels("TEST-123", ["frontend"])

        assert "not_found" not in result

    def test_remove_all_labels(self, labels_mixin):
        labels_mixin.jira.get_issue.return_value = _issue_with_labels(["a", "b"])

        result = labels_mixin.remove_issue_labels("TEST-123", ["a", "b"])

        assert result["labels"] == []
        assert result["removed"] == ["a", "b"]


class TestSetIssueLabels:
    """Tests for set_issue_labels method."""

    def test_replaces_labels(self, labels_mixin):
        result = labels_mixin.set_issue_labels("TEST-123", ["new1", "new2"])

        labels_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"labels": ["new1", "new2"]}},
        )
        assert result["issue_key"] == "TEST-123"
        assert result["labels"] == ["new1", "new2"]

    def test_clears_all_labels_with_empty_list(self, labels_mixin):
        result = labels_mixin.set_issue_labels("TEST-123", [])

        labels_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"labels": []}},
        )
        assert result["labels"] == []


class TestGetAvailableLabels:
    """Tests for get_available_labels method."""

    def test_returns_labels_list(self, labels_mixin):
        labels_mixin.jira.get.return_value = {
            "values": ["backend", "frontend", "urgent"],
            "total": 3,
            "startAt": 0,
            "maxResults": 50,
            "isLast": True,
        }

        result = labels_mixin.get_available_labels()

        labels_mixin.jira.get.assert_called_once_with(
            "label", params={"startAt": 0, "maxResults": 50}
        )
        assert result["labels"] == ["backend", "frontend", "urgent"]
        assert result["total"] == 3
        assert result["is_last"] is True

    def test_passes_query_parameter(self, labels_mixin):
        labels_mixin.jira.get.return_value = {
            "values": ["frontend"],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
            "isLast": True,
        }

        labels_mixin.get_available_labels(query="front")

        labels_mixin.jira.get.assert_called_once_with(
            "label", params={"startAt": 0, "maxResults": 50, "query": "front"}
        )

    def test_passes_pagination_parameters(self, labels_mixin):
        labels_mixin.jira.get.return_value = {
            "values": [],
            "total": 100,
            "startAt": 50,
            "maxResults": 25,
            "isLast": False,
        }

        result = labels_mixin.get_available_labels(start_at=50, max_results=25)

        labels_mixin.jira.get.assert_called_once_with(
            "label", params={"startAt": 50, "maxResults": 25}
        )
        assert result["start_at"] == 50
        assert result["is_last"] is False

    def test_handles_invalid_response_type(self, labels_mixin):
        labels_mixin.jira.get.return_value = "unexpected"

        result = labels_mixin.get_available_labels()

        assert result["labels"] == []
        assert result["total"] == 0
        assert result["is_last"] is True
