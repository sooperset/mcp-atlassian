"""E2E test configuration for Jira DC and Confluence DC instances.

Provides fixtures for running tests against real Data Center instances.
Tests require the --dc-e2e flag and reachable DC instances.
"""

from __future__ import annotations

import base64
import logging
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig

logger = logging.getLogger(__name__)

# Default DC instance settings
DEFAULT_JIRA_URL = "http://localhost:8080"
DEFAULT_CONFLUENCE_URL = "http://localhost:8090"
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin123"
DEFAULT_PROJECT_KEY = "E2E"
DEFAULT_SPACE_KEY = "E2E"


# --- Pytest Plugin ---


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --dc-e2e and --cloud-e2e command-line options."""
    parser.addoption(
        "--dc-e2e",
        action="store_true",
        default=False,
        help="Run E2E tests against DC instances",
    )
    parser.addoption(
        "--cloud-e2e",
        action="store_true",
        default=False,
        help="Run E2E tests against Cloud instances",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register dc_e2e and cloud_e2e markers."""
    config.addinivalue_line(
        "markers",
        "dc_e2e: mark test as requiring DC instances (Jira DC + Confluence DC)",
    )
    config.addinivalue_line(
        "markers",
        "cloud_e2e: mark test as requiring Cloud instances (Jira Cloud + Confluence Cloud)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-skip dc_e2e/cloud_e2e tests unless their flags are passed."""
    run_dc = config.getoption("--dc-e2e")
    run_cloud = config.getoption("--cloud-e2e")

    skip_dc = pytest.mark.skip(reason="need --dc-e2e option to run")
    skip_cloud = pytest.mark.skip(reason="need --cloud-e2e option to run")

    for item in items:
        if "dc_e2e" in item.keywords and not run_dc:
            item.add_marker(skip_dc)
        if "cloud_e2e" in item.keywords and not run_cloud:
            item.add_marker(skip_cloud)


# --- Data Classes ---


@dataclass
class DCInstanceInfo:
    """Connection info for DC instances."""

    jira_url: str = DEFAULT_JIRA_URL
    confluence_url: str = DEFAULT_CONFLUENCE_URL
    admin_username: str = DEFAULT_ADMIN_USER
    admin_password: str = DEFAULT_ADMIN_PASS
    project_key: str = DEFAULT_PROJECT_KEY
    space_key: str = DEFAULT_SPACE_KEY
    test_issue_key: str = ""
    test_page_id: str = ""
    jira_pat: str = ""
    confluence_pat: str = ""
    admin_email: str = ""
    _cleanup_issue_keys: list[str] = field(default_factory=list)
    _cleanup_page_ids: list[str] = field(default_factory=list)


@dataclass
class AuthVariant:
    """Named auth configuration pair."""

    name: str
    jira_config: JiraConfig
    confluence_config: ConfluenceConfig


class DCResourceTracker:
    """Tracks resources created during E2E tests for cleanup."""

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


# --- Helper Functions (raw REST API calls) ---


def _check_dc_health(url: str) -> bool:
    """Check if a DC instance is reachable."""
    try:
        resp = requests.get(f"{url}/status", timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _find_or_create_test_issue(info: DCInstanceInfo) -> Any:
    """Find existing E2E test issue or create one."""
    resp = requests.get(
        f"{info.jira_url}/rest/api/2/search",
        params={
            "jql": (f'project={info.project_key} AND summary~"E2E Test Task"'),
            "maxResults": "1",
        },
        auth=(info.admin_username, info.admin_password),
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
                "summary": "E2E Test Task",
                "issuetype": {"name": "Task"},
                "description": "Auto-created for E2E testing.",
            }
        },
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["key"]


def _find_or_create_test_page(info: DCInstanceInfo) -> Any:
    """Find existing E2E test page or create one."""
    resp = requests.get(
        f"{info.confluence_url}/rest/api/content",
        params={
            "spaceKey": info.space_key,
            "title": "E2E Test Page",
            "limit": "1",
        },
        auth=(info.admin_username, info.admin_password),
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
            "title": "E2E Test Page",
            "space": {"key": info.space_key},
            "body": {
                "storage": {
                    "value": "<p>Auto-created for E2E testing.</p>",
                    "representation": "storage",
                }
            },
        },
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _create_jira_pat(info: DCInstanceInfo) -> Any:
    """Create a Jira PAT via REST API."""
    resp = requests.post(
        f"{info.jira_url}/rest/pat/latest/tokens",
        json={"name": "e2e-pytest", "expirationDuration": 90},
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("rawToken") or data["token"]


def _create_confluence_pat(info: DCInstanceInfo) -> Any:
    """Create a Confluence PAT via REST API."""
    resp = requests.post(
        (f"{info.confluence_url}/rest/de.resolution.apitokenauth/1.0/user/token"),
        json={"tokenName": "e2e-pytest"},
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("rawToken") or data["token"]


# 1x1 red PNG (67 bytes) — minimal valid image for attachment tests
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "2mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)


def _get_admin_email(info: DCInstanceInfo) -> str:
    """Fetch admin email via /rest/api/2/myself."""
    resp = requests.get(
        f"{info.jira_url}/rest/api/2/myself",
        auth=(info.admin_username, info.admin_password),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("emailAddress", "")


def _create_image_test_issue(info: DCInstanceInfo) -> str:
    """Create a Jira issue and upload a tiny PNG attachment."""
    uid = uuid.uuid4().hex[:8]
    resp = requests.post(
        f"{info.jira_url}/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": info.project_key},
                "summary": f"E2E Image Test {uid}",
                "issuetype": {"name": "Task"},
                "description": "Auto-created for image E2E tests.",
            }
        },
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    )
    resp.raise_for_status()
    issue_key = resp.json()["key"]
    info._cleanup_issue_keys.append(issue_key)

    # Upload image attachment
    requests.post(
        f"{info.jira_url}/rest/api/2/issue/{issue_key}/attachments",
        headers={"X-Atlassian-Token": "no-check"},
        files={"file": ("test.png", TINY_PNG, "image/png")},
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    ).raise_for_status()

    return issue_key


def _delete_issue(info: DCInstanceInfo, issue_key: str) -> None:
    """Delete a Jira issue (best-effort)."""
    try:
        requests.delete(
            f"{info.jira_url}/rest/api/2/issue/{issue_key}",
            auth=(info.admin_username, info.admin_password),
            timeout=15,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete issue %s", issue_key)


def _create_image_test_page(info: DCInstanceInfo) -> str:
    """Create a Confluence page with ac:image macro and upload a PNG."""
    uid = uuid.uuid4().hex[:8]
    storage_body = (
        "<p>Text before image</p>"
        '<ac:image><ri:attachment ri:filename="test.png"/></ac:image>'
        "<p>Text after image</p>"
    )
    resp = requests.post(
        f"{info.confluence_url}/rest/api/content",
        json={
            "type": "page",
            "title": f"E2E Image Test {uid}",
            "space": {"key": info.space_key},
            "body": {
                "storage": {
                    "value": storage_body,
                    "representation": "storage",
                }
            },
        },
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    )
    resp.raise_for_status()
    page_id = resp.json()["id"]
    info._cleanup_page_ids.append(page_id)

    # Upload image attachment
    requests.post(
        f"{info.confluence_url}/rest/api/content/{page_id}/child/attachment",
        headers={"X-Atlassian-Token": "no-check"},
        files={"file": ("test.png", TINY_PNG, "image/png")},
        auth=(info.admin_username, info.admin_password),
        timeout=30,
    ).raise_for_status()

    return page_id


def _delete_page(info: DCInstanceInfo, page_id: str) -> None:
    """Delete a Confluence page (best-effort)."""
    try:
        requests.delete(
            f"{info.confluence_url}/rest/api/content/{page_id}",
            auth=(info.admin_username, info.admin_password),
            timeout=15,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete page %s", page_id)


# --- Config Factory Functions ---


def _make_jira_basic_config(info: DCInstanceInfo) -> JiraConfig:
    return JiraConfig(
        url=info.jira_url,
        auth_type="basic",
        username=info.admin_username,
        api_token=info.admin_password,
        ssl_verify=False,
    )


def _make_jira_pat_config(info: DCInstanceInfo) -> JiraConfig:
    return JiraConfig(
        url=info.jira_url,
        auth_type="pat",
        personal_token=info.jira_pat,
        ssl_verify=False,
    )


def _make_jira_byo_oauth_config(
    info: DCInstanceInfo,
) -> JiraConfig:
    return JiraConfig(
        url=info.jira_url,
        auth_type="oauth",
        oauth_config=BYOAccessTokenOAuthConfig(
            access_token=info.jira_pat,
            base_url=info.jira_url,
        ),
        ssl_verify=False,
    )


def _make_confluence_basic_config(
    info: DCInstanceInfo,
) -> ConfluenceConfig:
    return ConfluenceConfig(
        url=info.confluence_url,
        auth_type="basic",
        username=info.admin_username,
        api_token=info.admin_password,
        ssl_verify=False,
    )


def _make_confluence_pat_config(
    info: DCInstanceInfo,
) -> ConfluenceConfig:
    return ConfluenceConfig(
        url=info.confluence_url,
        auth_type="pat",
        personal_token=info.confluence_pat,
        ssl_verify=False,
    )


def _make_confluence_byo_oauth_config(
    info: DCInstanceInfo,
) -> ConfluenceConfig:
    return ConfluenceConfig(
        url=info.confluence_url,
        auth_type="oauth",
        oauth_config=BYOAccessTokenOAuthConfig(
            access_token=info.confluence_pat,
            base_url=info.confluence_url,
        ),
        ssl_verify=False,
    )


# --- Fixtures ---


@pytest.fixture(scope="session")
def dc_instance() -> DCInstanceInfo:
    """Session-scoped fixture providing DC instance connection info.

    Discovers test data and creates PATs at session start.
    Skips entire session if instances are unreachable.
    """
    info = DCInstanceInfo()

    if not _check_dc_health(info.jira_url):
        pytest.skip(f"Jira DC not reachable at {info.jira_url}")
    if not _check_dc_health(info.confluence_url):
        pytest.skip(f"Confluence DC not reachable at {info.confluence_url}")

    info.test_issue_key = _find_or_create_test_issue(info)
    info.test_page_id = _find_or_create_test_page(info)

    try:
        info.admin_email = _get_admin_email(info)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get admin email: %s", e)

    try:
        info.jira_pat = _create_jira_pat(info)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to create Jira PAT: %s", e)
    try:
        info.confluence_pat = _create_confluence_pat(info)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to create Confluence PAT: %s", e)

    logger.info(
        "DC instances ready: issue=%s page=%s jira_pat=%s confluence_pat=%s email=%s",
        info.test_issue_key,
        info.test_page_id,
        bool(info.jira_pat),
        bool(info.confluence_pat),
        info.admin_email,
    )
    return info


@pytest.fixture(scope="session")
def auth_variants(
    dc_instance: DCInstanceInfo,
) -> list[AuthVariant]:
    """Session-scoped list of auth variants to test.

    Jira and Confluence PATs are independent — if only Jira PAT is
    available, pat/byo_oauth variants still include Jira configs
    (Confluence falls back to basic auth for those variants).
    """
    variants = [
        AuthVariant(
            name="basic",
            jira_config=_make_jira_basic_config(dc_instance),
            confluence_config=_make_confluence_basic_config(dc_instance),
        ),
    ]
    has_jira_pat = bool(dc_instance.jira_pat)
    has_confluence_pat = bool(dc_instance.confluence_pat)

    if has_jira_pat or has_confluence_pat:
        variants.append(
            AuthVariant(
                name="pat",
                jira_config=(
                    _make_jira_pat_config(dc_instance)
                    if has_jira_pat
                    else _make_jira_basic_config(dc_instance)
                ),
                confluence_config=(
                    _make_confluence_pat_config(dc_instance)
                    if has_confluence_pat
                    else _make_confluence_basic_config(dc_instance)
                ),
            )
        )
        variants.append(
            AuthVariant(
                name="byo_oauth",
                jira_config=(
                    _make_jira_byo_oauth_config(dc_instance)
                    if has_jira_pat
                    else _make_jira_basic_config(dc_instance)
                ),
                confluence_config=(
                    _make_confluence_byo_oauth_config(dc_instance)
                    if has_confluence_pat
                    else _make_confluence_basic_config(dc_instance)
                ),
            )
        )
    return variants


@pytest.fixture(scope="session")
def jira_fetcher(dc_instance: DCInstanceInfo) -> JiraFetcher:
    """Session-scoped default Jira fetcher (basic auth)."""
    config = _make_jira_basic_config(dc_instance)
    return JiraFetcher(config=config)


@pytest.fixture(scope="session")
def confluence_fetcher(
    dc_instance: DCInstanceInfo,
) -> ConfluenceFetcher:
    """Session-scoped default Confluence fetcher (basic auth)."""
    config = _make_confluence_basic_config(dc_instance)
    return ConfluenceFetcher(config=config)


@pytest.fixture
def resource_tracker(
    jira_fetcher: JiraFetcher,
    confluence_fetcher: ConfluenceFetcher,
) -> Generator[DCResourceTracker, None, None]:
    """Function-scoped resource tracker with auto-cleanup."""
    tracker = DCResourceTracker()
    yield tracker
    tracker.cleanup(
        jira_client=jira_fetcher,
        confluence_client=confluence_fetcher,
    )


@pytest.fixture(scope="module")
def dc_image_issue(
    dc_instance: DCInstanceInfo,
) -> Generator[str, None, None]:
    """Module-scoped Jira issue with an image attachment."""
    try:
        key = _create_image_test_issue(dc_instance)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Failed to create image test issue: {exc}")
    yield key
    _delete_issue(dc_instance, key)


@pytest.fixture(scope="module")
def dc_image_page(
    dc_instance: DCInstanceInfo,
) -> Generator[str, None, None]:
    """Module-scoped Confluence page with an image attachment."""
    try:
        page_id = _create_image_test_page(dc_instance)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Failed to create image test page: {exc}")
    yield page_id
    _delete_page(dc_instance, page_id)
