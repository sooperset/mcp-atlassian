"""Unit tests for custom OAuth proxy client storage factory resolution."""

from __future__ import annotations

import os
from typing import Any

import pytest

from mcp_atlassian.servers import client_storage as client_storage_module
from mcp_atlassian.servers.client_storage import (
    CLIENT_STORAGE_ALLOW_ARBITRARY_ENV,
    CLIENT_STORAGE_CONFIG_JSON_ENV,
    CLIENT_STORAGE_FACTORY_ENV,
    CLIENT_STORAGE_MODE_ENV,
    _is_trusted_factory_module,
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
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_dummy_storage_factory",
    )
    monkeypatch.setenv(CLIENT_STORAGE_CONFIG_JSON_ENV, "{invalid")

    with pytest.raises(ValueError, match=CLIENT_STORAGE_CONFIG_JSON_ENV):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_loads_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
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
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
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
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
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
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_type_error_in_factory",
    )
    monkeypatch.setenv(CLIENT_STORAGE_CONFIG_JSON_ENV, '{"bucket":"mcp-client"}')
    monkeypatch.setenv(_TYPE_ERROR_FACTORY_CALLS_ENV, "0")

    with pytest.raises(ValueError, match="Failed to create OAuth client storage"):
        build_oauth_client_storage_from_env()

    assert os.getenv(_TYPE_ERROR_FACTORY_CALLS_ENV) == "1"


def test_is_trusted_factory_module_allows_reserved_namespaces() -> None:
    assert _is_trusted_factory_module("key_value")
    assert _is_trusted_factory_module("key_value.aio.stores.redis")
    assert _is_trusted_factory_module("mcp_atlassian.storage")
    assert _is_trusted_factory_module("mcp_atlassian.storage.redis_adapter")


def test_is_trusted_factory_module_rejects_prefix_lookalikes() -> None:
    # A module whose name merely starts with the trusted package name (no
    # separating dot) must not be treated as inside that namespace.
    assert not _is_trusted_factory_module("key_value_evil")
    assert not _is_trusted_factory_module("mcp_atlassian.storage_evil")
    assert not _is_trusted_factory_module("os")
    assert not _is_trusted_factory_module("tests.unit.servers.test_client_storage")


def test_is_trusted_factory_module_rejects_rest_of_the_package() -> None:
    # Trust is scoped to mcp_atlassian.storage.*, not the whole package: most
    # of it has nothing to do with storage and has not been audited for safe
    # use as an arbitrary callable (e.g. servers.client_storage itself
    # re-exports importlib.import_module as a plain, callable attribute).
    assert not _is_trusted_factory_module("mcp_atlassian")
    assert not _is_trusted_factory_module("mcp_atlassian.servers.client_storage")
    assert not _is_trusted_factory_module("mcp_atlassian.utils.credential_command")


def test_storage_builder_factory_rejects_untrusted_module_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.delenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, raising=False)
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_dummy_storage_factory",
    )

    with pytest.raises(ValueError, match=CLIENT_STORAGE_ALLOW_ARBITRARY_ENV):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_rejects_dangerous_module_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An untrusted factory path must be refused before anything is imported."""
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.delenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, raising=False)
    monkeypatch.setenv(CLIENT_STORAGE_FACTORY_ENV, "os:system")

    def _must_not_import(name: str, *args: Any, **kwargs: Any) -> Any:
        message = f"import_module must not be called for {name!r}"
        raise AssertionError(message)

    monkeypatch.setattr(client_storage_module, "import_module", _must_not_import)

    with pytest.raises(ValueError, match=CLIENT_STORAGE_ALLOW_ARBITRARY_ENV):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_allows_untrusted_module_with_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_dummy_storage_factory",
    )

    storage = build_oauth_client_storage_from_env()

    assert storage is not None
    assert storage.__class__.__name__ == "_DummyStorage"


class _KeywordOnlyStorage(_DummyStorage):
    """Mimics a key_value.aio.stores class: settings as keyword-only args,
    not one config dict — the shape _invoke_storage_factory must also support.
    """

    def __init__(
        self, *, host: str = "localhost", port: int = 6379, password: str | None = None
    ) -> None:
        super().__init__(config={"host": host, "port": port, "password": password})


def test_storage_builder_factory_spreads_config_for_keyword_only_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_KeywordOnlyStorage",
    )
    monkeypatch.setenv(
        CLIENT_STORAGE_CONFIG_JSON_ENV, '{"host": "redis.internal", "port": 6380}'
    )

    storage = build_oauth_client_storage_from_env()

    assert storage is not None
    assert storage.factory_config == {
        "host": "redis.internal",
        "port": 6380,
        "password": None,
    }


def test_storage_builder_factory_keyword_only_constructor_rejects_unknown_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.setenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, "true")
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV,
        "tests.unit.servers.test_client_storage:_KeywordOnlyStorage",
    )
    monkeypatch.setenv(CLIENT_STORAGE_CONFIG_JSON_ENV, '{"not_a_real_param": true}')

    with pytest.raises(ValueError, match="does not accept a configuration argument"):
        build_oauth_client_storage_from_env()


def test_storage_builder_factory_loads_real_redis_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end regression test for the documented key_value.* example.

    RedisStore's constructor is keyword-only with no single config
    parameter, so this exercises both the trusted-namespace check and the
    keyword-spreading fallback together, against the real dependency (no
    network I/O happens at construction time).
    """
    monkeypatch.setenv(CLIENT_STORAGE_MODE_ENV, "factory")
    monkeypatch.delenv(CLIENT_STORAGE_ALLOW_ARBITRARY_ENV, raising=False)
    monkeypatch.setenv(
        CLIENT_STORAGE_FACTORY_ENV, "key_value.aio.stores.redis:RedisStore"
    )
    monkeypatch.setenv(
        CLIENT_STORAGE_CONFIG_JSON_ENV, '{"host": "localhost", "port": 6379}'
    )

    storage = build_oauth_client_storage_from_env()

    assert storage is not None
    assert storage.__class__.__name__ == "RedisStore"
