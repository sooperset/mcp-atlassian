"""Resolve Jira identifiers to projects and enforce JIRA_PROJECTS_FILTER.

Every check resolves the identifier through the Jira API instead of trusting
its spelling: an issue key such as ``ALLOWED-1`` keeps resolving after the
issue is moved to another project, and numeric IDs carry no project prefix.
A check that cannot resolve the identifier denies it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from ..exceptions import ScopeViolationError
from ..models.jira.issue import field_metadata_kinds, normalize_field_name
from ..utils.urls import path_segment
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


@contextmanager
def _denied_as(kind: str, value: object) -> Iterator[None]:
    """Report a denial of a resolved parent as a denial of the caller's value.

    The denial text names only what the caller passed, so it reads the same
    whether the object is missing or resolves outside the allowlist.
    """
    try:
        yield
    except ScopeViolationError:
        raise _denied(kind, value) from None


def _issue_reference(value: object) -> object:
    """Return the issue key or ID a parent/epic value points at.

    ``None`` and ``""`` clear a reference and are returned as None. A dict
    yields its ``key`` or ``id``; any other dict is returned unchanged so the
    check denies it.
    """
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        ref = value.get("key") or value.get("id")
        return ref if ref is not None else value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


_REFERENCE_VERBS = ("set", "add", "edit")


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
    path = f"rest/agile/1.0/board/{path_segment(board_id)}/project"
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


# --- JQL references ------------------------------------------------------------
#
# The allowlist is ANDed into every query, but Jira still evaluates the
# caller's predicate: ``issue in linkedIssues("X-1")`` or ``parent = X-1``
# selects in-scope issues by their relation to an out-of-scope one. Only the
# places where JQL names an issue are checked: operands of issue fields and the
# issue arguments of issue functions. Values of other fields (labels, versions,
# sprints, users, text) are left alone however they look.

_JQL_ISSUE_FIELDS = frozenset({"key", "issuekey", "issue", "id", "parent"})
# Without field metadata these names are still taken as issue references.
_JQL_ISSUE_FIELD_NAMES = frozenset({"epic link", "parent link"})
# Jira system fields whose values are not issues.
_JQL_STANDARD_FIELDS = frozenset(
    {
        "affectedversion", "approvals", "approver", "assignee", "attachments",
        "category", "comment", "component", "created", "createddate", "creator",
        "description", "due", "duedate", "environment", "filter",
        "fixversion", "issuelinktype", "issuetype", "type", "labels",
        "lastviewed", "level", "organizations", "originalestimate",
        "timeoriginalestimate", "priority", "project", "projecttype",
        "remainingestimate", "timeestimate", "reporter", "resolution",
        "resolutiondate", "resolved", "sprint", "status", "statuscategory",
        "summary", "text", "timespent", "updated", "updateddate", "voter",
        "votes", "watcher", "watchers", "worklogauthor", "worklogcomment",
        "worklogdate", "workratio", "development", "team", "request",
        "requesttype", "requestchannel", "epic name", "story points",
    }
)  # fmt: skip
# Issue functions and the positions of their issue arguments.
_JQL_ISSUE_FUNCTIONS: dict[str, tuple[int, ...]] = {
    "linkedissues": (0,),
    "parentepic": (0,),
    "portfoliochildissuesof": (0,),
    "portfolioparentissuesof": (0,),
    "childissuesof": (0,),
}
# Words that are never function names, so "AND (" is a group, not a call.
_JQL_RESERVED = frozenset(
    {"and", "or", "not", "in", "is", "was", "changed", "empty", "null",
     "order", "by", "asc", "desc", "from", "to", "before", "after", "during",
     "on"}
)  # fmt: skip
_JQL_OPERATOR_CHARS = "=!<>~"
_ISSUE_KEY_FULL_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)-(\d+)")
_CF_RE = re.compile(r"cf\[(\d+)\]", re.IGNORECASE)
_JQL_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", " ": " "}


def _jql_tokens(jql: str) -> list[tuple[str, str]]:
    """Split JQL into ("str"|"word"|"op"|"punct", text) tokens, in one pass.

    Quoted strings are unescaped as JQL does (``\\"``, ``\\uXXXX``, ...).
    """
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(jql)
    while i < n:
        c = jql[i]
        if c.isspace():
            i += 1
        elif c in "\"'":
            j = i + 1
            buf: list[str] = []
            while j < n and jql[j] != c:
                if jql[j] == "\\" and j + 1 < n:
                    nxt = jql[j + 1]
                    if nxt == "u" and re.fullmatch(
                        r"[0-9A-Fa-f]{4}", jql[j + 2 : j + 6]
                    ):
                        buf.append(chr(int(jql[j + 2 : j + 6], 16)))
                        j += 6
                        continue
                    buf.append(_JQL_ESCAPES.get(nxt, nxt))
                    j += 2
                    continue
                buf.append(jql[j])
                j += 1
            tokens.append(("str", "".join(buf)))
            i = j + 1
        elif c in "(),":
            tokens.append(("punct", c))
            i += 1
        elif c in _JQL_OPERATOR_CHARS:
            j = i
            while j < n and jql[j] in _JQL_OPERATOR_CHARS:
                j += 1
            tokens.append(("op", jql[i:j]))
            i = j
        else:
            j = i
            while (
                j < n
                and not jql[j].isspace()
                and jql[j] not in "(),\"'"
                and jql[j] not in _JQL_OPERATOR_CHARS
            ):
                j += 1
            tokens.append(("word", jql[i:j]))
            i = j
    return tokens


def _normalize_field(name: str) -> str:
    cf = _CF_RE.fullmatch(name.strip())
    if cf:
        return f"customfield_{cf.group(1)}"
    return normalize_field_name(name)


def _out_of_scope_issue_value(value: str, allowed: frozenset[str]) -> bool:
    value = value.strip()
    if value.isdigit():
        return True
    match = _ISSUE_KEY_FULL_RE.fullmatch(value)
    return bool(match) and match.group(1).upper() not in allowed


def refuse_out_of_scope_jql_references(
    jql: str,
    allowed: frozenset[str],
    field_kinds: Callable[[], dict[str, Any] | None] | None = None,
) -> None:
    """Refuse JQL whose issue positions name an issue outside the allowlist.

    Issue positions are operands of ``key``, ``issuekey``, ``issue``, ``id``,
    ``parent`` and of custom fields that the field metadata types as issue
    references (Epic Link, Parent Link), by name or ``cf[N]``; and the issue
    arguments of issue functions such as ``linkedIssues``, also inside a list.
    An issue ID there is refused, since its project is not known without a
    lookup. Without field metadata, a key-shaped or numeric operand of a
    custom or unknown field is refused. Saved filters, app functions,
    ``CHANGED FROM/TO`` operands and nested function arguments are not checked.

    Args:
        jql: Caller JQL.
        allowed: Upper-cased JIRA_PROJECTS_FILTER keys.
        field_kinds: Returns custom reference field kinds, or None when the
            metadata cannot be read; called at most once.

    Raises:
        ScopeViolationError: For the first out-of-scope issue position.
    """
    tokens = _jql_tokens(jql)
    n = len(tokens)
    kinds_cache: list[dict[str, Any] | None] = []

    def kinds() -> dict[str, Any] | None:
        if not kinds_cache:
            kinds_cache.append(field_kinds() if field_kinds else None)
        return kinds_cache[0]

    def field_role(name: str) -> str:
        """Return "issue", "unverified" or "other" for a field name."""
        field = _normalize_field(name)
        if field in _JQL_ISSUE_FIELDS:
            return "issue"
        if field in _JQL_STANDARD_FIELDS:
            return "other"
        known = kinds()
        if known is None:
            return "issue" if field in _JQL_ISSUE_FIELD_NAMES else "unverified"
        return "issue" if known.get(field) == "issue" else "other"

    def check(value: str, role: str) -> None:
        if role == "other" or not _out_of_scope_issue_value(value, allowed):
            return
        if role == "unverified":
            raise ScopeViolationError(
                f"JQL value '{value}' could not be checked against the configured "
                f"{_FILTER_NAME}: the field metadata is not available."
            )
        if value.strip().isdigit():
            raise ScopeViolationError(
                f"JQL issue ID '{value}' cannot be checked against the configured "
                f"{_FILTER_NAME}. Use issue keys while the filter is set."
            )
        raise ScopeViolationError(
            f"JQL references issue '{value}' outside the configured "
            f"{_FILTER_NAME} or could not be verified."
        )

    def is_call(i: int) -> bool:
        return (
            i + 1 < n
            and tokens[i][0] == "word"
            and tokens[i][1].lower() not in _JQL_RESERVED
            and tokens[i + 1] == ("punct", "(")
        )

    def skip_call(i: int) -> int:
        """Check the issue arguments of the call at ``i``; return its end."""
        positions = _JQL_ISSUE_FUNCTIONS.get(tokens[i][1].lower(), ())
        depth, arg, j = 0, 0, i + 1
        while j < n:
            kind, text = tokens[j]
            if (kind, text) == ("punct", "("):
                depth += 1
            elif (kind, text) == ("punct", ")"):
                depth -= 1
                if depth == 0:
                    return j + 1
            elif (kind, text) == ("punct", ",") and depth == 1:
                arg += 1
            elif depth == 1 and arg in positions and kind in ("str", "word"):
                check(text, "issue")
            j += 1
        return j

    def operator_end(i: int) -> int | None:
        """Return where the operand starts if an operator begins at ``i``."""
        kind, text = tokens[i]
        word = text.lower() if kind == "word" else ""
        if kind == "op":
            return i + 1
        if word in ("in",):
            return i + 1
        if word == "not" and i + 1 < n and tokens[i + 1][1].lower() == "in":
            return i + 2
        if word in ("is", "was"):
            j = i + 1
            while j < n and tokens[j][1].lower() in ("not", "in"):
                j += 1
            return j
        return None

    i = 0
    field: tuple[str, str] | None = None
    while i < n:
        if is_call(i):
            i = skip_call(i)
            field = None
            continue
        start = operator_end(i)
        if start is None:
            kind, text = tokens[i]
            field = (kind, text) if kind in ("str", "word") else None
            i += 1
            continue
        role = (
            field_role(field[1])
            if field is not None and field[1].lower() not in _JQL_RESERVED
            else "other"
        )
        field = None
        i = start
        if i >= n:
            break
        if is_call(i):
            i = skip_call(i)
        elif tokens[i] == ("punct", "("):
            i += 1
            while i < n and tokens[i] != ("punct", ")"):
                if is_call(i):
                    i = skip_call(i)
                    continue
                if tokens[i][0] in ("str", "word"):
                    check(tokens[i][1], role)
                i += 1
            i += 1
        else:
            if tokens[i][0] == "str" or (
                tokens[i][0] == "word" and tokens[i][1].lower() not in _JQL_RESERVED
            ):
                check(tokens[i][1], role)
            i += 1


def output_scope_kwargs(fetcher: Any) -> dict[str, Any]:
    """Return the model keyword arguments that apply the allowlist to output.

    ``changelog_field_kinds`` reads the field metadata only when a model has
    changelogs to filter, and returns None when the metadata cannot be read.

    Args:
        fetcher: A Jira fetcher (``config`` and, when available, ``get_fields``).
    """

    # One answer per call: a failed read is not retried for every issue.
    memo: list[dict[str, Any] | None] = []

    def field_kinds() -> dict[str, Any] | None:
        # None means the metadata could not be read; the filter then drops
        # custom-field changes it cannot classify.
        if memo:
            return memo[0]
        get_fields = getattr(fetcher, "get_fields", None)
        result: dict[str, Any] | None = None
        if callable(get_fields):
            try:
                result = field_metadata_kinds(get_fields(raise_errors=True))
            except Exception:  # noqa: BLE001 - any failure means "unknown"
                result = None
        memo.append(result)
        return result

    return {
        "allowed_projects": allowed_project_keys(fetcher.config),
        "changelog_field_kinds": field_kinds,
    }


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
            project = self._get_json(f"rest/api/2/project/{path_segment(project_id)}")
            key = project.get("key")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira project {project_id!r}: {e}")
            raise _denied("project", project_id) from e
        if not isinstance(key, str):
            raise _denied("project", project_id)
        with _denied_as("project", project_id):
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

    def _epic_link_field_id(self) -> str | None:
        try:
            field_ids = self.get_field_ids_to_epic()  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001 - no epic link field known
            logger.debug(f"Could not discover the Epic Link field: {e}")
            return None
        field_id = field_ids.get("epic_link") if isinstance(field_ids, dict) else None
        return field_id if isinstance(field_id, str) and field_id else None

    def ensure_issue_relations_allowed(
        self,
        fields: dict[str, Any] | None,
        update: dict[str, Any] | None = None,
    ) -> None:
        """Check the issues a create, update or transition payload points at.

        ``fields.parent``, the Epic Link custom field, and the ``parent``,
        Epic Link and ``issuelinks`` operations of an ``update`` payload each
        name another issue. Writing them would attach the issue to an issue
        outside the allowlist, so every named issue must be allowed. Clearing
        a parent or epic link (``None``) is allowed.

        Args:
            fields: The ``fields`` payload sent to Jira.
            update: The ``update`` payload sent to Jira, if any.
        """
        if self.allowed_projects() is None:
            return
        fields = fields or {}
        update = update or {}
        epic_link = None
        if any(k.startswith("customfield_") for k in (*fields, *update)):
            epic_link = self._epic_link_field_id()

        refs: list[object] = []
        for name in ("parent", epic_link):
            if name and name in fields:
                refs.append(_issue_reference(fields[name]))
        for name, operations in update.items():
            ops = operations if isinstance(operations, list) else [operations]
            for op in ops:
                if not isinstance(op, dict):
                    continue
                for verb in _REFERENCE_VERBS:
                    if verb not in op:
                        continue
                    value = op[verb]
                    if name in ("parent", epic_link):
                        refs.append(_issue_reference(value))
                    elif name == "issuelinks" and isinstance(value, dict):
                        refs.extend(
                            _issue_reference(value.get(side))
                            for side in ("inwardIssue", "outwardIssue")
                            if side in value
                        )
        for ref in refs:
            if ref is not None:
                self.ensure_issue_allowed(ref)

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
        if not items:
            # Downstream code would call Jira with no key to check.
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
            board = self._get_json(f"rest/agile/1.0/board/{path_segment(board_id)}")
            project_key = (board.get("location") or {}).get("projectKey")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira board {board_id!r}: {e}")
            raise _denied("board", board_id) from e
        if isinstance(project_key, str):
            with _denied_as("board", board_id):
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
            sprint = self._get_json(f"rest/agile/1.0/sprint/{path_segment(sprint_id)}")
            board_id = sprint.get("originBoardId")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira sprint {sprint_id!r}: {e}")
            raise _denied("sprint", sprint_id) from e
        if board_id is None:
            raise _denied("sprint", sprint_id)
        with _denied_as("sprint", sprint_id):
            self.ensure_board_allowed(board_id)

    def ensure_version_allowed(self, version_id: object) -> None:
        """Check the project a fix version belongs to."""
        if self.allowed_projects() is None:
            return
        try:
            version = self._get_json(f"rest/api/2/version/{path_segment(version_id)}")
            project_id = version.get("projectId")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira version {version_id!r}: {e}")
            raise _denied("version", version_id) from e
        if project_id is None:
            raise _denied("version", version_id)
        with _denied_as("version", version_id):
            self.ensure_project_id_allowed(project_id)

    def ensure_issue_link_allowed(self, link_id: object) -> None:
        """Check both issues joined by an issue link."""
        if self.allowed_projects() is None:
            return
        try:
            link = self._get_json(f"rest/api/2/issueLink/{path_segment(link_id)}")
            keys = [
                (link.get(side) or {}).get("key")
                for side in ("inwardIssue", "outwardIssue")
            ]
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Jira issue link {link_id!r}: {e}")
            raise _denied("issue link", link_id) from e
        with _denied_as("issue link", link_id):
            for key in keys:
                self.ensure_issue_allowed(key)

    def ensure_service_desk_allowed(self, service_desk_id: object) -> None:
        """Check the project behind a Jira Service Management service desk."""
        if self.allowed_projects() is None:
            return
        try:
            desk = self._get_json(
                f"rest/servicedeskapi/servicedesk/{path_segment(service_desk_id)}"
            )
            project_key = desk.get("projectKey")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve service desk {service_desk_id!r}: {e}")
            raise _denied("service desk", service_desk_id) from e
        if not isinstance(project_key, str):
            raise _denied("service desk", service_desk_id)
        with _denied_as("service desk", service_desk_id):
            self.ensure_project_allowed(project_key)
