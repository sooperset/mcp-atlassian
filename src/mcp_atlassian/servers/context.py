from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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

    Backward compatibility: full_jira_config and full_confluence_config may be
    passed as constructor kwargs; they are normalized to jira_configs and
    confluence_configs with "" as the primary key.
    """

    jira_configs: dict[str, JiraConfig] = None  # type: ignore
    confluence_configs: dict[str, ConfluenceConfig] = None  # type: ignore
    read_only: bool = False
    enabled_tools: list[str] | None = None

    def __init__(
        self,
        jira_configs: dict[str, JiraConfig] | None = None,
        confluence_configs: dict[str, ConfluenceConfig] | None = None,
        read_only: bool = False,
        enabled_tools: list[str] | None = None,
        *,
        full_jira_config: JiraConfig | None = None,
        full_confluence_config: ConfluenceConfig | None = None,
        **kwargs: Any,
    ) -> None:
        # Normalize legacy kwargs into jira_configs/confluence_configs
        if full_jira_config is not None:
            jira_configs = (jira_configs or {}) | {"": full_jira_config}
        if full_confluence_config is not None:
            confluence_configs = (confluence_configs or {}) | {
                "": full_confluence_config
            }
        object.__setattr__(self, "jira_configs", jira_configs or None)
        object.__setattr__(self, "confluence_configs", confluence_configs or None)
        object.__setattr__(self, "read_only", kwargs.get("read_only", read_only))
        object.__setattr__(
            self, "enabled_tools", kwargs.get("enabled_tools", enabled_tools)
        )

    # Backward compatibility properties
    @property
    def full_jira_config(self) -> JiraConfig | None:
        """Get primary Jira config for backward compatibility."""
        if self.jira_configs:
            return self.jira_configs.get("")
        return None

    @property
    def full_confluence_config(self) -> ConfluenceConfig | None:
        """Get primary Confluence config for backward compatibility."""
        if self.confluence_configs:
            return self.confluence_configs.get("")
        return None
