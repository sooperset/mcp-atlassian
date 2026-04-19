"""Module for Jira issue set comparison operations."""

import logging
from typing import Any

from ..models.jira import JiraSearchResult
from ..utils.decorators import handle_auth_errors
from .client import JiraClient
from .protocols import SearchOperationsProto

logger = logging.getLogger("mcp-jira")

# Server/DC caps each search response at this many issues.
_SERVER_DC_PAGE_SIZE = 50

# Fields used for comparison when none are specified.
_DEFAULT_COMPARE_FIELDS = ["status", "assignee", "priority", "labels"]

# Fields always fetched so that every issue node carries basic identity info.
_BASE_FIELDS = ["summary", "status", "issuetype"]


def _normalize_field_value(value: Any) -> str | list[str] | None:
    """Normalize a field value for comparison.

    Args:
        value: The raw value from to_simplified_dict().

    Returns:
        A normalized comparable value.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("display_name", "name", "value"):
            v = value.get(key)
            if v is not None:
                return str(v)
        return None
    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, dict):
                for key in ("display_name", "name"):
                    v = item.get(key)
                    if v is not None:
                        normalized.append(str(v))
                        break
                else:
                    normalized.append(str(item))
            else:
                normalized.append(str(item))
        return sorted(normalized)
    return str(value)


class SetAnalysisMixin(JiraClient, SearchOperationsProto):
    """Mixin for comparing two sets of Jira issues."""

    def _fetch_all_issues(
        self,
        jql: str,
        fields: list[str],
        max_issues: int,
    ) -> list[dict[str, Any]]:
        """Fetch all issues for a JQL query up to max_issues.

        On Cloud, ``search_issues`` paginates internally via
        ``nextPageToken``, so a single call with ``limit=max_issues``
        returns up to that many results.  On Server/DC the API caps
        each response at 50, so we page with ``start``.

        Args:
            jql: The JQL query string.
            fields: Fields to include in results.
            max_issues: Upper bound on issues to fetch.

        Returns:
            List of simplified issue dicts.
        """
        result: JiraSearchResult = self.search_issues(
            jql=jql,
            fields=fields,
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
                result = self.search_issues(
                    jql=jql,
                    fields=fields,
                    start=len(all_issues),
                    limit=max_issues - len(all_issues),
                )
                if not result.issues:
                    break
                all_issues.extend(issue.to_simplified_dict() for issue in result.issues)

        return all_issues[:max_issues]

    @handle_auth_errors("Jira API")
    def compare_issue_sets(
        self,
        jql_a: str,
        jql_b: str,
        compare_fields: list[str] | None = None,
        max_issues: int = 200,
    ) -> dict[str, Any]:
        """Compare two sets of Jira issues defined by JQL queries.

        Runs both queries and computes set differences: issues only in A,
        only in B, present in both but with changed fields, and unchanged.

        Args:
            jql_a: JQL query defining set A.
            jql_b: JQL query defining set B.
            compare_fields: Field names to check for changes on issues
                present in both sets. Defaults to status, assignee,
                priority, and labels.
            max_issues: Maximum issues to fetch per query.

        Returns:
            Dict with only_in_a, only_in_b, changed, unchanged_count,
            and a summary sub-dict.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If there is an error executing the queries.
        """
        fields_to_compare = compare_fields or _DEFAULT_COMPARE_FIELDS
        fields_to_fetch = list(dict.fromkeys(_BASE_FIELDS + fields_to_compare))

        issues_a = self._fetch_all_issues(jql_a, fields_to_fetch, max_issues)
        issues_b = self._fetch_all_issues(jql_b, fields_to_fetch, max_issues)

        map_a: dict[str, dict[str, Any]] = {i["key"]: i for i in issues_a if "key" in i}
        map_b: dict[str, dict[str, Any]] = {i["key"]: i for i in issues_b if "key" in i}

        keys_a = set(map_a.keys())
        keys_b = set(map_b.keys())

        only_in_a_keys = sorted(keys_a - keys_b)
        only_in_b_keys = sorted(keys_b - keys_a)
        common_keys = sorted(keys_a & keys_b)

        only_in_a = [
            {"key": k, "summary": map_a[k].get("summary", "")} for k in only_in_a_keys
        ]
        only_in_b = [
            {"key": k, "summary": map_b[k].get("summary", "")} for k in only_in_b_keys
        ]

        changed: list[dict[str, Any]] = []
        unchanged_count = 0

        for key in common_keys:
            issue_a = map_a[key]
            issue_b = map_b[key]
            diffs: list[dict[str, Any]] = []

            for field in fields_to_compare:
                val_a = _normalize_field_value(issue_a.get(field))
                val_b = _normalize_field_value(issue_b.get(field))
                if val_a != val_b:
                    diffs.append(
                        {
                            "field": field,
                            "in_a": val_a,
                            "in_b": val_b,
                        }
                    )

            if diffs:
                changed.append(
                    {
                        "key": key,
                        "summary": issue_a.get("summary", ""),
                        "changes": diffs,
                    }
                )
            else:
                unchanged_count += 1

        return {
            "jql_a": jql_a,
            "jql_b": jql_b,
            "set_a_count": len(map_a),
            "set_b_count": len(map_b),
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "changed": changed,
            "unchanged_count": unchanged_count,
            "summary": {
                "only_in_a_count": len(only_in_a),
                "only_in_b_count": len(only_in_b),
                "changed_count": len(changed),
                "unchanged_count": unchanged_count,
            },
        }
