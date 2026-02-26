"""Toolset definitions and filtering utilities for MCP Atlassian.

Groups 68 tools into 21 named toolsets controlled via the TOOLSETS env var.
Supports 'all', 'default', and comma-separated toolset names.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TOOLSET_TAG_PREFIX = "toolset:"


@dataclass(frozen=True)
class ToolsetDefinition:
    """Metadata for a named toolset group."""

    name: str
    description: str
    default: bool


# --- Jira toolsets (15) ---

JIRA_TOOLSETS: dict[str, ToolsetDefinition] = {
    "jira_issues": ToolsetDefinition(
        name="jira_issues",
        description="Core issue operations: CRUD, search, batch, changelogs",
        default=True,
    ),
    "jira_fields": ToolsetDefinition(
        name="jira_fields",
        description="Field search and option retrieval",
        default=True,
    ),
    "jira_comments": ToolsetDefinition(
        name="jira_comments",
        description="Issue comment operations",
        default=True,
    ),
    "jira_transitions": ToolsetDefinition(
        name="jira_transitions",
        description="Workflow transition operations",
        default=True,
    ),
    "jira_projects": ToolsetDefinition(
        name="jira_projects",
        description="Project, version, and component management",
        default=False,
    ),
    "jira_agile": ToolsetDefinition(
        name="jira_agile",
        description="Agile boards, sprints, and related operations",
        default=False,
    ),
    "jira_links": ToolsetDefinition(
        name="jira_links",
        description="Issue links, epic links, and remote links",
        default=False,
    ),
    "jira_worklog": ToolsetDefinition(
        name="jira_worklog",
        description="Time tracking and worklog operations",
        default=False,
    ),
    "jira_attachments": ToolsetDefinition(
        name="jira_attachments",
        description="Attachment download and image retrieval",
        default=False,
    ),
    "jira_users": ToolsetDefinition(
        name="jira_users",
        description="User profile operations",
        default=False,
    ),
    "jira_watchers": ToolsetDefinition(
        name="jira_watchers",
        description="Issue watcher operations",
        default=False,
    ),
    "jira_service_desk": ToolsetDefinition(
        name="jira_service_desk",
        description="Jira Service Management queues and service desks",
        default=False,
    ),
    "jira_forms": ToolsetDefinition(
        name="jira_forms",
        description="ProForma form operations",
        default=False,
    ),
    "jira_metrics": ToolsetDefinition(
        name="jira_metrics",
        description="Issue dates and SLA metrics",
        default=False,
    ),
    "jira_development": ToolsetDefinition(
        name="jira_development",
        description="Development info (branches, PRs, commits)",
        default=False,
    ),
}

# --- Confluence toolsets (6) ---

CONFLUENCE_TOOLSETS: dict[str, ToolsetDefinition] = {
    "confluence_pages": ToolsetDefinition(
        name="confluence_pages",
        description="Page CRUD, search, children, and history",
        default=True,
    ),
    "confluence_comments": ToolsetDefinition(
        name="confluence_comments",
        description="Page comment operations",
        default=True,
    ),
    "confluence_labels": ToolsetDefinition(
        name="confluence_labels",
        description="Page label operations",
        default=False,
    ),
    "confluence_users": ToolsetDefinition(
        name="confluence_users",
        description="User search operations",
        default=False,
    ),
    "confluence_analytics": ToolsetDefinition(
        name="confluence_analytics",
        description="Page view analytics",
        default=False,
    ),
    "confluence_attachments": ToolsetDefinition(
        name="confluence_attachments",
        description="Attachment upload, download, and management",
        default=False,
    ),
}

# --- Combined registry ---

ALL_TOOLSETS: dict[str, ToolsetDefinition] = {
    **JIRA_TOOLSETS,
    **CONFLUENCE_TOOLSETS,
}

DEFAULT_TOOLSETS: set[str] = {
    name for name, defn in ALL_TOOLSETS.items() if defn.default
}


def get_enabled_toolsets() -> set[str]:
    """Parse the TOOLSETS env var into a set of enabled toolset names.

    Supports keywords 'all' (all 21 toolsets) and 'default' (6 defaults),
    plus comma-separated specific toolset names. Case-insensitive for keywords.

    When TOOLSETS is unset or empty, returns DEFAULT_TOOLSETS (6 core toolsets).
    Use ``TOOLSETS=all`` to explicitly enable all toolsets.

    Returns:
        A set of valid toolset names. Defaults to DEFAULT_TOOLSETS when unset.
        Unknown names are silently dropped with a warning. If only unknown
        names are given, returns an empty set (fail-closed).

    Examples:
        TOOLSETS unset -> DEFAULT_TOOLSETS (6 defaults)
        TOOLSETS="" -> DEFAULT_TOOLSETS (6 defaults)
        TOOLSETS="all" -> all 21 names
        TOOLSETS="default" -> 6 default names
        TOOLSETS="default,jira_agile" -> defaults + jira_agile
        TOOLSETS="typo_name" -> set() (fail-closed)
    """
    toolsets_str = os.getenv("TOOLSETS")
    if not toolsets_str:
        logger.info("TOOLSETS not set — using default toolsets.")
        return set(DEFAULT_TOOLSETS)

    # Split by comma and strip whitespace, filter empty tokens
    tokens = [t.strip() for t in toolsets_str.split(",")]
    tokens = [t for t in tokens if t]

    if not tokens:
        logger.info("TOOLSETS empty — using default toolsets.")
        return set(DEFAULT_TOOLSETS)

    result: set[str] = set()

    for token in tokens:
        normalized = token.lower()
        if normalized == "all":
            logger.info("TOOLSETS: 'all' keyword — enabling all toolsets.")
            return set(ALL_TOOLSETS.keys())
        elif normalized == "default":
            logger.info("TOOLSETS: 'default' keyword — adding default toolsets.")
            result |= DEFAULT_TOOLSETS
        elif token in ALL_TOOLSETS:
            result.add(token)
        else:
            logger.warning(f"TOOLSETS: unknown toolset name '{token}' — ignoring.")

    if result:
        logger.info(f"TOOLSETS: enabled toolsets: {sorted(result)}")
    else:
        logger.warning(
            "TOOLSETS: no valid toolset names found — all tools will be blocked (fail-closed)."
        )

    return result


def should_include_tool_by_toolset(
    tool_tags: set[str], enabled_toolsets: set[str] | None
) -> bool:
    """Check if a tool should be included based on toolset filtering.

    Args:
        tool_tags: The tool's tag set (e.g. {"jira", "read", "toolset:jira_issues"}).
        enabled_toolsets: Set of enabled toolset names, or None to include all tools.

    Returns:
        True if the tool should be included, False otherwise.
        Tools without a toolset tag are always included (graceful fallback).
    """
    if enabled_toolsets is None:
        return True

    toolset_name = get_toolset_tag(tool_tags)
    if toolset_name is None:
        logger.warning(
            f"Tool has no toolset tag in {tool_tags} — including by default."
        )
        return True

    return toolset_name in enabled_toolsets


def get_toolset_tag(tags: set[str]) -> str | None:
    """Extract the toolset name from a tool's tag set.

    Args:
        tags: The tool's tag set.

    Returns:
        The toolset name (without prefix) if found, None otherwise.
    """
    for tag in tags:
        if tag.startswith(TOOLSET_TAG_PREFIX):
            return tag[len(TOOLSET_TAG_PREFIX) :]
    return None
