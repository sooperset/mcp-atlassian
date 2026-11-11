"""Resolve Jira identifiers to projects and enforce JIRA_PROJECTS_FILTER.

Every check resolves the identifier through the Jira API instead of trusting
its spelling: an issue key such as ``ALLOWED-1`` keeps resolving after the
issue is moved to another project, and numeric IDs carry no project prefix.
A check that cannot resolve the identifier denies it.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from ..exceptions import ScopeViolationError
from .client import JiraClient

logger = logging.getLogger("mcp-jira")

_FILTER_NAME = "JIRA_PROJECTS_FILTER"


def allowed_project_keys(config: object) -> frozenset[str] | None:
    """Return the upper-cased JIRA_PROJECTS_FILTER keys of ``config``, or None."""
    raw = getattr(config, "projects_filter", None)
    if not isinstance(raw, str):
        return None
    keys = frozenset(k.strip().upper() for k in raw.split(",") if k.strip())
    return keys or None


def _denied(kind: str, value: object) -> ScopeViolationError:
    return ScopeViolationError(
        f"Jira {kind} '{value}' is outside the configured {_FILTER_NAME} "
        "or could not be verified."
    )


def _path_segment(value: object) -> str:
    return quote(str(value).strip(), safe="")


_BOARD_PROJECT_PAGES = 20


def board_project_keys(jira: Any, board_id: object) -> frozenset[str] | None:
    """Return every project key associated with a board, or None.

    Used for boards that have no ``location.projectKey`` (boards located in a
    user profile, or whose filter spans projects). ``/board/{id}/project``
    lists the projects the board's filter references or whose issues are on
    the board. None means the list is empty, incomplete or could not be read,
    which callers treat as "deny".

    Args:
        jira: The Atlassian client (``self.jira``).
        board_id: The board ID.
    """
    path = f"rest/agile/1.0/board/{_path_segment(board_id)}/project"
    keys: set[str] = set()
    start = 0
    try:
        for _ in range(_BOARD_PROJECT_PAGES):
            page = jira.get(path, params={"startAt": start, "maxResults": 50})
            if not isinstance(page, dict):
                return None
            values = page.get("values")
            if not isinstance(values, list):
                return None
            for project in values:
                key = project.get("key") if isinstance(project, dict) else None
                if not isinstance(key, str) or not key.strip():
                    return None
                keys.add(key.strip().upper())
            if page.get("isLast") is True:
                return frozenset(keys) or None
            if not values:
                return None
            start += len(values)
    except Exception as e:  # noqa: BLE001 - any failure denies
        logger.warning(f"Could not list projects of Jira board {board_id!r}: {e}")
        return None
    return None


def board_in_scope(jira: Any, board: dict[str, Any], allowed: frozenset[str]) -> bool:
    """Return True when ``board`` lies inside the project allowlist.

    A board located in a project is in scope when that project is allowed.
    A board with no location project is in scope only when every project
    associated with it is allowed.
    """
    project_key = (board.get("location") or {}).get("projectKey")
    if isinstance(project_key, str) and project_key.strip():
        return project_key.strip().upper() in allowed
    board_id = board.get("id")
    if board_id is None:
        return False
    keys = board_project_keys(jira, board_id)
    return keys is not None and keys <= allowed


class ScopeMixin(JiraClient):
    """Project-allowlist checks shared by every Jira tool."""

    def allowed_projects(self) -> frozenset[str] | None:
        """Return the upper-cased JIRA_PROJECTS_FILTER keys, or None if unset."""
        return allowed_project_keys(self.config)

    def _get_json(self, path: str) -> dict[str, Any]:
        data = self.jira.get(path)
        if not isinstance(data, dict):
            msg = f"Unexpected response type for {path}: {type(data).__name__}"
            raise TypeError(msg)
        return data

    def ensure_project_allowed(self, project_key: object) -> None:
        """Raise ScopeViolationError if ``project_key`` is not allowlisted."""
        allowed = self.allowed_projects()
        if allowed is None:
            return
        if not isinstance(project_key, str) or project_key.strip().upper() not in (
            allowed
        ):
            raise _denied("project", project_key)

    def ensure_project_id_allowed(self, project_id: object) -> None:
        """Resolve a numeric project ID and check its key."""
        if self.allowed_projects() is None:
            return
        try:
            project = self._get_json(f"rest/api/2/project/{_path_segment(project_id)}")
            key = project.get("key")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira project {project_id!r}: {e}")
            raise _denied("project", project_id) from e
        if not isinstance(key, str):
            raise _denied("project", project_id)
        self.ensure_project_allowed(key)

    def ensure_issue_allowed(self, issue_key: object) -> None:
        """Resolve an issue key or ID to its current project and check it."""
        allowed = self.allowed_projects()
        if allowed is None:
            return
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise _denied("issue", issue_key)
        try:
            issue = self.jira.issue(issue_key.strip(), fields="project")
            project = ((issue or {}).get("fields") or {}).get("project") or {}
            project_key = project.get("key")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira issue {issue_key!r}: {e}")
            raise _denied("issue", issue_key) from e
        if not isinstance(project_key, str) or project_key.upper() not in allowed:
            raise _denied("issue", issue_key)

    def ensure_issues_allowed(self, issue_keys: object) -> None:
        """Check every issue in a list or comma-separated string."""
        if self.allowed_projects() is None:
            return
        if isinstance(issue_keys, str):
            items: list[object] = [k for k in issue_keys.split(",") if k.strip()]
        elif isinstance(issue_keys, list | tuple | set):
            items = list(issue_keys)
        else:
            raise _denied("issue", issue_keys)
        for item in items:
            self.ensure_issue_allowed(item.strip() if isinstance(item, str) else item)

    def ensure_board_allowed(self, board_id: object) -> None:
        """Check the project a board is located in.

        A board without a location project (for example one located in a
        user profile) is allowed only when every project associated with it
        is allowlisted.
        """
        allowed = self.allowed_projects()
        if allowed is None:
            return
        try:
            board = self._get_json(f"rest/agile/1.0/board/{_path_segment(board_id)}")
            project_key = (board.get("location") or {}).get("projectKey")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira board {board_id!r}: {e}")
            raise _denied("board", board_id) from e
        if isinstance(project_key, str):
            self.ensure_project_allowed(project_key)
            return
        keys = board_project_keys(self.jira, board_id)
        if keys is None or not keys <= allowed:
            raise _denied("board", board_id)

    def ensure_sprint_allowed(self, sprint_id: object) -> None:
        """Check the project of the board a sprint was created on."""
        if self.allowed_projects() is None:
            return
        try:
            sprint = self._get_json(f"rest/agile/1.0/sprint/{_path_segment(sprint_id)}")
            board_id = sprint.get("originBoardId")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira sprint {sprint_id!r}: {e}")
            raise _denied("sprint", sprint_id) from e
        if board_id is None:
            raise _denied("sprint", sprint_id)
        self.ensure_board_allowed(board_id)

    def ensure_version_allowed(self, version_id: object) -> None:
        """Check the project a fix version belongs to."""
        if self.allowed_projects() is None:
            return
        try:
            version = self._get_json(f"rest/api/2/version/{_path_segment(version_id)}")
            project_id = version.get("projectId")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira version {version_id!r}: {e}")
            raise _denied("version", version_id) from e
        if project_id is None:
            raise _denied("version", version_id)
        self.ensure_project_id_allowed(project_id)

    def ensure_issue_link_allowed(self, link_id: object) -> None:
        """Check both issues joined by an issue link."""
        if self.allowed_projects() is None:
            return
        try:
            link = self._get_json(f"rest/api/2/issueLink/{_path_segment(link_id)}")
            keys = [
                (link.get(side) or {}).get("key")
                for side in ("inwardIssue", "outwardIssue")
            ]
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira issue link {link_id!r}: {e}")
            raise _denied("issue link", link_id) from e
        for key in keys:
            self.ensure_issue_allowed(key)

    def ensure_service_desk_allowed(self, service_desk_id: object) -> None:
        """Check the project behind a Jira Service Management service desk."""
        if self.allowed_projects() is None:
            return
        try:
            desk = self._get_json(
                f"rest/servicedeskapi/servicedesk/{_path_segment(service_desk_id)}"
            )
            project_key = desk.get("projectKey")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve service desk {service_desk_id!r}: {e}")
            raise _denied("service desk", service_desk_id) from e
        if not isinstance(project_key, str):
            raise _denied("service desk", service_desk_id)
        self.ensure_project_allowed(project_key)
