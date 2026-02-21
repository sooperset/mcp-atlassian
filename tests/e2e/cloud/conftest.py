"""Cloud E2E test configuration for Jira Cloud and Confluence Cloud.

Provides fixtures for running tests against real Atlassian Cloud instances.
Tests require the --cloud-e2e flag and valid Cloud credentials via env vars.

Pytest hooks (--cloud-e2e option, cloud_e2e marker, auto-skip) are registered
in the parent tests/e2e/conftest.py — NOT here. Pytest loads subdirectory
conftest files lazily after argument parsing.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import pytest
import requests

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_PROJECT_KEY = "E2E"
DEFAULT_SPACE_KEY = "E2E"


# --- Data Classes ---


@dataclass
class CloudInstanceInfo:
    """Connection info for Cloud instances, loaded from environment."""

    jira_url: str = ""
    confluence_url: str = ""
    username: str = ""
    api_token: str = ""
    project_key: str = DEFAULT_PROJECT_KEY
    space_key: str = DEFAULT_SPACE_KEY
    test_issue_key: str = ""
    test_page_id: str = ""
    oauth_access_token: str = ""
    oauth_cloud_id: str = ""

    @classmethod
    def from_env(cls) -> CloudInstanceInfo:
        """Create instance from CLOUD_E2E_* environment variables."""
        return cls(
            jira_url=os.environ.get("CLOUD_E2E_JIRA_URL", ""),
            confluence_url=os.environ.get("CLOUD_E2E_CONFLUENCE_URL", ""),
            username=os.environ.get("CLOUD_E2E_USERNAME", ""),
            api_token=os.environ.get("CLOUD_E2E_API_TOKEN", ""),
            project_key=os.environ.get("CLOUD_E2E_PROJECT_KEY", DEFAULT_PROJECT_KEY),
            space_key=os.environ.get("CLOUD_E2E_SPACE_KEY", DEFAULT_SPACE_KEY),
            oauth_access_token=os.environ.get("CLOUD_E2E_OAUTH_ACCESS_TOKEN", ""),
            oauth_cloud_id=os.environ.get("CLOUD_E2E_OAUTH_CLOUD_ID", ""),
        )

    def has_basic_auth(self) -> bool:
        return bool(self.jira_url and self.username and self.api_token)

    def has_oauth(self) -> bool:
        return bool(self.oauth_access_token and self.oauth_cloud_id)


@dataclass
class AuthVariant:
    """Named auth configuration pair."""

    name: str
    jira_config: JiraConfig
    confluence_config: ConfluenceConfig


class CloudResourceTracker:
    """Tracks resources created during Cloud E2E tests for cleanup."""

    def __init__(self) -> None:
        self.jira_issues: list[str] = []
        self.confluence_pages: list[str] = []

    def add_jira_issue(self, issue_key: str) -> None:
        self.jira_issues.append(issue_key)

    def add_confluence_page(self, page_id: str) -> None:
        self.confluence_pages.append(page_id)

    def cleanup(
        self,
        jira_client: JiraFetcher | None = None,
        confluence_client: ConfluenceFetcher | None = None,
    ) -> None:
        if jira_client:
            for key in reversed(self.jira_issues):
                try:
                    jira_client.delete_issue(key)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Failed to delete Jira issue %s: %s", key, e)
        if confluence_client:
            for page_id in reversed(self.confluence_pages):
                try:
                    confluence_client.delete_page(page_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Failed to delete page %s: %s", page_id, e)


# --- Helper Functions ---


def _check_cloud_health(info: CloudInstanceInfo) -> bool:
    """Check if Cloud instances are reachable and credentials work."""
    try:
        resp = requests.get(
            f"{info.jira_url}/rest/api/2/myself",
            auth=(info.username, info.api_token),
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("Jira Cloud health check failed: %s", resp.status_code)
            return False
    except requests.RequestException as e:
        logger.warning("Jira Cloud unreachable: %s", e)
        return False

    try:
        resp = requests.get(
            f"{info.confluence_url}/rest/api/space",
            params={"limit": "1"},
            auth=(info.username, info.api_token),
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("Confluence Cloud health check failed: %s", resp.status_code)
            return False
    except requests.RequestException as e:
        logger.warning("Confluence Cloud unreachable: %s", e)
        return False

    return True


def _find_or_create_test_issue(info: CloudInstanceInfo) -> Any:
    """Find existing Cloud E2E test issue or create one.

    Uses POST /rest/api/3/search/jql — Jira Cloud deprecated
    GET /rest/api/2/search (returns 410 Gone).
    """
    resp = requests.post(
        f"{info.jira_url}/rest/api/3/search/jql",
        json={
            "jql": (f'project={info.project_key} AND summary~"Cloud E2E Test Task"'),
            "maxResults": 1,
            "fields": ["id", "key", "summary"],
        },
        auth=(info.username, info.api_token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("total", 0) > 0:
        return data["issues"][0]["key"]

    resp = requests.post(
        f"{info.jira_url}/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": info.project_key},
                "summary": "Cloud E2E Test Task",
                "issuetype": {"name": "Task"},
                "description": "Auto-created for Cloud E2E testing.",
            }
        },
        auth=(info.username, info.api_token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["key"]


def _find_or_create_test_page(info: CloudInstanceInfo) -> Any:
    """Find existing Cloud E2E test page or create one."""
    resp = requests.get(
        f"{info.confluence_url}/rest/api/content",
        params={
            "spaceKey": info.space_key,
            "title": "Cloud E2E Test Page",
            "limit": "1",
        },
        auth=(info.username, info.api_token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("size", 0) > 0:
        return data["results"][0]["id"]

    resp = requests.post(
        f"{info.confluence_url}/rest/api/content",
        json={
            "type": "page",
            "title": "Cloud E2E Test Page",
            "space": {"key": info.space_key},
            "body": {
                "storage": {
                    "value": "<p>Auto-created for Cloud E2E testing.</p>",
                    "representation": "storage",
                }
            },
        },
        auth=(info.username, info.api_token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


# --- Config Factory Functions ---


def _make_jira_basic_config(info: CloudInstanceInfo) -> JiraConfig:
    return JiraConfig(
        url=info.jira_url,
        auth_type="basic",
        username=info.username,
        api_token=info.api_token,
    )


def _make_jira_byo_oauth_config(info: CloudInstanceInfo) -> JiraConfig:
    return JiraConfig(
        url=info.jira_url,
        auth_type="oauth",
        oauth_config=BYOAccessTokenOAuthConfig(
            access_token=info.oauth_access_token,
            cloud_id=info.oauth_cloud_id,
        ),
    )


def _make_confluence_basic_config(
    info: CloudInstanceInfo,
) -> ConfluenceConfig:
    return ConfluenceConfig(
        url=info.confluence_url,
        auth_type="basic",
        username=info.username,
        api_token=info.api_token,
    )


def _make_confluence_byo_oauth_config(
    info: CloudInstanceInfo,
) -> ConfluenceConfig:
    return ConfluenceConfig(
        url=info.confluence_url,
        auth_type="oauth",
        oauth_config=BYOAccessTokenOAuthConfig(
            access_token=info.oauth_access_token,
            cloud_id=info.oauth_cloud_id,
        ),
    )


# --- Fixtures ---


@pytest.fixture(scope="session")
def cloud_instance() -> CloudInstanceInfo:
    """Session-scoped fixture providing Cloud instance connection info.

    Loads credentials from env vars, performs health check,
    and discovers/creates test data.
    """
    info = CloudInstanceInfo.from_env()

    if not info.has_basic_auth():
        pytest.skip(
            "Cloud E2E requires CLOUD_E2E_JIRA_URL, "
            "CLOUD_E2E_USERNAME, and CLOUD_E2E_API_TOKEN"
        )

    if not info.confluence_url:
        pytest.skip("Cloud E2E requires CLOUD_E2E_CONFLUENCE_URL")

    if not _check_cloud_health(info):
        pytest.skip("Cloud instances not reachable or credentials invalid")

    info.test_issue_key = _find_or_create_test_issue(info)
    info.test_page_id = _find_or_create_test_page(info)

    logger.info(
        "Cloud instances ready: issue=%s page=%s oauth=%s",
        info.test_issue_key,
        info.test_page_id,
        info.has_oauth(),
    )
    return info


@pytest.fixture(scope="session")
def auth_variants(
    cloud_instance: CloudInstanceInfo,
) -> list[AuthVariant]:
    """Session-scoped list of auth variants to test.

    Always includes basic. Adds byo_oauth if OAuth env vars present.
    """
    variants = [
        AuthVariant(
            name="basic",
            jira_config=_make_jira_basic_config(cloud_instance),
            confluence_config=_make_confluence_basic_config(cloud_instance),
        ),
    ]

    if cloud_instance.has_oauth():
        variants.append(
            AuthVariant(
                name="byo_oauth",
                jira_config=_make_jira_byo_oauth_config(cloud_instance),
                confluence_config=_make_confluence_byo_oauth_config(cloud_instance),
            )
        )

    return variants


@pytest.fixture(scope="session")
def jira_fetcher(cloud_instance: CloudInstanceInfo) -> JiraFetcher:
    """Session-scoped default Jira fetcher (basic auth)."""
    config = _make_jira_basic_config(cloud_instance)
    return JiraFetcher(config=config)


@pytest.fixture(scope="session")
def confluence_fetcher(
    cloud_instance: CloudInstanceInfo,
) -> ConfluenceFetcher:
    """Session-scoped default Confluence fetcher (basic auth)."""
    config = _make_confluence_basic_config(cloud_instance)
    return ConfluenceFetcher(config=config)


@pytest.fixture
def resource_tracker(
    jira_fetcher: JiraFetcher,
    confluence_fetcher: ConfluenceFetcher,
) -> Generator[CloudResourceTracker, None, None]:
    """Function-scoped resource tracker with auto-cleanup."""
    tracker = CloudResourceTracker()
    yield tracker
    tracker.cleanup(
        jira_client=jira_fetcher,
        confluence_client=confluence_fetcher,
    )
