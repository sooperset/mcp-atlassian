from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.structures import StructuresMixin
from mcp_atlassian.models.jira.common import (
    JiraIssueType,
    JiraStatus,
    JiraStatusCategory,
)
from mcp_atlassian.models.jira.issue import JiraIssue
from mcp_atlassian.models.jira.project import JiraProject
from mcp_atlassian.models.jira.search import JiraSearchResult


def _resolved_issue(
    issue_id: str,
    key: str,
    summary: str = "S",
    issue_type: str = "Task",
    status: str = "Open",
    status_category: str = "To Do",
    project: str = "PROJ",
) -> JiraIssue:
    """Build a JiraIssue suitable for Structure batch resolution."""
    return JiraIssue(
        id=issue_id,
        key=key,
        summary=summary,
        issue_type=JiraIssueType(name=issue_type),
        status=JiraStatus(
            name=status,
            category=JiraStatusCategory(name=status_category),
        ),
        project=JiraProject(key=project),
    )


def _search_result(issues: list[JiraIssue]) -> JiraSearchResult:
    return JiraSearchResult(
        total=len(issues), start_at=0, max_results=50, issues=issues
    )


class TestStructuresMixin:
    @pytest.fixture
    def mixin(self, jira_fetcher):
        return jira_fetcher

    # ---- get_structure ----

    def test_get_structure_success(self, mixin):
        mixin.jira.get.return_value = {
            "id": 585,
            "name": "My Structure",
            "description": "A board",
            "editable": True,
            "isArchived": False,
        }

        result = mixin.get_structure("585")

        assert result["id"] == 585
        assert result["name"] == "My Structure"
        assert result["editable"] is True

    def test_get_structure_invalid_response(self, mixin):
        mixin.jira.get.return_value = "bad"

        result = mixin.get_structure("585")

        assert result["error"] == "Invalid response"

    def test_get_structure_auth_error(self, mixin):
        mixin.jira.get.side_effect = HTTPError(response=Mock(status_code=401))
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_structure("585")

    # ---- get_structure_forest ----

    def test_get_structure_forest_success(self, mixin):
        mixin.jira.post.return_value = {
            "formula": "1:0:100:0,2:1:200:0,3:1:300:0",
            "version": 42,
        }

        result = mixin.get_structure_forest("585")

        assert result["total_rows"] == 3
        assert result["rows"][0]["depth"] == 0
        assert result["rows"][0]["item_id"] == "100"
        assert result["rows"][1]["depth"] == 1
        assert result["version"] == 42

    def test_get_structure_forest_invalid_response(self, mixin):
        mixin.jira.post.return_value = {"no_formula": True}

        result = mixin.get_structure_forest("585")

        assert result["error"] == "Invalid response"

    def test_get_structure_forest_auth_error(self, mixin):
        mixin.jira.post.side_effect = HTTPError(response=Mock(status_code=401))
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_structure_forest("585")

    # ---- _parse_formula ----

    def test_parse_formula_issue_rows(self):
        rows = StructuresMixin._parse_formula("1:0:100:0,2:1:200:0")
        assert len(rows) == 2
        assert rows[0] == {
            "row_id": "1",
            "depth": 0,
            "item_id": "100",
            "item_type": "0",
            "row_type": "issue",
        }

    def test_parse_formula_generator_rows(self):
        rows = StructuresMixin._parse_formula("10:2:gen/abc")
        assert len(rows) == 1
        assert rows[0]["row_type"] == "generator"
        assert rows[0]["item_ref"] == "gen/abc"

    def test_parse_formula_empty(self):
        assert StructuresMixin._parse_formula("") == []

    def test_parse_formula_mixed(self):
        rows = StructuresMixin._parse_formula("1:0:100:0,2:1:gen/x,3:0:200:0")
        assert len(rows) == 3
        assert rows[0]["row_type"] == "issue"
        assert rows[1]["row_type"] == "generator"
        assert rows[2]["row_type"] == "issue"

    # ---- get_structure_issues ----

    def test_get_structure_issues_success(self, mixin):
        mixin.jira.get.return_value = {
            "id": 585,
            "name": "Board",
            "description": "",
            "editable": True,
            "isArchived": False,
        }
        mixin.jira.post.return_value = {
            "formula": "1:0:100:0,2:1:200:0",
            "version": 1,
        }
        mixin.search_issues = MagicMock(
            return_value=_search_result(
                [
                    _resolved_issue(
                        "100",
                        "PROJ-1",
                        summary="Top level",
                        issue_type="Epic",
                    ),
                    _resolved_issue(
                        "200",
                        "PROJ-2",
                        summary="Child",
                        issue_type="Story",
                        status="Done",
                        status_category="Done",
                    ),
                ]
            )
        )

        result = mixin.get_structure_issues("585")

        assert result["total_items"] == 2
        assert result["resolved_count"] == 2
        assert result["items"][0]["key"] == "PROJ-1"
        assert result["items"][0]["depth"] == 0
        assert result["items"][1]["key"] == "PROJ-2"
        assert result["items"][1]["depth"] == 1
        assert "partial" not in result

    def test_get_structure_issues_with_max_depth(self, mixin):
        mixin.jira.get.return_value = {
            "id": 1,
            "name": "B",
            "description": "",
        }
        mixin.jira.post.return_value = {
            "formula": "1:0:100:0,2:1:200:0,3:2:300:0",
            "version": 1,
        }
        mixin.search_issues = MagicMock(
            return_value=_search_result(
                [
                    _resolved_issue("100", "P-1"),
                    _resolved_issue("200", "P-2"),
                ]
            )
        )

        result = mixin.get_structure_issues("1", max_depth=1)

        assert result["total_items"] == 2
        depths = [i["depth"] for i in result["items"]]
        assert all(d <= 1 for d in depths)

    def test_get_structure_issues_auth_error(self, mixin):
        mixin.jira.get.side_effect = HTTPError(response=Mock(status_code=401))
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_structure_issues("585")

    def test_get_structure_issues_uses_search_issues(self, mixin):
        """Resolution goes through search_issues (respects projects_filter)."""
        mixin.jira.get.return_value = {
            "id": 1,
            "name": "B",
            "description": "",
        }
        mixin.jira.post.return_value = {
            "formula": "1:0:100:0",
            "version": 1,
        }
        mixin.search_issues = MagicMock(
            return_value=_search_result([_resolved_issue("100", "P-1")])
        )

        mixin.get_structure_issues("1")

        mixin.search_issues.assert_called_once()
        call_args = mixin.search_issues.call_args
        jql_arg = call_args.kwargs.get(
            "jql", call_args.args[0] if call_args.args else ""
        )
        assert "id in" in jql_arg

    def test_get_structure_issues_partial_failure(self, mixin):
        """Failed batch surfaces partial=True and unresolved placeholders."""
        mixin.jira.get.return_value = {
            "id": 1,
            "name": "B",
            "description": "",
        }
        mixin.jira.post.return_value = {
            "formula": "1:0:100:0,2:1:200:0",
            "version": 1,
        }
        mixin.search_issues = MagicMock(side_effect=RuntimeError("connection lost"))

        result = mixin.get_structure_issues("1")

        assert result["partial"] is True
        assert result["unresolved_count"] == 2
        assert result["resolved_count"] == 0
        assert any("[unresolved]" == i["summary"] for i in result["items"])
        for item in result["items"]:
            assert "id=" not in item["summary"]
