"""Module for Jira issue link graph traversal and analysis."""

import logging
from collections import deque
from typing import Any

from requests.exceptions import HTTPError

from ..models.jira import JiraSearchResult
from ..utils.decorators import handle_auth_errors
from .client import JiraClient
from .constants import PARENT_OF_PHRASES

logger = logging.getLogger("mcp-jira")

_SERVER_DC_PAGE_SIZE = 50

# Legacy map kept for backward compatibility with callers that import
# ``CONTAINMENT_LINKS``.  Keys are lower-cased phrases; values are the
# direction in which the *target* is a child when the phrase appears in
# ``type.name`` (not a directional label).
CONTAINMENT_LINKS: dict[str, str] = {
    "is parent of": "outward",
    "parent": "outward",
    "contains": "outward",
    "is child of": "inward",
    "is contained by": "inward",
}

_LINK_FIELDS = [
    "summary",
    "status",
    "issuetype",
    "issuelinks",
    "parent",
    "subtasks",
]


def _node_from_issue(issue_dict: dict[str, Any], depth: int) -> dict[str, Any]:
    """Build a lightweight node dict from a simplified issue."""
    status = issue_dict.get("status")
    status_name = "Unknown"
    if isinstance(status, dict):
        status_name = status.get("name", "Unknown")

    itype = issue_dict.get("issue_type")
    type_name = "Unknown"
    if isinstance(itype, dict):
        type_name = itype.get("name", "Unknown")

    return {
        "key": issue_dict.get("key", ""),
        "summary": issue_dict.get("summary", ""),
        "status": status_name,
        "issue_type": type_name,
        "depth": depth,
    }


def _is_child_direction(
    link_type_name: str,
    direction: str,
    inward_label: str = "",
    outward_label: str = "",
) -> bool:
    """Return True if a link with this type+direction means target is a child.

    The label for *this* direction describes the current issue's role
    relative to the target:

    * ``direction="outward"``: ``outward_label`` applies.
      "is parent of" → we are parent → target is child.
    * ``direction="inward"``: ``inward_label`` applies.
      "is parent of" → we are parent → target is child.

    When no directional labels are set, ``type.name`` is checked as a
    fallback for link types whose name is itself a parent-of phrase.
    """
    if direction == "outward":
        own_label = outward_label.lower()
    else:
        own_label = inward_label.lower()

    if own_label in PARENT_OF_PHRASES:
        return True

    # Fallback: if type.name is a parent-of phrase and matches the
    # expected direction from CONTAINMENT_LINKS, treat as containment.
    # Only applies when directional labels are absent.
    if not own_label:
        expected_dir = CONTAINMENT_LINKS.get(link_type_name.lower())
        if expected_dir is not None and expected_dir == direction:
            return True

    return False


class LinkAnalysisMixin(JiraClient):
    """Mixin for recursive issue-link graph traversal."""

    def _batch_fetch_issues(
        self,
        keys: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch multiple issues by key via JQL ``key in (...)``."""
        if not keys:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for i in range(0, len(keys), _SERVER_DC_PAGE_SIZE):
            chunk = keys[i : i + _SERVER_DC_PAGE_SIZE]
            jql = "key in ({})".format(",".join(chunk))
            try:
                search: JiraSearchResult = self.search_issues(  # type: ignore[attr-defined]
                    jql=jql,
                    fields=_LINK_FIELDS,
                    limit=len(chunk),
                )
                for issue in search.issues:
                    result[issue.key] = issue.to_simplified_dict()
            except HTTPError:
                raise
            except Exception:
                logger.warning("Failed to batch-fetch issues: %s", chunk)
        return result

    @staticmethod
    def _extract_links(
        issue_dict: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Normalise ``issuelinks`` into a flat list of link descriptors."""
        links: list[dict[str, Any]] = []

        for raw_link in issue_dict.get("issuelinks", []):
            lt = raw_link.get("type")
            link_type_name = ""
            inward_label = ""
            outward_label = ""
            if isinstance(lt, dict):
                link_type_name = lt.get("name", "")
                inward_label = lt.get("inward", "")
                outward_label = lt.get("outward", "")

            for direction, field in [
                ("outward", "outward_issue"),
                ("inward", "inward_issue"),
            ]:
                target = raw_link.get(field)
                if not target:
                    continue
                target_key = target.get("key", "")
                if target_key:
                    links.append(
                        {
                            "target_key": target_key,
                            "link_type": link_type_name,
                            "direction": direction,
                            "is_child": _is_child_direction(
                                link_type_name,
                                direction,
                                inward_label,
                                outward_label,
                            ),
                        }
                    )

        return links

    @handle_auth_errors("Jira API")
    def trace_issue_links(
        self,
        issue_key: str,
        max_depth: int = 3,
        link_type_filter: list[str] | None = None,
        direction_filter: str | None = None,
        max_issues: int = 100,
    ) -> dict[str, Any]:
        """BFS traversal of issue links returning a flat graph.

        Args:
            issue_key: Root issue key.
            max_depth: Maximum hops to follow (1-5).
            link_type_filter: Only follow links whose type name is in
                this list (case-insensitive).  ``None`` means all.
            direction_filter: ``"inward"``, ``"outward"``, or ``None``
                for both.
            max_issues: Safety limit on total visited nodes.

        Returns:
            Dict with ``root``, ``nodes`` (list), ``edges`` (list),
            ``total_nodes``, and ``total_edges``.

        Raises:
            ValueError: If direction_filter is invalid.
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: On API errors.
        """
        if direction_filter and direction_filter not in ("inward", "outward"):
            raise ValueError(
                f"direction_filter must be 'inward', 'outward', or None; "
                f"got '{direction_filter}'"
            )

        type_filter_lower: set[str] | None = None
        if link_type_filter:
            type_filter_lower = {t.lower() for t in link_type_filter}

        visited: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, str]] = []
        seen_edges: set[tuple[str, str, str]] = set()
        queue: deque[tuple[str, int]] = deque([(issue_key, 0)])

        while queue:
            current_key, depth = queue.popleft()
            if current_key in visited or len(visited) >= max_issues:
                continue

            # Collect all unvisited keys at this depth for batch fetch.
            batch_keys = [current_key]
            remainder: list[tuple[str, int]] = []
            while queue:
                nk, nd = queue.popleft()
                if nk in visited or len(visited) + len(batch_keys) >= max_issues:
                    remainder.append((nk, nd))
                elif nd == depth:
                    batch_keys.append(nk)
                else:
                    remainder.append((nk, nd))
            for item in remainder:
                queue.append(item)

            fetched = self._batch_fetch_issues(batch_keys)

            for bk in batch_keys:
                if bk in visited or len(visited) >= max_issues:
                    continue
                issue_dict = fetched.get(bk)
                if issue_dict is None:
                    continue

                visited[bk] = _node_from_issue(issue_dict, depth)

                if depth >= max_depth:
                    continue

                for link in self._extract_links(issue_dict):
                    target = link["target_key"]

                    if type_filter_lower and (
                        link["link_type"].lower() not in type_filter_lower
                    ):
                        continue
                    if direction_filter and link["direction"] != direction_filter:
                        continue

                    # Deduplicate mirrored edges.
                    edge_id = (
                        min(bk, target),
                        max(bk, target),
                        link["link_type"],
                    )
                    if edge_id not in seen_edges:
                        seen_edges.add(edge_id)
                        edges.append(
                            {
                                "source": bk,
                                "target": target,
                                "link_type": link["link_type"],
                                "direction": link["direction"],
                            }
                        )

                    if target not in visited:
                        queue.append((target, depth + 1))

        # Only keep edges where both endpoints were visited.
        visited_keys = set(visited.keys())
        edges = [
            e
            for e in edges
            if e["source"] in visited_keys and e["target"] in visited_keys
        ]

        return {
            "root": issue_key,
            "max_depth": max_depth,
            "nodes": list(visited.values()),
            "edges": edges,
            "total_nodes": len(visited),
            "total_edges": len(edges),
        }

    @handle_auth_errors("Jira API")
    def get_issue_tree(
        self,
        issue_key: str,
        max_depth: int = 3,
        max_issues: int = 100,
    ) -> dict[str, Any]:
        """Build a hierarchical tree following containment links only.

        Containment links (parent/child, contains) form the tree spine.
        Non-containment links are recorded as ``cross_links``
        annotations but are **not** traversed.

        Args:
            issue_key: Root issue key.
            max_depth: Maximum tree depth (1-5).
            max_issues: Safety limit on visited nodes.

        Returns:
            Dict with ``root`` (recursive tree node), ``cross_links``
            list, and ``total_nodes``.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: On API errors.
        """
        visited: set[str] = set()
        cross_links: list[dict[str, str]] = []

        def _build(key: str, depth: int) -> dict[str, Any] | None:
            if key in visited or len(visited) >= max_issues:
                return None

            fetched = self._batch_fetch_issues([key])
            issue_dict = fetched.get(key)
            if issue_dict is None:
                return None

            visited.add(key)
            node = _node_from_issue(issue_dict, depth)
            children: list[dict[str, Any]] = []
            child_keys: set[str] = set()

            for st in issue_dict.get("subtasks", []):
                st_key = st.get("key", "") if isinstance(st, dict) else ""
                if st_key and st_key not in visited:
                    child_keys.add(st_key)

            for link in self._extract_links(issue_dict):
                target = link["target_key"]
                if link["is_child"]:
                    if target not in visited:
                        child_keys.add(target)
                else:
                    cross_links.append(
                        {
                            "source": key,
                            "target": target,
                            "link_type": link["link_type"],
                            "direction": link["direction"],
                        }
                    )

            if depth < max_depth:
                for ck in sorted(child_keys):
                    child_node = _build(ck, depth + 1)
                    if child_node is not None:
                        children.append(child_node)

            node["children"] = children
            return node

        root = _build(issue_key, 0)
        if root is None:
            root = {
                "key": issue_key,
                "summary": "",
                "status": "Unknown",
                "issue_type": "Unknown",
                "depth": 0,
                "children": [],
            }

        return {
            "root": root,
            "cross_links": cross_links,
            "total_nodes": len(visited),
        }
