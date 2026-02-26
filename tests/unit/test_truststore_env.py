"""Unit tests for truststore env var parsing logic.

Verifies that MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE is correctly parsed
from both os.environ and .env files, including edge cases like bare keys
(no value) in .env files.
"""

from unittest.mock import patch

import pytest


def _should_inject_truststore(env_value: str | None, dotenv_value: str | None) -> bool:
    """Replicate the truststore env var resolution logic from __init__.py.

    This mirrors the expression:
        (os.getenv("MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE",
                    dotenv_values().get(...) or "true")
         .lower() not in ("false", "0", "no"))

    Args:
        env_value: Value of OS env var, or None if unset.
        dotenv_value: Value from dotenv_values(), or None if key absent
                      or bare key (no =).

    Returns:
        True if truststore should be injected (enabled).
    """
    dotenv_fallback = dotenv_value or "true"
    # os.getenv returns env_value if set, else the default
    resolved = env_value if env_value is not None else dotenv_fallback
    return resolved.lower() not in ("false", "0", "no")


class TestTruststoreEnvParsing:
    """Test MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE parsing logic."""

    @pytest.mark.parametrize(
        "env_value, dotenv_value, expected",
        [
            # Default: no env var, no dotenv → enabled
            (None, None, True),
            # Explicitly enabled via env var
            ("true", None, True),
            ("TRUE", None, True),
            ("1", None, True),
            ("yes", None, True),
            # Disabled via env var
            ("false", None, False),
            ("FALSE", None, False),
            ("0", None, False),
            ("no", None, False),
            ("No", None, False),
            # Enabled via dotenv (env var unset)
            (None, "true", True),
            (None, "1", True),
            # Disabled via dotenv (env var unset)
            (None, "false", False),
            (None, "0", False),
            (None, "no", False),
            # Bare key in .env (no =) → dotenv returns None → default "true"
            (None, None, True),
            # Env var overrides dotenv
            ("false", "true", False),
            ("true", "false", True),
            # Empty string in dotenv → falsy, falls back to "true"
            (None, "", True),
        ],
        ids=[
            "default-no-config",
            "env-true",
            "env-TRUE",
            "env-1",
            "env-yes",
            "env-false",
            "env-FALSE",
            "env-0",
            "env-no",
            "env-No",
            "dotenv-true",
            "dotenv-1",
            "dotenv-false",
            "dotenv-0",
            "dotenv-no",
            "dotenv-bare-key-none",
            "env-overrides-dotenv-disable",
            "env-overrides-dotenv-enable",
            "dotenv-empty-string-fallback",
        ],
    )
    def test_resolution_logic(
        self,
        env_value: str | None,
        dotenv_value: str | None,
        expected: bool,
    ) -> None:
        """Verify env var resolution produces correct enable/disable result."""
        assert _should_inject_truststore(env_value, dotenv_value) is expected

    def test_none_dotenv_value_does_not_crash(self) -> None:
        """Verify that None from dotenv (bare key) doesn't cause AttributeError.

        This is the specific bug fixed: dotenv_values().get() returns None
        for bare keys (key without =), and the old code used .get(key, "true")
        which only applies the default when the key is absent, not when
        the value is None.
        """
        # This must not raise AttributeError
        result = _should_inject_truststore(env_value=None, dotenv_value=None)
        assert result is True

    def test_import_time_with_env_false(self) -> None:
        """Verify truststore is NOT injected when env var is 'false'.

        Mocks the import-time code path to confirm truststore.inject_into_ssl
        is not called when the env var disables it.
        """
        with (
            patch.dict(
                "os.environ",
                {"MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE": "false"},
            ),
            patch("mcp_atlassian.dotenv_values", return_value={}),
            patch("truststore.inject_into_ssl") as mock_inject,
        ):
            import importlib

            import mcp_atlassian

            importlib.reload(mcp_atlassian)
            mock_inject.assert_not_called()

    def test_import_time_with_env_0(self) -> None:
        """Verify truststore is NOT injected when env var is '0'."""
        with (
            patch.dict(
                "os.environ",
                {"MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE": "0"},
            ),
            patch("mcp_atlassian.dotenv_values", return_value={}),
            patch("truststore.inject_into_ssl") as mock_inject,
        ):
            import importlib

            import mcp_atlassian

            importlib.reload(mcp_atlassian)
            mock_inject.assert_not_called()

    def test_import_time_with_env_no(self) -> None:
        """Verify truststore is NOT injected when env var is 'no'."""
        with (
            patch.dict(
                "os.environ",
                {"MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE": "no"},
            ),
            patch("mcp_atlassian.dotenv_values", return_value={}),
            patch("truststore.inject_into_ssl") as mock_inject,
        ):
            import importlib

            import mcp_atlassian

            importlib.reload(mcp_atlassian)
            mock_inject.assert_not_called()

    def test_import_time_default_enables_truststore(self) -> None:
        """Verify truststore IS injected by default (no env var set)."""
        env_without_key = {
            k: v
            for k, v in __import__("os").environ.items()
            if k != "MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE"
        }
        with (
            patch.dict("os.environ", env_without_key, clear=True),
            patch("mcp_atlassian.dotenv_values", return_value={}),
            patch("truststore.inject_into_ssl") as mock_inject,
        ):
            import importlib

            import mcp_atlassian

            importlib.reload(mcp_atlassian)
            mock_inject.assert_called_once()

    def test_import_time_dotenv_none_does_not_crash(self) -> None:
        """Verify bare key in .env (None value) doesn't crash at import.

        Regression test for the AttributeError fix.
        """
        env_without_key = {
            k: v
            for k, v in __import__("os").environ.items()
            if k != "MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE"
        }
        # Simulate bare key: key exists but maps to None
        dotenv_with_none = {"MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE": None}
        with (
            patch.dict("os.environ", env_without_key, clear=True),
            patch(
                "mcp_atlassian.dotenv_values",
                return_value=dotenv_with_none,
            ),
            patch("truststore.inject_into_ssl") as mock_inject,
        ):
            import importlib

            import mcp_atlassian

            # Must not raise AttributeError
            importlib.reload(mcp_atlassian)
            # None falls back to "true" → truststore enabled
            mock_inject.assert_called_once()
