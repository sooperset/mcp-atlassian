from collections import defaultdict
from urllib.parse import unquote_plus
from typing import Any

from ..jira.config import JiraConfig
from ..confluence.config import ConfluenceConfig

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


def user_config_from_query_params(query_params: dict[str, Any]) -> tuple[JiraConfig | None, ConfluenceConfig | None] | None:
    config = {
        "confluence-username": query_params.get("confluence-username", None),
        "confluence-token": query_params.get("confluence-token", None),
        "confluence-personal-token": query_params.get("confluence-personal-token", None),
        "jira-username": query_params.get("jira-username", None),
        "jira-token": query_params.get("jira-token", None),
        "jira-personal-token": query_params.get("jira-personal-token", None),
    }

    if not any(config.values()):
        return None

    if config["confluence-username"] and (config["confluence-token"] or config["confluence-personal-token"]):
        confluence_config = ConfluenceConfig.from_request(
            username=config["confluence-username"],
            api_token=config["confluence-token"],
            personal_token=config["confluence-personal-token"],
        )
    else:
        confluence_config = None

    if config["jira-username"] and (config["jira-token"] or config["jira-personal-token"]):
        jira_config = JiraConfig.from_request(
            username=config["jira-username"],
            api_token=config["jira-token"],
            personal_token=config["jira-personal-token"],
        )
    else:
        jira_config = None

    return (confluence_config, jira_config)