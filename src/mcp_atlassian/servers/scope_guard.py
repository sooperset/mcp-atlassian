"""Enforce JIRA_PROJECTS_FILTER and CONFLUENCE_SPACES_FILTER on every tool.

The allowlists are a boundary for the whole server, not only for search. Each
tool argument name is classified once here: either it identifies something
that lives in a project/space (and is resolved and checked before the tool
runs), or it does not. ``ErrorPreservingFastMCP`` runs the guard in front of
every registered tool, so a new tool inherits the check without code of its
own, and ``tests/unit/servers/test_scope_guard.py`` fails when a tool argument
is not classified.

Search arguments (``jql``, ``query``, ``projects_filter``, ``spaces_filter``)
are unscoped here because the search mixins AND the allowlist into the query
(see :mod:`mcp_atlassian.utils.query_scope`).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

import anyio

from mcp_atlassian.exceptions import ScopeViolationError

logger = logging.getLogger("mcp-atlassian.scope")

ScopeCheck = Callable[[Any, Any], None]
FetcherGetter = Callable[[Any], Awaitable[Any]]


def _method(name: str) -> ScopeCheck:
    def check(fetcher: Any, value: Any) -> None:
        getattr(fetcher, name)(value)

    check.__name__ = name
    return check


def _batch_issue_projects(fetcher: Any, value: Any) -> None:
    """Check ``project_key`` of every entry of batch_create_issues ``issues``."""
    try:
        items = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        # The tool rejects invalid JSON itself; nothing is created.
        return
    if not isinstance(items, list):
        return
    for item in items:
        project_key = item.get("project_key") if isinstance(item, dict) else None
        fetcher.ensure_project_allowed(project_key)


@dataclass(frozen=True)
class ScopePolicy:
    """How one service's tool arguments map to allowlist checks.

    Attributes:
        service: Service name used in messages.
        filter_attr: Config attribute holding the allowlist.
        lifespan_config_attr: ``MainAppContext`` attribute holding the config.
        env_var: Environment variable holding the operator allowlist, read
            when the server has no global config for the service.
        checks: Argument name to check, called as ``check(fetcher, value)``.
        unscoped_params: Argument names that do not identify a project/space
            object, or whose object is already checked through another
            argument of the same tool.
    """

    service: str
    filter_attr: str
    lifespan_config_attr: str
    env_var: str
    checks: Mapping[str, ScopeCheck]
    unscoped_params: frozenset[str]

    def classify(self, param: str) -> str | None:
        """Return ``"scoped"``, ``"unscoped"`` or None for an unknown name."""
        if param in self.checks:
            return "scoped"
        if param in self.unscoped_params:
            return "unscoped"
        return None


_COMMON_UNSCOPED = frozenset({"ctx", "limit", "start", "start_at", "expand"})

JIRA_SCOPE_POLICY = ScopePolicy(
    service="Jira",
    filter_attr="projects_filter",
    lifespan_config_attr="full_jira_config",
    env_var="JIRA_PROJECTS_FILTER",
    checks={
        "issue_key": _method("ensure_issue_allowed"),
        "inward_issue_key": _method("ensure_issue_allowed"),
        "outward_issue_key": _method("ensure_issue_allowed"),
        "epic_key": _method("ensure_issue_allowed"),
        "issue_keys": _method("ensure_issues_allowed"),
        "issue_ids_or_keys": _method("ensure_issues_allowed"),
        "project_key": _method("ensure_project_allowed"),
        "target_project_key": _method("ensure_project_allowed"),
        "board_id": _method("ensure_board_allowed"),
        "sprint_id": _method("ensure_sprint_allowed"),
        "version_id": _method("ensure_version_allowed"),
        "link_id": _method("ensure_issue_link_allowed"),
        "service_desk_id": _method("ensure_service_desk_allowed"),
        "issues": _batch_issue_projects,
    },
    unscoped_params=_COMMON_UNSCOPED
    | frozenset(
        {
            # Search: the allowlist is ANDed into the JQL by SearchMixin.
            "jql",
            "projects_filter",
            "page_token",
            # Global metadata, not stored in a project.
            "user_identifier",
            "username",
            "account_id",
            "query",
            "keyword",
            "refresh",
            "field_id",
            "context_id",
            "contains",
            "return_limit",
            "values_only",
            "name_filter",
            "board_name",
            "board_type",
            "include_archived",
            "max_results",
            "current_project_ids",
            # Sub-objects addressed through a checked issue, project or
            # service desk argument of the same tool.
            "comment_id",
            "form_id",
            "queue_id",
            "request_type_id",
            "issue_type_id",
            # Payload and output options.
            "fields",
            "comment_limit",
            "properties",
            "update_history",
            "include",
            # Epic children are fetched through SearchMixin, which ANDs the
            # allowlist into the JQL.
            "epic_summary_children",
            "max_epic_children",
            "use_display_names",
            "issue_type",
            "summary",
            "assignee",
            "description",
            "components",
            "additional_fields",
            "validate_only",
            "attachments",
            "attachments_base64",
            "transition",
            "comment",
            "comment_visibility",
            "worklog",
            "worklog_started",
            "return_fields",
            "body",
            "visibility",
            "public",
            "time_spent",
            "started",
            "original_estimate",
            "remaining_estimate",
            "link_type",
            "url",
            "title",
            "relationship",
            "icon_url",
            "transition_id",
            "name",
            "state",
            "start_date",
            "end_date",
            "release_date",
            "goal",
            "versions",
            "archived",
            "released",
            "request_field_values",
            "raise_on_behalf_of",
            "request_participants",
            "strict_on_behalf",
            "answers",
            "include_status_changes",
            "include_status_summary",
            "metrics",
            "working_hours_only",
            "include_raw_dates",
            "application_type",
            "data_type",
            "max_epics",
            "max_issues",
        }
    ),
)

CONFLUENCE_SCOPE_POLICY = ScopePolicy(
    service="Confluence",
    filter_attr="spaces_filter",
    lifespan_config_attr="full_confluence_config",
    env_var="CONFLUENCE_SPACES_FILTER",
    checks={
        "page_id": _method("ensure_content_allowed"),
        "parent_id": _method("ensure_content_allowed"),
        "target_parent_id": _method("ensure_content_allowed"),
        "source_page_id": _method("ensure_content_allowed"),
        "destination_parent_id": _method("ensure_content_allowed"),
        "content_id": _method("ensure_content_allowed"),
        "comment_id": _method("ensure_content_allowed"),
        "attachment_id": _method("ensure_content_allowed"),
        "space_key": _method("ensure_space_allowed"),
        "target_space_key": _method("ensure_space_allowed"),
        "destination_space_key": _method("ensure_space_allowed"),
        "space_id": _method("ensure_space_id_allowed"),
        "template_id": _method("ensure_template_allowed"),
    },
    unscoped_params=_COMMON_UNSCOPED
    | frozenset(
        {
            # Search: the allowlist is ANDed into the CQL by SearchMixin.
            "query",
            "spaces_filter",
            "cursor",
            # Global metadata, not stored in a space.
            "group_name",
            "user_identifier",
            "operation",
            "subject_type",
            # Payload and output options.
            "title",
            "include_metadata",
            "convert_to_markdown",
            "include_content",
            "include_folders",
            "content",
            "content_format",
            "content_file",
            "enable_heading_anchors",
            "emoji",
            "page_width",
            "table_layout",
            "subtype",
            "is_minor_edit",
            "version_comment",
            "heading_text",
            "new_content",
            "position",
            "body",
            "text_selection",
            "text_selection_match_count",
            "text_selection_match_index",
            "name",
            "version",
            "from_version",
            "to_version",
            "include_title",
            "file_path",
            "file_paths",
            "content_base64",
            "filename",
            "media_type",
            "comment",
            "minor_edit",
            "read_users",
            "read_groups",
            "edit_users",
            "edit_groups",
            "new_title",
            "copy_attachments",
        }
    ),
)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str | list | tuple) and not value)


def _filter_keys(value: Any) -> frozenset[str]:
    """Normalize an allowlist (comma string or list) to upper-cased keys."""
    if isinstance(value, str):
        items: list[Any] = value.split(",")
    elif isinstance(value, list | tuple | set | frozenset):
        items = list(value)
    else:
        return frozenset()
    return frozenset(str(k).strip().upper() for k in items if str(k).strip())


class ToolScopeGuard:
    """Check a tool call's arguments against the configured allowlist."""

    def __init__(self, policy: ScopePolicy, fetcher_getter: FetcherGetter) -> None:
        """Create a guard.

        Args:
            policy: The service's argument classification.
            fetcher_getter: ``async (ctx) -> fetcher``. Resolved at call time
                so the tool module's fetcher dependency is used.
        """
        self.policy = policy
        self._fetcher_getter = fetcher_getter

    def _lifespan_config(self, ctx: Any) -> Any:
        try:
            lifespan = ctx.request_context.lifespan_context
            app_ctx = (
                lifespan.get("app_lifespan_context")
                if isinstance(lifespan, dict)
                else None
            )
        except (AttributeError, LookupError, ValueError):
            return None
        if app_ctx is None:
            return None
        return getattr(app_ctx, self.policy.lifespan_config_attr, None)

    def operator_filter(self, ctx: Any) -> frozenset[str]:
        """Return the operator allowlist, independent of the request's credentials.

        The server's global config is the source when it exists; otherwise
        (for example a header-only deployment without ``JIRA_URL``) the
        environment variable is read directly. The per-request fetcher config
        is never consulted here, because it is built from caller input.
        """
        config = self._lifespan_config(ctx)
        if config is not None:
            return _filter_keys(getattr(config, self.policy.filter_attr, None))
        return _filter_keys(os.getenv(self.policy.env_var))

    async def __call__(self, tool_name: str, arguments: Mapping[str, Any]) -> None:
        """Raise ScopeViolationError if an argument is outside the allowlist.

        Args:
            tool_name: Registered tool name, for messages.
            arguments: Bound call arguments by parameter name, including ctx.
        """
        targets: list[tuple[str, Any]] = []
        unknown: list[str] = []
        for name, value in arguments.items():
            kind = self.policy.classify(name)
            if kind is None:
                unknown.append(name)
            elif kind == "scoped" and not _is_empty(value):
                targets.append((name, value))

        ctx = arguments.get("ctx")
        operator = self.operator_filter(ctx)
        if not operator and self._lifespan_config(ctx) is not None:
            # The server config is known and sets no allowlist.
            return
        if not operator and not targets and not unknown:
            return

        fetcher = await self._fetcher_getter(ctx)
        configured = _filter_keys(
            getattr(fetcher.config, self.policy.filter_attr, None)
        )
        if not operator and not configured:
            return
        if operator and configured != operator:
            # The fetcher serving this request does not carry the operator's
            # allowlist, so its searches and checks would not be bounded.
            logger.error(
                f"{self.policy.service} fetcher for tool '{tool_name}' does not "
                f"carry the operator {self.policy.env_var}; refusing."
            )
            raise ScopeViolationError(
                f"{self.policy.service} tool '{tool_name}' cannot be used: the "
                f"request's configuration does not apply the configured "
                f"{self.policy.env_var}."
            )

        if unknown:
            # A tool argument nobody classified could address anything; refuse
            # rather than guess while an allowlist is configured.
            logger.error(
                f"{self.policy.service} tool '{tool_name}' has unclassified "
                f"arguments {sorted(unknown)}; refusing under the allowlist."
            )
            raise ScopeViolationError(
                f"{self.policy.service} tool '{tool_name}' cannot be used while "
                f"the {self.policy.filter_attr} allowlist is configured."
            )

        for name, value in targets:
            await anyio.to_thread.run_sync(
                partial(self.policy.checks[name], fetcher, value)
            )
