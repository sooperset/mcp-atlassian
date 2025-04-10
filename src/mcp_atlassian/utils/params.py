"""Parse query string parameters and create user configuration objects.

This module provides utility functions to parse query string parameters
and create user configuration objects for Jira and Confluence.
"""

from collections import defaultdict
from typing import Any
from urllib.parse import unquote_plus

from ..confluence.config import ConfluenceConfig
from ..jira.config import JiraConfig


def parse_query_string_params(raw_query: str) -> dict:
    if not raw_query:
        return {}

    params = defaultdict(list)
    for pair in raw_query.split("&"):
        key_value = pair.split("=", 1)
        key = unquote_plus(key_value[0])
        value = unquote_plus(key_value[1]) if len(key_value) > 1 else None
        params[key].append(value)

    return dict(params)


def user_config_from_query_params(
    query_params: dict[str, Any],
) -> tuple[JiraConfig | None, ConfluenceConfig | None] | None:
    config = {
        "confluence-username": query_params.get("confluence-username"),
        "confluence-token": query_params.get("confluence-token"),
        "confluence-personal-token": query_params.get("confluence-personal-token"),
        "jira-username": query_params.get("jira-username"),
        "jira-token": query_params.get("jira-token"),
        "jira-personal-token": query_params.get("jira-personal-token"),
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
