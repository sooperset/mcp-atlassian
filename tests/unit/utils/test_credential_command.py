"""Tests for deferred credential resolution via *_COMMAND env vars."""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.credential_command import (
    CredentialCommandResolver,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# All *_COMMAND and target env vars that must be clean between tests.
_ALL_VARS = [
    "JIRA_URL",
    "JIRA_USERNAME",
    "JIRA_API_TOKEN",
    "JIRA_API_TOKEN_COMMAND",
    "JIRA_PERSONAL_TOKEN",
    "JIRA_PERSONAL_TOKEN_COMMAND",
    "CONFLUENCE_URL",
    "CONFLUENCE_USERNAME",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_API_TOKEN_COMMAND",
    "CONFLUENCE_PERSONAL_TOKEN",
    "CONFLUENCE_PERSONAL_TOKEN_COMMAND",
    "CREDENTIAL_COMMAND_TIMEOUT",
]


@pytest.fixture(autouse=True)
def _clean_env():
    """Ensure a clean environment for every test."""
    with patch.dict(os.environ, {}, clear=False) as env:
        for var in _ALL_VARS:
            env.pop(var, None)
        yield env


@pytest.fixture()
def resolver() -> CredentialCommandResolver:
    """Return a fresh resolver instance (not the global singleton)."""
    return CredentialCommandResolver()


# ---------------------------------------------------------------------------
# has_deferred_credentials
# ---------------------------------------------------------------------------


class TestHasDeferredCredentials:
    def test_no_command_vars(self, resolver: CredentialCommandResolver) -> None:
        assert resolver.has_deferred_credentials("jira") is False
        assert resolver.has_deferred_credentials("confluence") is False

    def test_jira_api_token_command(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_URL"] = "https://example.atlassian.net"
        os.environ["JIRA_USERNAME"] = "user@example.com"
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo secret"
        assert resolver.has_deferred_credentials("jira") is True
        assert resolver.has_deferred_credentials("confluence") is False

    def test_confluence_personal_token_command(
        self, resolver: CredentialCommandResolver
    ) -> None:
        os.environ["CONFLUENCE_URL"] = "https://confluence.example.com"
        os.environ["CONFLUENCE_PERSONAL_TOKEN_COMMAND"] = "echo secret"
        assert resolver.has_deferred_credentials("confluence") is True
        assert resolver.has_deferred_credentials("jira") is False

    def test_plain_var_takes_precedence(
        self, resolver: CredentialCommandResolver
    ) -> None:
        os.environ["JIRA_URL"] = "https://example.atlassian.net"
        os.environ["JIRA_USERNAME"] = "user@example.com"
        os.environ["JIRA_API_TOKEN"] = "already-set"
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo secret"
        assert resolver.has_deferred_credentials("jira") is False

    @pytest.mark.parametrize(
        "env",
        [
            {"JIRA_API_TOKEN_COMMAND": "echo secret"},
            {
                "JIRA_URL": "https://example.atlassian.net",
                "JIRA_API_TOKEN_COMMAND": "echo secret",
            },
            {
                "JIRA_URL": "https://example.atlassian.net",
                "JIRA_PERSONAL_TOKEN_COMMAND": "echo secret",
            },
        ],
    )
    def test_incomplete_cloud_configuration_is_not_deferred(
        self, resolver: CredentialCommandResolver, env: dict[str, str]
    ) -> None:
        os.environ.update(env)
        assert resolver.has_deferred_credentials("jira") is False

    def test_unknown_service(self, resolver: CredentialCommandResolver) -> None:
        assert resolver.has_deferred_credentials("unknown") is False


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


class TestResolve:
    def test_resolve_sets_env_var(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo my-secret-token"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="echo my-secret-token",
                returncode=0,
                stdout="my-secret-token\n",
                stderr="",
            )
            resolver.resolve("jira")

        assert os.environ["JIRA_API_TOKEN"] == "my-secret-token"
        mock_run.assert_called_once()

    def test_resolve_is_idempotent(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo secret"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="echo secret", returncode=0, stdout="secret\n", stderr=""
            )
            resolver.resolve("jira")
            resolver.resolve("jira")

        mock_run.assert_called_once()

    def test_command_failure(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "false"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="false", returncode=1, stdout="", stderr="command failed"
            )
            with pytest.raises(ValueError, match="failed.*exit code 1"):
                resolver.resolve("jira")

    def test_command_timeout(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "sleep 100"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="sleep 100", timeout=30
            )
            with pytest.raises(ValueError, match="timed out"):
                resolver.resolve("jira")

    def test_command_empty_output(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="echo", returncode=0, stdout="\n", stderr=""
            )
            with pytest.raises(ValueError, match="empty output"):
                resolver.resolve("jira")

    def test_command_not_found(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "nonexistent-binary"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("not found")
            with pytest.raises(ValueError, match="could not be started"):
                resolver.resolve("jira")

    def test_invalid_command_quoting(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "secret-tool 'unterminated"

        with pytest.raises(ValueError, match="invalid quoting"):
            resolver.resolve("jira")

    def test_skips_when_plain_var_set(
        self, resolver: CredentialCommandResolver
    ) -> None:
        os.environ["JIRA_API_TOKEN"] = "already-set"
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo should-not-run"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            resolver.resolve("jira")

        mock_run.assert_not_called()
        assert os.environ["JIRA_API_TOKEN"] == "already-set"

    def test_custom_timeout(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo secret"
        os.environ["CREDENTIAL_COMMAND_TIMEOUT"] = "5"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="echo secret", returncode=0, stdout="secret\n", stderr=""
            )
            resolver.resolve("jira")

        mock_run.assert_called_once_with(
            ["echo", "secret"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

    @pytest.mark.parametrize("timeout", ["invalid", "0", "-1"])
    def test_invalid_timeout(
        self, resolver: CredentialCommandResolver, timeout: str
    ) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo secret"
        os.environ["CREDENTIAL_COMMAND_TIMEOUT"] = timeout

        with pytest.raises(ValueError, match="must be a positive integer"):
            resolver.resolve("jira")

    def test_resolves_multiple_vars(self, resolver: CredentialCommandResolver) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "echo token1"
        os.environ["JIRA_PERSONAL_TOKEN_COMMAND"] = "echo token2"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(
                    args="echo token1", returncode=0, stdout="token1\n", stderr=""
                ),
                subprocess.CompletedProcess(
                    args="echo token2", returncode=0, stdout="token2\n", stderr=""
                ),
            ]
            resolver.resolve("jira")

        assert os.environ["JIRA_API_TOKEN"] == "token1"
        assert os.environ["JIRA_PERSONAL_TOKEN"] == "token2"
        assert mock_run.call_count == 2

    def test_failed_command_can_be_retried_without_partial_credentials(
        self, resolver: CredentialCommandResolver
    ) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "get-api-secret"
        os.environ["JIRA_PERSONAL_TOKEN_COMMAND"] = "get-pat-secret"
        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(
                    args=["get-api-secret"],
                    returncode=0,
                    stdout="api-secret\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    args=["get-pat-secret"],
                    returncode=1,
                    stdout="",
                    stderr="locked",
                ),
                subprocess.CompletedProcess(
                    args=["get-api-secret"],
                    returncode=0,
                    stdout="api-secret\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    args=["get-pat-secret"],
                    returncode=0,
                    stdout="pat-secret\n",
                    stderr="",
                ),
            ]

            with pytest.raises(ValueError, match="failed"):
                resolver.resolve("jira")
            assert "JIRA_API_TOKEN" not in os.environ
            assert "JIRA_PERSONAL_TOKEN" not in os.environ

            resolver.resolve("jira")

        assert os.environ["JIRA_API_TOKEN"] == "api-secret"
        assert os.environ["JIRA_PERSONAL_TOKEN"] == "pat-secret"
        assert mock_run.call_count == 4

    def test_concurrent_resolution_runs_command_once(
        self, resolver: CredentialCommandResolver
    ) -> None:
        os.environ["JIRA_API_TOKEN_COMMAND"] = "get-secret"
        command_started = Event()
        release_command = Event()

        def run_command(
            *args: object, **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            command_started.set()
            assert release_command.wait(timeout=1)
            return subprocess.CompletedProcess(
                args=["get-secret"], returncode=0, stdout="secret\n", stderr=""
            )

        with patch(
            "mcp_atlassian.utils.credential_command.subprocess.run",
            side_effect=run_command,
        ) as mock_run:
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(resolver.resolve, "jira")
                assert command_started.wait(timeout=1)
                second = executor.submit(resolver.resolve, "jira")
                release_command.set()
                first.result(timeout=1)
                second.result(timeout=1)

        mock_run.assert_called_once()

    def test_unknown_service_is_rejected(
        self, resolver: CredentialCommandResolver
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported credential service"):
            resolver.resolve("unknown")
