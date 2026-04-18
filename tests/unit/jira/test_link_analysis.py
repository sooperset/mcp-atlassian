from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.models.jira.common import JiraIssueType, JiraStatus
from mcp_atlassian.models.jira.issue import JiraIssue
from mcp_atlassian.models.jira.link import (
    JiraIssueLink,
    JiraIssueLinkType,
    JiraLinkedIssue,
    JiraLinkedIssueFields,
)
from mcp_atlassian.models.jira.search import JiraSearchResult


def _link(
    *,
    name: str = "Blocks",
    inward_key: str | None = None,
    outward_key: str | None = None,
    inward_label: str = "",
    outward_label: str = "",
) -> JiraIssueLink:
    lt = JiraIssueLinkType(name=name, inward=inward_label, outward=outward_label)
    inward = (
        JiraLinkedIssue(
            key=inward_key,
            fields=JiraLinkedIssueFields(summary=f"S {inward_key}"),
        )
        if inward_key
        else None
    )
    outward = (
        JiraLinkedIssue(
            key=outward_key,
            fields=JiraLinkedIssueFields(summary=f"S {outward_key}"),
        )
        if outward_key
        else None
    )
    return JiraIssueLink(type=lt, inward_issue=inward, outward_issue=outward)


def _issue(
    key: str,
    links: list[JiraIssueLink] | None = None,
    subtasks: list[dict] | None = None,
) -> JiraIssue:
    return JiraIssue(
        key=key,
        summary=f"Issue {key}",
        status=JiraStatus(name="Open"),
        issue_type=JiraIssueType(name="Task"),
        issuelinks=links or [],
        subtasks=subtasks or [],
    )


def _search(issues: list[JiraIssue]) -> JiraSearchResult:
    return JiraSearchResult(
        total=len(issues), start_at=0, max_results=50, issues=issues
    )


def _issue_store(*issues: JiraIssue) -> dict[str, JiraIssue]:
    return {i.key: i for i in issues}


class TestTraceIssueLinks:
    @pytest.fixture
    def mixin(self, jira_fetcher):
        return jira_fetcher

    def _setup_issues(self, mixin, store: dict[str, JiraIssue]) -> None:
        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            for k, v in store.items():
                if k in jql:
                    return _search([v])
            return _search([])

        mixin.search_issues = MagicMock(side_effect=fake_search)

    def test_single_hop(self, mixin):
        """Trace one issue linked to another."""
        a = _issue("A-1", [_link(outward_key="B-1")])
        b = _issue("B-1")
        self._setup_issues(mixin, _issue_store(a, b))

        result = mixin.trace_issue_links("A-1", max_depth=1)

        assert result["total_nodes"] == 2
        assert result["total_edges"] == 1
        keys = {n["key"] for n in result["nodes"]}
        assert keys == {"A-1", "B-1"}

    def test_depth_respected(self, mixin):
        """BFS stops at max_depth."""
        a = _issue("A-1", [_link(outward_key="B-1")])
        b = _issue("B-1", [_link(outward_key="C-1")])
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.trace_issue_links("A-1", max_depth=1)

        keys = {n["key"] for n in result["nodes"]}
        assert "A-1" in keys
        assert "B-1" in keys
        assert "C-1" not in keys

    def test_cycle_detection(self, mixin):
        """Cycles don't cause infinite loops."""
        a = _issue("A-1", [_link(outward_key="B-1")])
        b = _issue("B-1", [_link(outward_key="A-1")])
        self._setup_issues(mixin, _issue_store(a, b))

        result = mixin.trace_issue_links("A-1", max_depth=5)

        assert result["total_nodes"] == 2

    def test_max_issues_limit(self, mixin):
        """Traversal stops when max_issues reached."""
        a = _issue("A-1", [_link(outward_key="B-1"), _link(outward_key="C-1")])
        b = _issue("B-1")
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.trace_issue_links("A-1", max_depth=5, max_issues=2)

        assert result["total_nodes"] <= 2

    def test_type_filter(self, mixin):
        """Only follows specified link types."""
        a = _issue(
            "A-1",
            [
                _link(outward_key="B-1", name="Blocks"),
                _link(outward_key="C-1", name="Related"),
            ],
        )
        b = _issue("B-1")
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.trace_issue_links(
            "A-1", max_depth=2, link_type_filter=["Blocks"]
        )

        keys = {n["key"] for n in result["nodes"]}
        assert "B-1" in keys
        assert "C-1" not in keys

    def test_direction_filter(self, mixin):
        """Only follows specified direction."""
        a = _issue(
            "A-1",
            [
                _link(outward_key="B-1", name="Blocks"),
                _link(inward_key="C-1", name="Related"),
            ],
        )
        b = _issue("B-1")
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.trace_issue_links("A-1", max_depth=2, direction_filter="outward")

        keys = {n["key"] for n in result["nodes"]}
        assert "B-1" in keys
        assert "C-1" not in keys

    def test_invalid_direction_filter(self, mixin):
        """Invalid direction_filter raises ValueError."""
        with pytest.raises(ValueError, match="direction_filter"):
            mixin.trace_issue_links("A-1", direction_filter="OUTWARD")

    def test_edges_only_reference_visited_nodes(self, mixin):
        """Edges to unvisited nodes (due to max_issues) are filtered out."""
        a = _issue("A-1", [_link(outward_key="B-1"), _link(outward_key="C-1")])
        b = _issue("B-1")
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.trace_issue_links("A-1", max_depth=5, max_issues=1)

        visited_keys = {n["key"] for n in result["nodes"]}
        for edge in result["edges"]:
            assert edge["source"] in visited_keys
            assert edge["target"] in visited_keys

    def test_auth_error(self, mixin):
        mixin.search_issues = MagicMock(
            side_effect=HTTPError(response=Mock(status_code=401))
        )
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.trace_issue_links("A-1")


class TestGetIssueTree:
    @pytest.fixture
    def mixin(self, jira_fetcher):
        return jira_fetcher

    def _setup_issues(self, mixin, store: dict[str, JiraIssue]) -> None:
        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            for k, v in store.items():
                if k in jql:
                    return _search([v])
            return _search([])

        mixin.search_issues = MagicMock(side_effect=fake_search)

    def test_containment_only(self, mixin):
        """Tree follows containment links, not non-containment."""
        a = _issue(
            "A-1",
            [
                _link(outward_key="B-1", name="is parent of"),
                _link(outward_key="C-1", name="Related"),
            ],
        )
        b = _issue("B-1")
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        child_keys = [ch["key"] for ch in result["root"]["children"]]
        assert "B-1" in child_keys
        assert "C-1" not in child_keys

    def test_cross_links_annotated(self, mixin):
        """Non-containment links appear in cross_links."""
        a = _issue(
            "A-1",
            [_link(outward_key="C-1", name="Related")],
        )
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, c))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        assert len(result["cross_links"]) == 1
        assert result["cross_links"][0]["target"] == "C-1"

    def test_subtasks_as_children(self, mixin):
        """Subtasks appear as tree children."""
        a = _issue("A-1", subtasks=[{"key": "A-2"}])
        a2 = _issue("A-2")
        self._setup_issues(mixin, _issue_store(a, a2))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        child_keys = [ch["key"] for ch in result["root"]["children"]]
        assert "A-2" in child_keys

    def test_max_depth_respected(self, mixin):
        """Tree doesn't recurse past max_depth."""
        a = _issue("A-1", [_link(outward_key="B-1", name="is parent of")])
        b = _issue("B-1", [_link(outward_key="C-1", name="is parent of")])
        c = _issue("C-1")
        self._setup_issues(mixin, _issue_store(a, b, c))

        result = mixin.get_issue_tree("A-1", max_depth=1)

        assert result["root"]["children"][0]["key"] == "B-1"
        assert result["root"]["children"][0]["children"] == []

    def test_cycle_in_tree(self, mixin):
        """Cycles in containment links don't cause infinite recursion."""
        a = _issue("A-1", [_link(outward_key="B-1", name="is parent of")])
        b = _issue("B-1", [_link(outward_key="A-1", name="is parent of")])
        self._setup_issues(mixin, _issue_store(a, b))

        result = mixin.get_issue_tree("A-1", max_depth=5)

        assert result["total_nodes"] == 2

    def test_hierarchy_via_directional_labels(self, mixin):
        """Containment detected via type.outward even when type.name is generic."""
        a = _issue(
            "A-1",
            [
                _link(
                    outward_key="B-1",
                    name="Hierarchy",
                    outward_label="is parent of",
                    inward_label="is child of",
                ),
            ],
        )
        b = _issue("B-1")
        self._setup_issues(mixin, _issue_store(a, b))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        child_keys = [ch["key"] for ch in result["root"]["children"]]
        assert "B-1" in child_keys

    def test_split_to_treated_as_child(self, mixin):
        """outward 'Split to' links are containment — target is a child."""
        a = _issue(
            "A-1",
            [
                _link(
                    outward_key="B-1",
                    name="Issue split",
                    outward_label="Split to",
                    inward_label="Split from",
                ),
            ],
        )
        b = _issue("B-1")
        self._setup_issues(mixin, _issue_store(a, b))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        child_keys = [ch["key"] for ch in result["root"]["children"]]
        assert "B-1" in child_keys

    def test_split_from_not_treated_as_child(self, mixin):
        """inward 'Split from' means the inward issue is our parent, not child."""
        a = _issue(
            "A-1",
            [
                _link(
                    inward_key="P-1",
                    name="Issue split",
                    outward_label="Split to",
                    inward_label="Split from",
                ),
            ],
        )
        p = _issue("P-1")
        self._setup_issues(mixin, _issue_store(a, p))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        child_keys = [ch["key"] for ch in result["root"]["children"]]
        assert "P-1" not in child_keys

    def test_inward_child_of_not_treated_as_child(self, mixin):
        """inward_issue with inward='is child of' is our parent, not child."""
        a = _issue(
            "A-1",
            [
                _link(
                    inward_key="P-1",
                    name="Hierarchy",
                    outward_label="is parent of",
                    inward_label="is child of",
                ),
            ],
        )
        p = _issue("P-1")
        self._setup_issues(mixin, _issue_store(a, p))

        result = mixin.get_issue_tree("A-1", max_depth=2)

        child_keys = [ch["key"] for ch in result["root"]["children"]]
        assert "P-1" not in child_keys
        cross_targets = [cl["target"] for cl in result["cross_links"]]
        assert "P-1" in cross_targets

    def test_auth_error(self, mixin):
        mixin.search_issues = MagicMock(
            side_effect=HTTPError(response=Mock(status_code=401))
        )
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_issue_tree("A-1")
