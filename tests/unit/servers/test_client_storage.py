"""Unit tests for custom OAuth proxy client storage factory resolution."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_atlassian.servers.client_storage import (
    CLIENT_STORAGE_CONFIG_JSON_ENV,
    CLIENT_STORAGE_FACTORY_ENV,
    CLIENT_STORAGE_MODE_ENV,
    build_oauth_client_storage_from_env,
)


class _DummyStorage:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.factory_config = config

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def put(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def delete(self, *args: Any, **kwargs: Any) -> bool:
        return True


def _dummy_storage_factory(config: dict[str, Any] | None = None) -> _DummyStorage:
    return _DummyStorage(config=config)


def _invalid_storage_factory(config: dict[str, Any] | None = None) -> object:
    _ = config
    return object()


def test_storage_builder_default_mode_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CLIENT_STORAGE_MODE_ENV, raising=False)
    monkeypatch.delenv(CLIENT_STORAGE_FACTORY_ENV, raising=False)
    monkeypatch.delenv(CLIENT_STORAGE_CONFIG_JSON_ENV, raising=False)

    assert build_oauth_client_storage_from_env() is None


def test_storage_builder_rejects_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "unsupported")

    with pytest.raises(ValueError, match=CLIENT_STORAGE_MODE_ENV):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_requires_import_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.delenv(CLIENT_STORAGE_FACTORY_ENV, raising=False)

    with pytest.raises(ValueError, match=CLIENT_STORAGE_FACTORY_ENV):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_rejects_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_dummy_storage_factory",
    )
    monkeypatch.setenv(CLIENT_STORAGE_CONFIG_JSON_ENV, "{invalid")

    with pytest.raises(ValueError, match=CLIENT_STORAGE_CONFIG_JSON_ENV):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_loads_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_dummy_storage_factory",
    )
    monkeypatch.setenv(CLIENT_STORAGE_CONFIG_JSON_ENV, '{"bucket":"mcp-client"}')

    storage = build_oauth_client_storage_from_env()

    assert storage is not None
    assert storage.__class__.__name__ == "_DummyStorage"
    assert callable(getattr(storage, "get", None))
    assert callable(getattr(storage, "put", None))
    assert callable(getattr(storage, "delete", None))
    assert storage.factory_config == {"bucket": "mcp-client"}


def test_storage_builder_factory_rejects_incompatible_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_invalid_storage_factory",
    )

    with pytest.raises(ValueError, match="incompatible object"):
        build_oauth_client_storage_from_env()
