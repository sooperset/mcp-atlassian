"""Parse query string parameters and create user configuration objects.

This module provides utility functions to parse query string parameters
and create user configuration objects for Jira and Confluence.
"""

from typing import Any

from ..confluence.config import ConfluenceConfig
from ..jira.config import JiraConfig


def user_config_from_request(
    config_params: dict[str, Any],
) -> tuple[JiraConfig | None, ConfluenceConfig | None] | None:
    """Create user configuration objects from request headers and query parameters.

    Args:
        config_params (dict[str, Any]): Dictionary of configuration parameters
            from the request headers and query parameters.

    Returns:
        tuple[JiraConfig | None, ConfluenceConfig | None] | None: Tuple of JiraConfig and ConfluenceConfig objects,
        or None if no valid configurations are found.
    """
    config = {
        "confluence-username": config_params.get("confluence-username"),
        "confluence-token": config_params.get("confluence-token"),
        "confluence-personal-token": config_params.get("confluence-personal-token"),
        "jira-username": config_params.get("jira-username"),
        "jira-token": config_params.get("jira-token"),
        "jira-personal-token": config_params.get("jira-personal-token"),
    }

    if not any(config.values()):
        return None

    if config["confluence-username"] and (
        config["confluence-token"] or config["confluence-personal-token"]
    ):
        confluence_config = ConfluenceConfig.from_request(
            username=config["confluence-username"],
            api_token=config["confluence-token"],
            personal_token=config["confluence-personal-token"],
        )
    else:
        confluence_config = None

    if config["jira-username"] and (
        config["jira-token"] or config["jira-personal-token"]
    ):
        jira_config = JiraConfig.from_request(
            username=config["jira-username"],
            api_token=config["jira-token"],
            personal_token=config["jira-personal-token"],
        )
    else:
        jira_config = None

    return (confluence_config, jira_config)
