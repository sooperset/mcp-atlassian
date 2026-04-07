"""Deferred credential resolution via shell commands.

Supports ``*_COMMAND`` environment variable variants (e.g.
``JIRA_API_TOKEN_COMMAND``) that run a shell command lazily on first tool
use and populate the corresponding plain environment variable with the
command's stdout.  This allows users who store secrets in tools like
``gopass`` or ``1password-cli`` to avoid unlocking their secret storage
until they actually need it.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger("mcp-atlassian.utils.credential_command")

# Maps *_COMMAND env var → target env var it resolves to.
COMMAND_ENV_MAP: dict[str, str] = {
    "JIRA_API_TOKEN_COMMAND": "JIRA_API_TOKEN",
    "JIRA_PERSONAL_TOKEN_COMMAND": "JIRA_PERSONAL_TOKEN",
    "CONFLUENCE_API_TOKEN_COMMAND": "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_PERSONAL_TOKEN_COMMAND": "CONFLUENCE_PERSONAL_TOKEN",
}

# Which *_COMMAND vars belong to which service.
_SERVICE_COMMANDS: dict[str, list[str]] = {
    "jira": [
        "JIRA_API_TOKEN_COMMAND",
        "JIRA_PERSONAL_TOKEN_COMMAND",
    ],
    "confluence": [
        "CONFLUENCE_API_TOKEN_COMMAND",
        "CONFLUENCE_PERSONAL_TOKEN_COMMAND",
    ],
}

_DEFAULT_TIMEOUT = 30


class CredentialCommandResolver:
    """Resolves ``*_COMMAND`` env vars by running the command and caching the result."""

    def __init__(self) -> None:
        self._resolved_services: set[str] = set()
        self._fetcher_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public helpers (no side-effects — safe to call at startup)
    # ------------------------------------------------------------------

    def has_deferred_credentials(self, service: str) -> bool:
        """Return ``True`` if any ``*_COMMAND`` vars are configured for *service*
        and the corresponding plain env var is **not** already set.
        """
        for cmd_var in _SERVICE_COMMANDS.get(service, []):
            target_var = COMMAND_ENV_MAP[cmd_var]
            if os.getenv(cmd_var) and not os.getenv(target_var):
                return True
        return False

    # ------------------------------------------------------------------
    # Resolution (runs commands — call only when credentials are needed)
    # ------------------------------------------------------------------

    def resolve(self, service: str) -> None:
        """Run all pending ``*_COMMAND`` env vars for *service*.

        Sets the corresponding plain env var with the trimmed stdout of
        each command.  Idempotent per service — subsequent calls are
        no-ops.

        Raises:
            ValueError: If any command fails, times out, or returns
                empty output.
        """
        if service in self._resolved_services:
            return
        self._resolved_services.add(service)

        timeout = int(os.getenv("CREDENTIAL_COMMAND_TIMEOUT", str(_DEFAULT_TIMEOUT)))

        for cmd_var in _SERVICE_COMMANDS.get(service, []):
            target_var = COMMAND_ENV_MAP[cmd_var]
            command = os.getenv(cmd_var)
            if not command or os.getenv(target_var):
                continue

            logger.debug("Resolving %s via %s", target_var, cmd_var)
            try:
                result = subprocess.run(  # noqa: S602
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    f"Credential command for {target_var} (from {cmd_var}) "
                    f"timed out after {timeout}s"
                ) from exc
            except FileNotFoundError as exc:
                raise ValueError(
                    f"Credential command not found for {cmd_var}: {command}"
                ) from exc

            if result.returncode != 0:
                raise ValueError(
                    f"Credential command for {target_var} (from {cmd_var}) "
                    f"failed (exit code {result.returncode}): {result.stderr.strip()}"
                )

            token = result.stdout.strip()
            if not token:
                raise ValueError(
                    f"Credential command for {target_var} (from {cmd_var}) "
                    "returned empty output"
                )

            os.environ[target_var] = token
            logger.info("Resolved %s from %s", target_var, cmd_var)

    # ------------------------------------------------------------------
    # Fetcher cache
    # ------------------------------------------------------------------

    def get_cached_fetcher(self, service: str) -> Any | None:
        """Return the cached fetcher for *service*, or ``None``."""
        return self._fetcher_cache.get(service)

    def cache_fetcher(self, service: str, fetcher: Any) -> None:
        """Cache *fetcher* for *service*."""
        self._fetcher_cache[service] = fetcher


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_resolver: CredentialCommandResolver | None = None


def get_resolver() -> CredentialCommandResolver:
    """Return the module-level ``CredentialCommandResolver`` singleton."""
    global _resolver  # noqa: PLW0603
    if _resolver is None:
        _resolver = CredentialCommandResolver()
    return _resolver
