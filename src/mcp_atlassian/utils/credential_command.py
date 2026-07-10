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


class CredentialCommandResolver:
    """Resolve credentials produced by configured commands exactly once."""

    def __init__(self) -> None:
        self._resolved_services: set[str] = set()
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

        Commands are parsed into arguments and run without an implicit shell.
        Results become visible only after every pending command succeeds, and a
        failed attempt can be retried.

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

                try:
                    arguments = shlex.split(command, posix=os.name != "nt")
                except ValueError as exc:
                    message = f"Credential command in {command_var} has invalid quoting"
                    raise ValueError(message) from exc
                if not arguments:
                    message = f"Credential command in {command_var} is empty"
                    raise ValueError(message)

                logger.debug("Resolving %s via %s", target_var, command_var)
                try:
                    result = subprocess.run(  # noqa: S603
                        arguments,
                        shell=False,
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
