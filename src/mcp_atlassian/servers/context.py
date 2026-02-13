from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig
    from mcp_atlassian.zephyr.config import ZephyrConfig


@dataclass(frozen=True)
class MainAppContext:
    """
    Context holding fully configured Jira, Confluence, and Zephyr configurations
    loaded from environment variables at server startup.
    These configurations include any global/default authentication details.
    """

    full_jira_config: JiraConfig | None = None
    full_confluence_config: ConfluenceConfig | None = None
    full_zephyr_config: ZephyrConfig | None = None
    read_only: bool = False
    enabled_tools: list[str] | None = None
