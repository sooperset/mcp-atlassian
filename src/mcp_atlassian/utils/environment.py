"""Utility functions related to environment checking."""

import logging
import os

from .urls import is_atlassian_cloud_url

logger = logging.getLogger("mcp-atlassian.utils.environment")


def _check_service_auth(
    service_name: str,
    service_url: str,
    client_id_envs: tuple[str, str],
    client_secret_envs: tuple[str, str],
    access_token_envs: tuple[str, str],
    username_env: str,
    api_env: str,
    pat_env: str,
) -> bool:
    """Detect whether a single Atlassian service is authenticated.

    Args:
        service_name: Human-readable service name (e.g. ``"Confluence"``).
        service_url: URL of the service instance.
        client_id_envs: ``(shared_env, service_env)`` pair for OAuth client ID.
        client_secret_envs: ``(shared_env, service_env)`` pair for OAuth client secret.
        access_token_envs: ``(shared_env, service_env)`` pair for OAuth access token.
        username_env: Env var name for the Basic Auth username.
        api_env: Env var name for the Basic Auth API token / password.
        pat_env: Env var name for the Personal Access Token (Server/DC only).

    Returns:
        ``True`` when a valid auth configuration is detected, ``False`` otherwise.
    """
    is_cloud = is_atlassian_cloud_url(service_url)

    client_id = os.getenv(client_id_envs[0]) or os.getenv(client_id_envs[1])
    client_secret = os.getenv(client_secret_envs[0]) or os.getenv(client_secret_envs[1])
    access_token = os.getenv(access_token_envs[0]) or os.getenv(access_token_envs[1])
    cloud_id = os.getenv("ATLASSIAN_OAUTH_CLOUD_ID")

    # Cloud OAuth check (needs cloud_id)
    if all([client_id, client_secret, cloud_id]):
        logger.info("Using %s OAuth 2.0 (3LO) authentication (Cloud)", service_name)
        return True

    # DC OAuth check (no cloud_id, but has client credentials + non-cloud URL)
    if not is_cloud and client_id and client_secret:
        logger.info("Using %s OAuth 2.0 authentication (Data Center)", service_name)
        return True

    # Cloud BYO access token
    if all([access_token, cloud_id]):
        logger.info(
            "Using %s OAuth 2.0 (3LO) authentication (Cloud) "
            "with provided access token",
            service_name,
        )
        return True

    # DC BYO access token (no cloud_id, non-cloud URL)
    if not is_cloud and access_token:
        logger.info(
            "Using %s OAuth 2.0 authentication (Data Center) "
            "with provided access token",
            service_name,
        )
        return True

    if is_cloud:  # Cloud non-OAuth
        if os.getenv(username_env) and os.getenv(api_env):
            logger.info("Using %s Cloud Basic Authentication (API Token)", service_name)
            return True
    else:  # Server/Data Center non-OAuth
        if os.getenv(pat_env) or (os.getenv(username_env) and os.getenv(api_env)):
            logger.info(
                "Using %s Server/Data Center authentication (PAT or Basic Auth)",
                service_name,
            )
            return True

    return False


def get_available_services(
    headers: dict[str, str] | None = None,
) -> dict[str, bool | None]:
    """Determine which services are available based on environment variables and optional headers."""
    headers = headers or {}

    confluence_url = os.getenv("CONFLUENCE_URL")
    confluence_is_setup = False
    if confluence_url:
        confluence_is_setup = _check_service_auth(
            service_name="Confluence",
            service_url=confluence_url,
            client_id_envs=("ATLASSIAN_OAUTH_CLIENT_ID", "CONFLUENCE_OAUTH_CLIENT_ID"),
            client_secret_envs=(
                "ATLASSIAN_OAUTH_CLIENT_SECRET",
                "CONFLUENCE_OAUTH_CLIENT_SECRET",
            ),
            access_token_envs=(
                "ATLASSIAN_OAUTH_ACCESS_TOKEN",
                "CONFLUENCE_OAUTH_ACCESS_TOKEN",
            ),
            username_env="CONFLUENCE_USERNAME",
            api_env="CONFLUENCE_API_TOKEN",
            pat_env="CONFLUENCE_PERSONAL_TOKEN",
        )

    if not confluence_is_setup and os.getenv("ATLASSIAN_OAUTH_ENABLE", "").lower() in (
        "true",
        "1",
        "yes",
    ):
        confluence_is_setup = True
        logger.info(
            "Using Confluence minimal OAuth configuration "
            "- expecting user-provided tokens via headers"
        )

    if not confluence_is_setup:
        confluence_token = headers.get("X-Atlassian-Confluence-Personal-Token")
        confluence_url_header = headers.get("X-Atlassian-Confluence-Url")

        if confluence_token and confluence_url_header:
            confluence_is_setup = True
            logger.info("Using Confluence authentication from header personal token")

    jira_url = os.getenv("JIRA_URL")
    jira_is_setup = False
    if jira_url:
        jira_is_setup = _check_service_auth(
            service_name="Jira",
            service_url=jira_url,
            client_id_envs=("ATLASSIAN_OAUTH_CLIENT_ID", "JIRA_OAUTH_CLIENT_ID"),
            client_secret_envs=(
                "ATLASSIAN_OAUTH_CLIENT_SECRET",
                "JIRA_OAUTH_CLIENT_SECRET",
            ),
            access_token_envs=(
                "ATLASSIAN_OAUTH_ACCESS_TOKEN",
                "JIRA_OAUTH_ACCESS_TOKEN",
            ),
            username_env="JIRA_USERNAME",
            api_env="JIRA_API_TOKEN",
            pat_env="JIRA_PERSONAL_TOKEN",
        )

    if not jira_is_setup and os.getenv("ATLASSIAN_OAUTH_ENABLE", "").lower() in (
        "true",
        "1",
        "yes",
    ):
        jira_is_setup = True
        logger.info(
            "Using Jira minimal OAuth configuration "
            "- expecting user-provided tokens via headers"
        )

    if not jira_is_setup:
        jira_token = headers.get("X-Atlassian-Jira-Personal-Token")
        jira_url_header = headers.get("X-Atlassian-Jira-Url")

        if jira_token and jira_url_header:
            jira_is_setup = True
            logger.info("Using Jira authentication from header personal token")

    if not confluence_is_setup:
        logger.info(
            "Confluence is not configured or required environment variables are missing."
        )
    if not jira_is_setup:
        logger.info(
            "Jira is not configured or required environment variables are missing."
        )

    return {"confluence": confluence_is_setup, "jira": jira_is_setup}
