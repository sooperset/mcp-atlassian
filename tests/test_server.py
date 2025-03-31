"""Unit tests for server"""

import os
from collections.abc import Generator
from contextlib import contextmanager

from mcp_atlassian.server import get_available_services


@contextmanager
def env_vars(new_env: dict[str, str | None]) -> Generator[None, None, None]:
    # Save the old values
    old_values = {k: os.getenv(k) for k in new_env.keys()}

    # Set the new values
    for k, v in new_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        # Put everything back to how it was
        for k, v in old_values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_no_service_available():
    with env_vars({"JIRA_URL": None, "CONFLUENCE_URL": None}):
        av = get_available_services()
        assert not av["jira"]
        assert not av["confluence"]


def test_available_services_confluence():
    # Cloud confluence with username/api token authentication
    with env_vars(
        {
            "JIRA_URL": None,
            "CONFLUENCE_URL": "https://my-company.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "john.doe@example.com",
            "CONFLUENCE_API_TOKEN": "my_api_token",
            "CONFLUENCE_PERSONAL_TOKEN": None,
        }
    ):
        av = get_available_services()
        assert not av["jira"]
        assert av["confluence"]

    # On prem/DC confluence with just token authentication
    with env_vars(
        {
            "JIRA_URL": None,
            "CONFLUENCE_URL": "https://confluence.localnetwork.local",
            "CONFLUENCE_USERNAME": None,
            "CONFLUENCE_API_TOKEN": None,
            "CONFLUENCE_PERSONAL_TOKEN": "Some personal token",
        }
    ):
        av = get_available_services()
        assert not av["jira"]
        assert av["confluence"]

    # On prem/DC confluence with username/api token basic authentication
    with env_vars(
        {
            "JIRA_URL": None,
            "CONFLUENCE_URL": "https://confluence.localnetwork.local",
            "CONFLUENCE_USERNAME": "john.doe",
            "CONFLUENCE_API_TOKEN": "your_confluence_password",
            "CONFLUENCE_PERSONAL_TOKEN": None,
        }
    ):
        av = get_available_services()
        assert not av["jira"]
        assert av["confluence"]


def test_available_services_jira():
    """Test available services"""
    # Cloud jira with username/api token authentication
    with env_vars(
        {
            "JIRA_URL": "https://my-company.atlassian.net",
            "JIRA_USERNAME": "john.doe@example.com",
            "JIRA_API_TOKEN": "my_api_token",
            "JIRA_PERSONAL_TOKEN": None,
            "CONFLUENCE_URL": None,
        }
    ):
        av = get_available_services()
        assert av["jira"]
        assert not av["confluence"]

    # On-prem/DC jira with just token authentication
    with env_vars(
        {
            "JIRA_URL": "https://jira.localnetwork.local",
            "JIRA_USERNAME": None,
            "JIRA_API_TOKEN": None,
            "JIRA_PERSONAL_TOKEN": "my_personal_token",
            "CONFLUENCE_URL": None,
        }
    ):
        av = get_available_services()
        assert av["jira"]
        assert not av["confluence"]
