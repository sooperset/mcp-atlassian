"""Deferred credential resolution via external commands."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import threading

from mcp_atlassian.utils.urls import is_atlassian_cloud_url

logger = logging.getLogger("mcp-atlassian.utils.credential_command")

COMMAND_ENV_MAP: dict[str, str] = {
    "JIRA_API_TOKEN_COMMAND": "JIRA_API_TOKEN",
    "JIRA_PERSONAL_TOKEN_COMMAND": "JIRA_PERSONAL_TOKEN",
    "CONFLUENCE_API_TOKEN_COMMAND": "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_PERSONAL_TOKEN_COMMAND": "CONFLUENCE_PERSONAL_TOKEN",
}

_SERVICE_COMMANDS: dict[str, tuple[str, ...]] = {
    "jira": (
        "JIRA_API_TOKEN_COMMAND",
        "JIRA_PERSONAL_TOKEN_COMMAND",
    ),
    "confluence": (
        "CONFLUENCE_API_TOKEN_COMMAND",
        "CONFLUENCE_PERSONAL_TOKEN_COMMAND",
    ),
}

_DEFAULT_TIMEOUT = 30


def _parse_command(
    command: str, command_var: str, *, is_windows: bool | None = None
) -> str | list[str]:
    """Parse a credential command into a form ``subprocess.run`` accepts.

    On Windows the raw string is returned so that ``CreateProcess`` applies the
    platform's native argument rules; ``shlex`` does not implement them and
    would leave quote characters inside the arguments. On POSIX the command is
    split with ``shlex``. Neither form uses a shell.

    Args:
        command: Configured command line.
        command_var: Name of the environment variable holding *command*, used
            in error messages.
        is_windows: Whether to use Windows argument rules. Defaults to the
            current platform; injected by tests.

    Returns:
        The raw command string on Windows, otherwise the split arguments.

    Raises:
        ValueError: If the command is empty or, on POSIX, quoted incorrectly.
    """
    empty_message = f"Credential command in {command_var} is empty"
    if not command.strip():
        raise ValueError(empty_message)
    if is_windows is None:
        is_windows = os.name == "nt"
    if is_windows:
        return command

    try:
        arguments = shlex.split(command)
    except ValueError as exc:
        message = f"Credential command in {command_var} has invalid quoting"
        raise ValueError(message) from exc
    if not arguments:
        raise ValueError(empty_message)
    return arguments


def deferred_pat_outranks(
    service: str, *, is_cloud: bool, auth_type: str | None
) -> bool:
    """Check whether a deferred personal token beats an already-loaded config.

    ``JiraConfig.from_env`` and ``ConfluenceConfig.from_env`` prefer a personal
    access token over OAuth and Basic auth on Server/Data Center. A deferred
    personal token is invisible to them at startup, so a lower-priority auth
    type can load instead. This reports that case so the deferred command wins.

    Args:
        service: Service name (``"jira"`` or ``"confluence"``).
        is_cloud: Whether the loaded configuration targets Atlassian Cloud.
        auth_type: Auth type of the loaded configuration.

    Returns:
        ``True`` when a pending personal token command should take precedence.
    """
    if service not in _SERVICE_COMMANDS or is_cloud or auth_type == "pat":
        return False

    prefix = service.upper()
    return bool(os.getenv(f"{prefix}_PERSONAL_TOKEN_COMMAND")) and not os.getenv(
        f"{prefix}_PERSONAL_TOKEN"
    )


class CredentialCommandResolver:
    """Resolve credentials produced by configured commands exactly once."""

    def __init__(self, *, is_windows: bool | None = None) -> None:
        """Initialize a resolver.

        Args:
            is_windows: Optional platform override for deterministic tests. When
                omitted, command parsing follows the current operating system.
        """
        self._resolved_services: set[str] = set()
        self._is_windows = is_windows
        self._service_locks = {
            service: threading.Lock() for service in _SERVICE_COMMANDS
        }

    def has_deferred_credentials(self, service: str) -> bool:
        """Check whether a service has a viable deferred credential.

        This method never executes a command. Cloud API-token commands require
        the matching username, while Server/Data Center can also use a deferred
        personal token.

        Args:
            service: Service name (``"jira"`` or ``"confluence"``).

        Returns:
            ``True`` when the remaining static configuration is sufficient.
        """
        if service not in _SERVICE_COMMANDS:
            return False

        prefix = service.upper()
        url = os.getenv(f"{prefix}_URL")
        if not url:
            return False

        username = os.getenv(f"{prefix}_USERNAME")
        api_token_is_deferred = bool(
            os.getenv(f"{prefix}_API_TOKEN_COMMAND")
        ) and not bool(os.getenv(f"{prefix}_API_TOKEN"))
        personal_token_is_deferred = bool(
            os.getenv(f"{prefix}_PERSONAL_TOKEN_COMMAND")
        ) and not bool(os.getenv(f"{prefix}_PERSONAL_TOKEN"))

        if is_atlassian_cloud_url(url):
            return bool(username and api_token_is_deferred)
        return personal_token_is_deferred or bool(username and api_token_is_deferred)

    def resolve(self, service: str) -> None:
        """Run all pending credential commands for a service.

        Commands run without an implicit shell and with standard input closed,
        so they cannot consume the MCP stdio transport. Results become visible
        only after every pending command succeeds, and a failed attempt can be
        retried.

        Args:
            service: Service name (``"jira"`` or ``"confluence"``).

        Raises:
            ValueError: If the service or command configuration is invalid, or
                if a command fails, times out, or returns empty output.
        """
        if service not in _SERVICE_COMMANDS:
            message = f"Unsupported credential service: {service}"
            raise ValueError(message)

        with self._service_locks[service]:
            if service in self._resolved_services:
                return

            timeout = self._get_timeout()
            resolved_credentials: dict[str, str] = {}

            for command_var in _SERVICE_COMMANDS[service]:
                target_var = COMMAND_ENV_MAP[command_var]
                command = os.getenv(command_var)
                if not command or os.getenv(target_var):
                    continue

                arguments = _parse_command(
                    command, command_var, is_windows=self._is_windows
                )

                logger.debug("Resolving %s via %s", target_var, command_var)
                try:
                    result = subprocess.run(  # noqa: S603
                        arguments,
                        shell=False,
                        # Never let a helper read the MCP stdio transport.
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired as exc:
                    message = (
                        f"Credential command for {target_var} (from {command_var}) "
                        f"timed out after {timeout}s"
                    )
                    raise ValueError(message) from exc
                except OSError as exc:
                    message = (
                        f"Credential command configured by {command_var} "
                        "could not be started"
                    )
                    raise ValueError(message) from exc

                if result.returncode != 0:
                    message = (
                        f"Credential command for {target_var} (from {command_var}) "
                        f"failed with exit code {result.returncode}"
                    )
                    raise ValueError(message)

                credential = result.stdout.strip()
                if not credential:
                    message = (
                        f"Credential command for {target_var} (from {command_var}) "
                        "returned empty output"
                    )
                    raise ValueError(message)
                resolved_credentials[target_var] = credential

            os.environ.update(resolved_credentials)
            self._resolved_services.add(service)
            for target_var in resolved_credentials:
                logger.info("Resolved %s from its configured command", target_var)

    @staticmethod
    def _get_timeout() -> int:
        raw_timeout = os.getenv(
            "CREDENTIAL_COMMAND_TIMEOUT",
            str(_DEFAULT_TIMEOUT),
        )
        try:
            timeout = int(raw_timeout)
        except ValueError as exc:
            raise ValueError(
                "CREDENTIAL_COMMAND_TIMEOUT must be a positive integer"
            ) from exc
        if timeout <= 0:
            raise ValueError("CREDENTIAL_COMMAND_TIMEOUT must be a positive integer")
        return timeout


_resolver = CredentialCommandResolver()


def get_resolver() -> CredentialCommandResolver:
    """Return the process-wide credential command resolver.

    Returns:
        The shared resolver instance.
    """
    return _resolver
