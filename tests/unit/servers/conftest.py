"""Shared fixtures for server-level tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def assume_credentials_are_usable():
    """Treat configured credentials as valid for server wiring tests.

    ``main_lifespan`` verifies credentials against the live API before loading
    a service config. These tests exercise wiring with fake configs and must
    not depend on the network; the check itself is covered separately in
    tests/unit/test_startup_credential_validation.py.
    """
    with patch("mcp_atlassian.servers.main._credentials_are_usable", return_value=True):
        yield
