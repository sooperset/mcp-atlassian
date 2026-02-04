from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig


@dataclass(frozen=True)
class MainAppContext:
    """
    Context holding fully configured Jira and Confluence configurations
    loaded from environment variables at server startup.
    These configurations include any global/default authentication details.

    For multi-instance support:
    - jira_configs: dict[str, JiraConfig] where "" is primary instance
    - confluence_configs: dict[str, ConfluenceConfig] where "" is primary instance
    """

    jira_configs: dict[str, "JiraConfig"] = None  # type: ignore
    confluence_configs: dict[str, "ConfluenceConfig"] = None  # type: ignore
    read_only: bool = False
    enabled_tools: list[str] | None = None

    # Backward compatibility properties
    @property
    def full_jira_config(self) -> "JiraConfig | None":
        """Get primary Jira config for backward compatibility."""
        if self.jira_configs:
            return self.jira_configs.get("")
        return None

    @property
    def full_confluence_config(self) -> "ConfluenceConfig | None":
        """Get primary Confluence config for backward compatibility."""
        if self.confluence_configs:
            return self.confluence_configs.get("")
        return None
