"""Module for Jira project-level analysis operations."""

import logging
from collections import defaultdict
from typing import Any

from requests.exceptions import HTTPError

from ..models.jira import JiraSearchResult
from ..utils.decorators import handle_auth_errors
from .client import JiraClient
from .constants import CHILD_OF_PHRASES

logger = logging.getLogger("mcp-jira")

_SERVER_DC_PAGE_SIZE = 50

_LINK_FIELDS = [
    "summary",
    "status",
    "issuetype",
    "issuelinks",
    "parent",
]


def _project_key_from_issue_key(issue_key: str) -> str:
    """Extract the project key portion of an issue key."""
    return issue_key.rsplit("-", 1)[0] if "-" in issue_key else issue_key


class ProjectAnalysisMixin(JiraClient):
    """Mixin for project-level Jira analysis."""

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    def _fetch_project_issues_with_links(
        self,
        jql: str,
        max_issues: int,
    ) -> list[dict[str, Any]]:
        """Fetch issues matching *jql* with link data, handling pagination.

        Args:
            jql: JQL query to execute.
            max_issues: Upper bound on the number of issues.

        Returns:
            List of simplified issue dicts (via ``to_simplified_dict``).
        """
        result: JiraSearchResult = self.search_issues(  # type: ignore[attr-defined]
            jql=jql,
            fields=_LINK_FIELDS,
            limit=max_issues,
        )
        all_issues: list[dict[str, Any]] = [
            issue.to_simplified_dict() for issue in result.issues
        ]

        # Cloud paginates internally via nextPageToken — only page
        # manually on Server/DC where each response caps at 50.
        if not self.config.is_cloud:
            while (
                len(all_issues) < max_issues
                and len(result.issues) >= _SERVER_DC_PAGE_SIZE
            ):
                result = self.search_issues(  # type: ignore[attr-defined]
                    jql=jql,
                    fields=_LINK_FIELDS,
                    start=len(all_issues),
                    limit=max_issues - len(all_issues),
                )
                if not result.issues:
                    break
                all_issues.extend(issue.to_simplified_dict() for issue in result.issues)

        return all_issues[:max_issues]

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    @handle_auth_errors("Jira API")
    def get_project_epic_hierarchy(
        self,
        project_key: str,
        max_epics: int = 200,
    ) -> dict[str, Any]:
        """Group a project's epics under their cross-project parent issues.

        Fetches all epics in *project_key*, inspects their ``parent``
        field and ``issuelinks`` for cross-project containment
        relationships, then groups them by parent.  Epics with no
        detected parent appear under an *Unlinked* group.

        Args:
            project_key: Jira project key (e.g. ``PROJ``).
            max_epics: Maximum number of epics to fetch.

        Returns:
            Dict with ``project_key``, ``total_epics``, and ``groups``
            (each group has a ``parent`` dict and an ``epics`` list).

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: On API or query errors.
        """
        jql = f'project = "{project_key}" AND issuetype = Epic ORDER BY updated DESC'
        epic_dicts = self._fetch_project_issues_with_links(jql, max_epics)

        parent_keys: set[str] = set()
        epic_to_parent: dict[str, str | None] = {}

        for epic in epic_dicts:
            parent_key = self._detect_parent_key(epic, project_key)
            key = epic.get("key", "")
            epic_to_parent[key] = parent_key
            if parent_key:
                parent_keys.add(parent_key)

        parent_info = self._batch_fetch_summaries(parent_keys)

        groups: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for epic in epic_dicts:
            key = epic.get("key", "")
            parent_key = epic_to_parent.get(key)
            groups[parent_key].append(
                {
                    "key": key,
                    "summary": epic.get("summary", ""),
                    "status": self._extract_status_name(epic),
                }
            )

        result_groups: list[dict[str, Any]] = []
        for pk in sorted(groups, key=lambda k: (k is None, k or "")):
            if pk is None:
                result_groups.append(
                    {
                        "parent": None,
                        "group_name": "Unlinked",
                        "epics": groups[pk],
                    }
                )
            else:
                info = parent_info.get(pk, {})
                result_groups.append(
                    {
                        "parent": {
                            "key": pk,
                            "summary": info.get("summary", ""),
                            "project": _project_key_from_issue_key(pk),
                        },
                        "epics": groups[pk],
                    }
                )

        return {
            "project_key": project_key,
            "total_epics": len(epic_dicts),
            "groups": result_groups,
        }

    @handle_auth_errors("Jira API")
    def get_cross_project_dependencies(
        self,
        project_key: str,
        max_issues: int = 200,
    ) -> dict[str, Any]:
        """Find all cross-project issue links for a project.

        Scans issues in *project_key*, extracts every issue link whose
        target belongs to a different project, and groups them by
        target project and link type.

        Args:
            project_key: Jira project key (e.g. ``PROJ``).
            max_issues: Maximum issues to scan.

        Returns:
            Dict with ``project_key``, ``total_issues_scanned``,
            ``total_cross_project_links``, and ``by_project`` grouped
            results.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: On API or query errors.
        """
        jql = f'project = "{project_key}" ORDER BY updated DESC'
        issues = self._fetch_project_issues_with_links(jql, max_issues)

        by_project: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        total_links = 0

        for issue in issues:
            issue_key = issue.get("key", "")
            for link_info in self._extract_cross_project_links(issue, project_key):
                target_proj = _project_key_from_issue_key(link_info["target_key"])
                by_project[target_proj][link_info["link_type"]].append(
                    {
                        "source": issue_key,
                        "target": link_info["target_key"],
                        "direction": link_info["direction"],
                    }
                )
                total_links += 1

        by_project_output: dict[str, Any] = {}
        for proj in sorted(by_project):
            link_types = by_project[proj]
            by_project_output[proj] = {
                "total_links": sum(len(v) for v in link_types.values()),
                "by_link_type": dict(link_types),
            }

        return {
            "project_key": project_key,
            "total_issues_scanned": len(issues),
            "total_cross_project_links": total_links,
            "by_project": by_project_output,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_parent_key(
        epic_dict: dict[str, Any],
        own_project: str,
    ) -> str | None:
        """Detect a cross-project parent from an epic's data.

        Checks the ``parent`` field first, then issue links whose
        direction indicates the *current* epic is the child.
        """
        parent = epic_dict.get("parent")
        if isinstance(parent, dict):
            parent_key = parent.get("key", "")
            if parent_key and _project_key_from_issue_key(parent_key) != own_project:
                return parent_key

        for link in epic_dict.get("issuelinks", []):
            lt = link.get("type")
            if not isinstance(lt, dict):
                continue
            link_name = lt.get("name", "").lower()
            inward_label = lt.get("inward", "").lower()
            outward_label = lt.get("outward", "").lower()

            # For inward_issue: accept if the inward label (or name)
            # says we are the child (e.g. "is child of").
            inward = link.get("inward_issue")
            if inward:
                inward_key = inward.get("key", "")
                if (
                    inward_key
                    and _project_key_from_issue_key(inward_key) != own_project
                ):
                    labels = {link_name, inward_label}
                    if labels & CHILD_OF_PHRASES:
                        return inward_key

            # For outward_issue: accept if the outward label (or name)
            # says we are the child (e.g. "is child of").
            outward = link.get("outward_issue")
            if outward:
                outward_key = outward.get("key", "")
                if (
                    outward_key
                    and _project_key_from_issue_key(outward_key) != own_project
                ):
                    labels = {link_name, outward_label}
                    if labels & CHILD_OF_PHRASES:
                        return outward_key

        return None

    @staticmethod
    def _extract_cross_project_links(
        issue_dict: dict[str, Any],
        own_project: str,
    ) -> list[dict[str, str]]:
        """Return cross-project link info from an issue's simplified dict."""
        results: list[dict[str, str]] = []
        for link in issue_dict.get("issuelinks", []):
            link_type_name = ""
            lt = link.get("type")
            if isinstance(lt, dict):
                link_type_name = lt.get("name", "")

            for direction, link_key_field in [
                ("outward", "outward_issue"),
                ("inward", "inward_issue"),
            ]:
                target = link.get(link_key_field)
                if not target:
                    continue
                target_key = target.get("key", "")
                if not target_key:
                    continue
                target_proj = _project_key_from_issue_key(target_key)
                if target_proj != own_project:
                    results.append(
                        {
                            "target_key": target_key,
                            "link_type": link_type_name,
                            "direction": direction,
                        }
                    )
        return results

    @staticmethod
    def _extract_status_name(issue_dict: dict[str, Any]) -> str:
        status = issue_dict.get("status")
        if isinstance(status, dict):
            return status.get("name", "Unknown")
        return "Unknown"

    def _batch_fetch_summaries(
        self,
        keys: set[str],
    ) -> dict[str, dict[str, str]]:
        """Fetch summary info for a set of issue keys."""
        if not keys:
            return {}

        result: dict[str, dict[str, str]] = {}
        keys_list = sorted(keys)

        for i in range(0, len(keys_list), _SERVER_DC_PAGE_SIZE):
            chunk = keys_list[i : i + _SERVER_DC_PAGE_SIZE]
            jql = "key in ({})".format(",".join(chunk))
            try:
                search = self.search_issues(  # type: ignore[attr-defined]
                    jql=jql,
                    fields=["summary", "status"],
                    limit=len(chunk),
                )
                for issue in search.issues:
                    result[issue.key] = {
                        "summary": issue.summary,
                        "status": issue.status.name if issue.status else "",
                    }
            except HTTPError:
                raise
            except Exception:
                logger.warning("Failed to resolve parent summaries for %s", chunk)
        return result
