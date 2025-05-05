"""Utility functions related to environment checking."""

import logging
import os

from .urls import is_atlassian_cloud_url

logger = logging.getLogger("mcp-atlassian.utils.environment")


def get_available_services() -> dict[str, bool | None]:
    """Determine which services are available based on environment variables."""
    confluence_url = os.getenv("CONFLUENCE_URL")
    if confluence_url:
        is_cloud = is_atlassian_cloud_url(confluence_url)
        if is_cloud:
            confluence_is_setup = all(
                [
                    confluence_url,
                    os.getenv("CONFLUENCE_USERNAME"),
                    os.getenv("CONFLUENCE_API_TOKEN"),
                ]
            )
            logger.info("Using Confluence Cloud authentication method")
        else:
            confluence_is_setup = all(
                [
                    confluence_url,
                    os.getenv("CONFLUENCE_PERSONAL_TOKEN")
                    or (
                        os.getenv("CONFLUENCE_USERNAME")
                        and os.getenv("CONFLUENCE_API_TOKEN")
                    ),
                ]
            )
            logger.info("Using Confluence Server/Data Center authentication method")
    else:
        confluence_is_setup = False

    jira_url = os.getenv("JIRA_URL")
    if jira_url:
        is_cloud = is_atlassian_cloud_url(jira_url)
        if is_cloud:
            jira_is_setup = all(
                [
                    jira_url,
                    os.getenv("JIRA_USERNAME"),
                    os.getenv("JIRA_API_TOKEN"),
                ]
            )
            logger.info("Using Jira Cloud authentication method")
        else:
            jira_is_setup = all(
                [
                    jira_url,
                    os.getenv("JIRA_PERSONAL_TOKEN")
                    or (os.getenv("JIRA_USERNAME") and os.getenv("JIRA_API_TOKEN")),
                ]
            )
            logger.info("Using Jira Server/Data Center authentication method")
    else:
        jira_is_setup = False

    return {"confluence": confluence_is_setup, "jira": jira_is_setup}
