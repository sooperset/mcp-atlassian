from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig


@dataclass(frozen=True)
class MainAppContext:
    """Context holding base configs and server settings (no fetchers)."""

    jira_base_config: JiraConfig | None = None
    confluence_base_config: ConfluenceConfig | None = None
    read_only: bool = False
    enabled_tools: list[str] | None = None
