"""Tests for deferred credential resolution via *_COMMAND env vars."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.credential_command import (
    CredentialCommandResolver,
    _parse_command,
    deferred_pat_outranks,
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

    def test_windows_command_uses_native_line(self) -> None:
        command = 'op read "op://Vault/Jira PAT/credential"'
        os.environ["JIRA_PERSONAL_TOKEN_COMMAND"] = command
        resolver = CredentialCommandResolver(is_windows=True)

        with patch("mcp_atlassian.utils.credential_command.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=command, returncode=0, stdout="pat-token\n", stderr=""
            )
            resolver.resolve("jira")

        mock_run.assert_called_once_with(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )

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
            stdin=subprocess.DEVNULL,
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

    def test_command_cannot_consume_stdin(
        self, resolver: CredentialCommandResolver
    ) -> None:
        """A helper reading stdin must not see the MCP stdio transport.

        Runs a real subprocess with a readable pipe on file descriptor 0. Under
        pytest's default capture fd 0 is already ``/dev/null``, so the pipe is
        what makes this fail when the child inherits stdin.
        """
        frame = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        os.environ["JIRA_API_TOKEN_COMMAND"] = shlex.join(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write(sys.stdin.read() or 'ISOLATED')",
            ]
        )

        read_fd, write_fd = os.pipe()
        os.write(write_fd, frame)
        os.close(write_fd)
        saved_stdin = os.dup(0)
        try:
            os.dup2(read_fd, 0)
            resolver.resolve("jira")
            leftover = os.read(0, len(frame))
        finally:
            os.dup2(saved_stdin, 0)
            os.close(saved_stdin)
            os.close(read_fd)

        assert os.environ["JIRA_API_TOKEN"] == "ISOLATED"
        assert leftover == frame


# ---------------------------------------------------------------------------
# _parse_command
# ---------------------------------------------------------------------------


class TestParseCommand:
    def test_windows_returns_raw_string(self) -> None:
        """Windows argument rules are applied by CreateProcess, not shlex."""
        command = 'op read "op://Vault/Jira PAT/credential"'
        assert (
            _parse_command(command, "JIRA_PERSONAL_TOKEN_COMMAND", is_windows=True)
            == command
        )

    def test_windows_keeps_quoted_executable_path(self) -> None:
        command = '"C:\\Program Files\\1Password CLI\\op.exe" read op://Vault/PAT'
        assert (
            _parse_command(command, "JIRA_PERSONAL_TOKEN_COMMAND", is_windows=True)
            == command
        )

    def test_posix_splits_without_quotes(self) -> None:
        assert _parse_command(
            'op read "op://Vault/Jira PAT/credential"',
            "JIRA_PERSONAL_TOKEN_COMMAND",
            is_windows=False,
        ) == ["op", "read", "op://Vault/Jira PAT/credential"]

    @pytest.mark.parametrize("is_windows", [True, False])
    def test_empty_command(self, is_windows: bool) -> None:
        with pytest.raises(ValueError, match="is empty"):
            _parse_command("   ", "JIRA_API_TOKEN_COMMAND", is_windows=is_windows)

    def test_posix_invalid_quoting(self) -> None:
        with pytest.raises(ValueError, match="invalid quoting"):
            _parse_command(
                "secret-tool 'unterminated",
                "JIRA_API_TOKEN_COMMAND",
                is_windows=False,
            )

    def test_windows_unbalanced_quotes(self) -> None:
        """Windows has no parsing step, so quoting errors surface at spawn."""
        command = "secret-tool 'unterminated"
        assert (
            _parse_command(command, "JIRA_API_TOKEN_COMMAND", is_windows=True)
            == command
        )


# ---------------------------------------------------------------------------
# deferred_pat_outranks
# ---------------------------------------------------------------------------


class TestDeferredPatOutranks:
    @pytest.mark.parametrize(
        ("env", "is_cloud", "auth_type", "expected"),
        [
            # Server/DC: a deferred PAT beats Basic and OAuth, as a static one would.
            ({"JIRA_PERSONAL_TOKEN_COMMAND": "get-pat"}, False, "basic", True),
            ({"JIRA_PERSONAL_TOKEN_COMMAND": "get-pat"}, False, "oauth", True),
            # Already using a PAT — nothing to gain.
            ({"JIRA_PERSONAL_TOKEN_COMMAND": "get-pat"}, False, "pat", False),
            # A static personal token wins over its command variant.
            (
                {
                    "JIRA_PERSONAL_TOKEN_COMMAND": "get-pat",
                    "JIRA_PERSONAL_TOKEN": "static-pat",
                },
                False,
                "basic",
                False,
            ),
            # Cloud ignores personal tokens entirely.
            ({"JIRA_PERSONAL_TOKEN_COMMAND": "get-pat"}, True, "oauth", False),
            # No command configured.
            ({}, False, "basic", False),
            # An API token command is Basic auth — never outranks.
            ({"JIRA_API_TOKEN_COMMAND": "get-token"}, False, "oauth", False),
        ],
    )
    def test_jira(
        self,
        env: dict[str, str],
        is_cloud: bool,
        auth_type: str,
        expected: bool,
    ) -> None:
        os.environ.update(env)
        assert (
            deferred_pat_outranks("jira", is_cloud=is_cloud, auth_type=auth_type)
            is expected
        )

    def test_confluence(self) -> None:
        os.environ["CONFLUENCE_PERSONAL_TOKEN_COMMAND"] = "get-pat"
        assert (
            deferred_pat_outranks("confluence", is_cloud=False, auth_type="basic")
            is True
        )
        assert deferred_pat_outranks("jira", is_cloud=False, auth_type="basic") is False

    def test_unknown_service(self) -> None:
        os.environ["JIRA_PERSONAL_TOKEN_COMMAND"] = "get-pat"
        assert (
            deferred_pat_outranks("unknown", is_cloud=False, auth_type="basic") is False
        )
