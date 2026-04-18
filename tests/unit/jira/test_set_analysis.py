from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.set_analysis import _normalize_field_value
from mcp_atlassian.models.jira import JiraSearchResult
from mcp_atlassian.models.jira.issue import JiraIssue


def _make_issue(key: str, **field_overrides: object) -> JiraIssue:
    """Build a minimal JiraIssue with overridable fields."""
    from mcp_atlassian.models.jira.common import (
        JiraIssueType,
        JiraPriority,
        JiraStatus,
        JiraUser,
    )

    defaults: dict[str, object] = {
        "key": key,
        "summary": f"Summary for {key}",
        "status": JiraStatus(name="Open"),
        "issue_type": JiraIssueType(name="Task"),
        "assignee": JiraUser(display_name="Alice"),
        "priority": JiraPriority(name="Medium"),
        "labels": ["backend"],
    }
    defaults.update(field_overrides)
    return JiraIssue(**defaults)  # type: ignore[arg-type]


def _search_result(issues: list[JiraIssue]) -> JiraSearchResult:
    return JiraSearchResult(
        total=len(issues),
        start_at=0,
        max_results=50,
        issues=issues,
    )


class TestNormalizeFieldValue:
    def test_none(self) -> None:
        assert _normalize_field_value(None) is None

    def test_string(self) -> None:
        assert _normalize_field_value("hello") == "hello"

    def test_dict_with_display_name(self) -> None:
        assert _normalize_field_value({"display_name": "Alice"}) == "Alice"

    def test_dict_with_name(self) -> None:
        assert _normalize_field_value({"name": "Open"}) == "Open"

    def test_list_of_strings_sorted(self) -> None:
        result = _normalize_field_value(["z", "a", "m"])
        assert result == ["a", "m", "z"]

    def test_list_of_dicts(self) -> None:
        result = _normalize_field_value([{"name": "B"}, {"name": "A"}])
        assert result == ["A", "B"]


class TestSetAnalysisMixin:
    @pytest.fixture
    def mixin(self, jira_fetcher):
        return jira_fetcher

    def test_compare_disjoint_sets(self, mixin):
        """Sets with no overlap produce only_in_a and only_in_b."""
        issues_a = [_make_issue("A-1"), _make_issue("A-2")]
        issues_b = [_make_issue("B-1")]

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _search_result(issues_a)
            return _search_result(issues_b)

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.compare_issue_sets("project = A", "project = B")

        assert result["set_a_count"] == 2
        assert result["set_b_count"] == 1
        assert len(result["only_in_a"]) == 2
        assert len(result["only_in_b"]) == 1
        assert result["changed"] == []
        assert result["unchanged_count"] == 0

    def test_compare_identical_sets(self, mixin):
        """Same issues with same fields produce unchanged only."""
        issues = [_make_issue("X-1"), _make_issue("X-2")]

        mixin.search_issues = MagicMock(return_value=_search_result(issues))

        result = mixin.compare_issue_sets("q1", "q2")

        assert result["summary"]["only_in_a_count"] == 0
        assert result["summary"]["only_in_b_count"] == 0
        assert result["summary"]["changed_count"] == 0
        assert result["summary"]["unchanged_count"] == 2

    def test_compare_with_field_changes(self, mixin):
        """Issues present in both sets with changed fields."""
        from mcp_atlassian.models.jira.common import JiraStatus

        issue_a = _make_issue("X-1", status=JiraStatus(name="Open"))
        issue_b = _make_issue("X-1", status=JiraStatus(name="Done"))

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _search_result([issue_a])
            return _search_result([issue_b])

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.compare_issue_sets("q1", "q2")

        assert result["summary"]["changed_count"] == 1
        assert result["changed"][0]["key"] == "X-1"
        changes = result["changed"][0]["changes"]
        status_change = next(c for c in changes if c["field"] == "status")
        assert status_change["in_a"] == "Open"
        assert status_change["in_b"] == "Done"

    def test_compare_mixed(self, mixin):
        """Mix of added, removed, changed, and unchanged."""
        from mcp_atlassian.models.jira.common import JiraStatus

        issues_a = [
            _make_issue("X-1", status=JiraStatus(name="Open")),
            _make_issue("X-2"),
            _make_issue("X-3"),
        ]
        issues_b = [
            _make_issue("X-1", status=JiraStatus(name="Done")),
            _make_issue("X-2"),
            _make_issue("X-4"),
        ]

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _search_result(issues_a)
            return _search_result(issues_b)

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.compare_issue_sets("q1", "q2")

        assert result["summary"]["only_in_a_count"] == 1  # X-3
        assert result["summary"]["only_in_b_count"] == 1  # X-4
        assert result["summary"]["changed_count"] == 1  # X-1
        assert result["summary"]["unchanged_count"] == 1  # X-2

    def test_compare_custom_fields(self, mixin):
        """Custom compare_fields restricts which fields are diffed."""
        from mcp_atlassian.models.jira.common import JiraPriority, JiraStatus

        issue_a = _make_issue(
            "X-1",
            status=JiraStatus(name="Open"),
            priority=JiraPriority(name="High"),
        )
        issue_b = _make_issue(
            "X-1",
            status=JiraStatus(name="Done"),
            priority=JiraPriority(name="High"),
        )

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _search_result([issue_a])
            return _search_result([issue_b])

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.compare_issue_sets("q1", "q2", compare_fields=["priority"])
        assert result["summary"]["changed_count"] == 0
        assert result["summary"]["unchanged_count"] == 1

    def test_compare_empty_results(self, mixin):
        """Both queries returning empty."""
        mixin.search_issues = MagicMock(return_value=_search_result([]))

        result = mixin.compare_issue_sets("q1", "q2")

        assert result["set_a_count"] == 0
        assert result["set_b_count"] == 0
        assert result["summary"]["unchanged_count"] == 0

    def test_compare_auth_error(self, mixin):
        """401 raises MCPAtlassianAuthenticationError."""
        mixin.search_issues = MagicMock(
            side_effect=HTTPError(response=Mock(status_code=401))
        )

        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.compare_issue_sets("q1", "q2")

    def test_fetch_all_issues_pagination(self, mixin):
        """_fetch_all_issues pages through results on Server/DC."""
        mixin.config = MagicMock(is_cloud=False)

        page1 = [_make_issue(f"X-{i}") for i in range(50)]
        page2 = [_make_issue(f"X-{i}") for i in range(50, 75)]

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _search_result(page1)
            return _search_result(page2)

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin._fetch_all_issues("q", ["summary"], 100)

        assert len(result) == 75
        assert mixin.search_issues.call_count == 2

    def test_fetch_all_issues_cloud_no_repaging(self, mixin):
        """On Cloud, _fetch_all_issues must not manually re-page."""
        mixin.config = MagicMock(is_cloud=True)

        all_issues = [_make_issue(f"X-{i}") for i in range(80)]
        mixin.search_issues = MagicMock(return_value=_search_result(all_issues))

        result = mixin._fetch_all_issues("q", ["summary"], 200)

        assert len(result) == 80
        assert mixin.search_issues.call_count == 1
