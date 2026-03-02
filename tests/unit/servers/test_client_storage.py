"""Unit tests for custom OAuth proxy client storage factory resolution."""

from __future__ import annotations

import os
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

    async def ttl(self, *args: Any, **kwargs: Any) -> int | None:
        return None

    async def get_many(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def put_many(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def delete_many(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def ttl_many(self, *args: Any, **kwargs: Any) -> dict[str, int | None]:
        return {}


class _PartialStorage:
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


def _partial_storage_factory(config: dict[str, Any] | None = None) -> _PartialStorage:
    _ = config
    return _PartialStorage()


_TYPE_ERROR_FACTORY_CALLS_ENV = "MCP_ATLASSIAN_TEST_TYPE_ERROR_FACTORY_CALLS"


def _type_error_in_factory(config: dict[str, Any] | None = None) -> _DummyStorage:
    call_count = int(os.getenv(_TYPE_ERROR_FACTORY_CALLS_ENV, "0"))
    os.environ[_TYPE_ERROR_FACTORY_CALLS_ENV] = str(call_count + 1)
    # Raise a real internal TypeError to ensure we do not mask it via a fallback call.
    assert config is not None
    _ = config["bucket"] + 1
    return _DummyStorage(config=config)


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
    assert callable(getattr(storage, "ttl", None))
    assert callable(getattr(storage, "get_many", None))
    assert callable(getattr(storage, "put_many", None))
    assert callable(getattr(storage, "delete_many", None))
    assert callable(getattr(storage, "ttl_many", None))
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


def test_storage_builder_factory_rejects_partially_implemented_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_partial_storage_factory",
    )

    with pytest.raises(ValueError, match="ttl"):
        build_oauth_client_storage_from_env()


def test_storage_builder_does_not_mask_internal_factory_typeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_type_error_in_factory",
    )
    monkeypatch.setenv(CLIENT_STORAGE_CONFIG_JSON_ENV, '{"bucket":"mcp-client"}')
    monkeypatch.setenv(_TYPE_ERROR_FACTORY_CALLS_ENV, "0")

    with pytest.raises(ValueError, match="Failed to create OAuth client storage"):
        build_oauth_client_storage_from_env()

    assert os.getenv(_TYPE_ERROR_FACTORY_CALLS_ENV) == "1"
