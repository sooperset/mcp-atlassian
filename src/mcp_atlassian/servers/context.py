from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_atlassian.confluence import ConfluenceFetcher
    from mcp_atlassian.jira import JiraFetcher


@dataclass(frozen=True)
class MainAppContext:
    """Context holding initialized fetchers and server settings."""

    jira: JiraFetcher | None = None
    confluence: ConfluenceFetcher | None = None
    read_only: bool = False
    enabled_tools: list[str] | None = None
