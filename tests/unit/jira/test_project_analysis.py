from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.project_analysis import _project_key_from_issue_key
from mcp_atlassian.models.jira.common import JiraIssueType, JiraStatus
from mcp_atlassian.models.jira.issue import JiraIssue
from mcp_atlassian.models.jira.link import (
    JiraIssueLink,
    JiraIssueLinkType,
    JiraLinkedIssue,
    JiraLinkedIssueFields,
)
from mcp_atlassian.models.jira.search import JiraSearchResult


def _make_link(
    *,
    link_type_name: str = "Blocks",
    inward_key: str | None = None,
    outward_key: str | None = None,
    inward_label: str = "",
    outward_label: str = "",
) -> JiraIssueLink:
    lt = JiraIssueLinkType(
        name=link_type_name, inward=inward_label, outward=outward_label
    )
    inward = (
        JiraLinkedIssue(
            key=inward_key,
            fields=JiraLinkedIssueFields(summary=f"Summary {inward_key}"),
        )
        if inward_key
        else None
    )
    outward = (
        JiraLinkedIssue(
            key=outward_key,
            fields=JiraLinkedIssueFields(summary=f"Summary {outward_key}"),
        )
        if outward_key
        else None
    )
    return JiraIssueLink(type=lt, inward_issue=inward, outward_issue=outward)


def _epic(key: str, links: list[JiraIssueLink] | None = None) -> JiraIssue:
    return JiraIssue(
        key=key,
        summary=f"Epic {key}",
        status=JiraStatus(name="In Progress"),
        issue_type=JiraIssueType(name="Epic"),
        issuelinks=links or [],
    )


def _issue(key: str, links: list[JiraIssueLink] | None = None) -> JiraIssue:
    return JiraIssue(
        key=key,
        summary=f"Issue {key}",
        status=JiraStatus(name="Open"),
        issue_type=JiraIssueType(name="Task"),
        issuelinks=links or [],
    )


def _search_result(issues: list[JiraIssue]) -> JiraSearchResult:
    return JiraSearchResult(
        total=len(issues), start_at=0, max_results=50, issues=issues
    )


class TestProjectKeyFromIssueKey:
    def test_standard(self) -> None:
        assert _project_key_from_issue_key("PROJ-123") == "PROJ"

    def test_multi_segment(self) -> None:
        assert _project_key_from_issue_key("MY-PROJ-45") == "MY-PROJ"

    def test_no_dash(self) -> None:
        assert _project_key_from_issue_key("NODASH") == "NODASH"


class TestProjectAnalysisMixin:
    @pytest.fixture
    def mixin(self, jira_fetcher):
        return jira_fetcher

    # ---- get_project_epic_hierarchy ----

    def test_epic_hierarchy_groups_by_parent(self, mixin):
        """Epics with cross-project inward links group under parent."""
        epics = [
            _epic(
                "PROJ-10",
                [_make_link(inward_key="INIT-1", link_type_name="Split from")],
            ),
            _epic(
                "PROJ-20",
                [_make_link(inward_key="INIT-1", link_type_name="Split from")],
            ),
        ]
        parent_issue = JiraIssue(
            key="INIT-1",
            summary="Initiative A",
            status=JiraStatus(name="Open"),
        )

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if "issuetype = Epic" in jql:
                return _search_result(epics)
            return _search_result([parent_issue])

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert result["total_epics"] == 2
        assert len(result["groups"]) == 1
        group = result["groups"][0]
        assert group["parent"]["key"] == "INIT-1"
        assert len(group["epics"]) == 2

    def test_epic_hierarchy_unlinked_group(self, mixin):
        """Epics with no cross-project parent go into Unlinked."""
        epics = [_epic("PROJ-10")]

        mixin.search_issues = MagicMock(return_value=_search_result(epics))

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert len(result["groups"]) == 1
        assert result["groups"][0]["group_name"] == "Unlinked"

    def test_epic_hierarchy_same_project_link_ignored(self, mixin):
        """Links within the same project are not treated as parents."""
        epics = [
            _epic(
                "PROJ-10",
                [_make_link(inward_key="PROJ-1", link_type_name="Related")],
            ),
        ]
        mixin.search_issues = MagicMock(return_value=_search_result(epics))

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert result["groups"][0]["group_name"] == "Unlinked"

    def test_epic_hierarchy_parent_via_directional_label(self, mixin):
        """Parent detected via type.inward label even when type.name is generic."""
        epics = [
            _epic(
                "PROJ-10",
                [
                    _make_link(
                        inward_key="INIT-1",
                        link_type_name="Hierarchy",
                        inward_label="is child of",
                        outward_label="is parent of",
                    )
                ],
            ),
        ]
        parent_issue = JiraIssue(
            key="INIT-1",
            summary="Initiative A",
            status=JiraStatus(name="Open"),
        )

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if "issuetype = Epic" in jql:
                return _search_result(epics)
            return _search_result([parent_issue])

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert result["total_epics"] == 1
        group = result["groups"][0]
        assert group["parent"]["key"] == "INIT-1"

    def test_epic_hierarchy_parent_via_outward_issue(self, mixin):
        """Parent detected via outward_issue when link type matches."""
        epics = [
            _epic(
                "PROJ-10",
                [
                    _make_link(
                        outward_key="INIT-2",
                        link_type_name="is child of",
                    )
                ],
            ),
        ]
        parent_issue = JiraIssue(
            key="INIT-2",
            summary="Initiative B",
            status=JiraStatus(name="Open"),
        )

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if "issuetype = Epic" in jql:
                return _search_result(epics)
            return _search_result([parent_issue])

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert result["total_epics"] == 1
        group = result["groups"][0]
        assert group["parent"]["key"] == "INIT-2"

    def test_epic_hierarchy_outward_parent_of_not_treated_as_parent(self, mixin):
        """Outward 'is parent of' means we are the parent, not the child."""
        epics = [
            _epic(
                "PROJ-10",
                [
                    _make_link(
                        outward_key="CHILD-1",
                        link_type_name="Hierarchy",
                        inward_label="is child of",
                        outward_label="is parent of",
                    )
                ],
            ),
        ]
        mixin.search_issues = MagicMock(return_value=_search_result(epics))

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert result["groups"][0]["group_name"] == "Unlinked"

    def test_epic_hierarchy_empty(self, mixin):
        """No epics in project."""
        mixin.search_issues = MagicMock(return_value=_search_result([]))

        result = mixin.get_project_epic_hierarchy("PROJ")

        assert result["total_epics"] == 0
        assert result["groups"] == []

    def test_epic_hierarchy_auth_error(self, mixin):
        mixin.search_issues = MagicMock(
            side_effect=HTTPError(response=Mock(status_code=401))
        )
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_project_epic_hierarchy("PROJ")

    # ---- get_cross_project_dependencies ----

    def test_cross_deps_basic(self, mixin):
        """Detects outward and inward cross-project links."""
        issues = [
            _issue(
                "PROJ-1",
                [
                    _make_link(
                        outward_key="OTHER-5",
                        link_type_name="Blocks",
                    ),
                    _make_link(
                        inward_key="THIRD-1",
                        link_type_name="Depends on",
                    ),
                ],
            ),
        ]
        mixin.search_issues = MagicMock(return_value=_search_result(issues))

        result = mixin.get_cross_project_dependencies("PROJ")

        assert result["total_cross_project_links"] == 2
        assert "OTHER" in result["by_project"]
        assert "THIRD" in result["by_project"]

    def test_cross_deps_no_cross_links(self, mixin):
        """All links within the same project → empty result."""
        issues = [
            _issue(
                "PROJ-1",
                [_make_link(outward_key="PROJ-2", link_type_name="Blocks")],
            ),
        ]
        mixin.search_issues = MagicMock(return_value=_search_result(issues))

        result = mixin.get_cross_project_dependencies("PROJ")

        assert result["total_cross_project_links"] == 0
        assert result["by_project"] == {}

    def test_cross_deps_grouped_by_project_and_type(self, mixin):
        """Multiple links group correctly."""
        issues = [
            _issue(
                "PROJ-1",
                [_make_link(outward_key="EXT-1", link_type_name="Blocks")],
            ),
            _issue(
                "PROJ-2",
                [_make_link(outward_key="EXT-2", link_type_name="Blocks")],
            ),
        ]
        mixin.search_issues = MagicMock(return_value=_search_result(issues))

        result = mixin.get_cross_project_dependencies("PROJ")

        ext = result["by_project"]["EXT"]
        assert ext["total_links"] == 2
        assert len(ext["by_link_type"]["Blocks"]) == 2

    def test_cross_deps_auth_error(self, mixin):
        mixin.search_issues = MagicMock(
            side_effect=HTTPError(response=Mock(status_code=401))
        )
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_cross_project_dependencies("PROJ")

    # ---- pagination ----

    def test_fetch_with_pagination(self, mixin):
        """_fetch_project_issues_with_links pages correctly on Server/DC."""
        mixin.config = MagicMock(is_cloud=False)

        page1 = [_issue(f"P-{i}") for i in range(50)]
        page2 = [_issue(f"P-{i}") for i in range(50, 60)]

        call_count = 0

        def fake_search(jql, fields=None, start=0, limit=50, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _search_result(page1)
            return _search_result(page2)

        mixin.search_issues = MagicMock(side_effect=fake_search)

        result = mixin._fetch_project_issues_with_links("key in ()", 100)
        assert len(result) == 60
        assert mixin.search_issues.call_count == 2

    def test_fetch_cloud_no_repaging(self, mixin):
        """On Cloud, _fetch_project_issues_with_links must not re-page."""
        mixin.config = MagicMock(is_cloud=True)

        all_issues = [_issue(f"P-{i}") for i in range(80)]
        mixin.search_issues = MagicMock(return_value=_search_result(all_issues))

        result = mixin._fetch_project_issues_with_links("key in ()", 200)
        assert len(result) == 80
        assert mixin.search_issues.call_count == 1
