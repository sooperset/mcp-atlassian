"""Tests for privacy.install_privacy_filter and the public API surface."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_atlassian.privacy import (
    PrivacyConfig,
    PrivacyFilterMiddleware,
    install_privacy_filter,
)


class _FakeServer:
    def __init__(self) -> None:
        self.middlewares: list[Any] = []

    def add_middleware(self, middleware: Any) -> None:
        self.middlewares.append(middleware)


class TestInstallPrivacyFilter:
    def test_disabled_config_does_not_install(self) -> None:
        server = _FakeServer()
        installed = install_privacy_filter(
            server=server,  # type: ignore[arg-type]
            config=PrivacyConfig(enabled=False),
        )
        assert installed is False
        assert server.middlewares == []

    def test_enabled_but_no_rules_does_not_install(self) -> None:
        server = _FakeServer()
        installed = install_privacy_filter(
            server=server,  # type: ignore[arg-type]
            config=PrivacyConfig(enabled=True),
        )
        assert installed is False
        assert server.middlewares == []

    def test_enabled_with_rules_installs_middleware(self) -> None:
        server = _FakeServer()
        installed = install_privacy_filter(
            server=server,  # type: ignore[arg-type]
            config=PrivacyConfig(enabled=True, pii_pattern_names=["email"]),
        )
        assert installed is True
        assert len(server.middlewares) == 1
        assert isinstance(server.middlewares[0], PrivacyFilterMiddleware)

    def test_default_config_loads_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PRIVACY_FILTER_ENABLED", raising=False)
        server = _FakeServer()
        assert (
            install_privacy_filter(server=server)  # type: ignore[arg-type]
            is False
        )
