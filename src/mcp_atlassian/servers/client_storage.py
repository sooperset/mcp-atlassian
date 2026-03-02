"""Helpers for optional OAuth proxy client storage backends.

By default, FastMCP provides encrypted client storage. This module adds an
opt-in factory mode for advanced deployments that need custom storage.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue
else:
    AsyncKeyValue = Any

logger = logging.getLogger("mcp-atlassian.server.client_storage")

CLIENT_STORAGE_MODE_ENV = "ATLASSIAN_OAUTH_CLIENT_STORAGE_MODE"
CLIENT_STORAGE_FACTORY_ENV = "ATLASSIAN_OAUTH_CLIENT_STORAGE_FACTORY"
CLIENT_STORAGE_CONFIG_JSON_ENV = "ATLASSIAN_OAUTH_CLIENT_STORAGE_CONFIG_JSON"
REQUIRED_STORAGE_METHODS = (
    "get",
    "put",
    "delete",
    "ttl",
    "get_many",
    "put_many",
    "delete_many",
    "ttl_many",
)


def _load_storage_factory(import_path: str) -> Callable[..., AsyncKeyValue]:
    module_path, separator, attribute_name = import_path.partition(":")
    if not separator or not module_path or not attribute_name:
        raise ValueError(
            f"Invalid {CLIENT_STORAGE_FACTORY_ENV}='{import_path}'. "
            "Expected '<module.path>:<callable>'."
        )

    try:
        module = import_module(module_path)
    except Exception as exc:
        raise ValueError(
            f"Unable to import module '{module_path}' from "
            f"{CLIENT_STORAGE_FACTORY_ENV}='{import_path}'."
        ) from exc

    factory = getattr(module, attribute_name, None)
    if not callable(factory):
        raise ValueError(
            f"{CLIENT_STORAGE_FACTORY_ENV}='{import_path}' does not resolve to a callable."
        )
    return cast(Callable[..., AsyncKeyValue], factory)


def _parse_factory_config(raw_json: str) -> dict[str, Any] | None:
    stripped = raw_json.strip()
    if not stripped:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{CLIENT_STORAGE_CONFIG_JSON_ENV} must be valid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            f"{CLIENT_STORAGE_CONFIG_JSON_ENV} must decode to a JSON object."
        )

    return parsed


def _validate_storage_candidate(storage: object) -> None:
    # Keep validation lightweight and interface-oriented.
    missing = [
        method
        for method in REQUIRED_STORAGE_METHODS
        if not callable(getattr(storage, method, None))
    ]
    if missing:
        raise ValueError(
            "OAuth client storage factory returned an incompatible object. "
            f"Missing methods: {', '.join(missing)}"
        )


def _invoke_storage_factory(
    factory: Callable[..., AsyncKeyValue], config: dict[str, Any] | None
) -> AsyncKeyValue:
    if config is None:
        return factory()

    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        # Some callables may not expose an introspectable signature.
        return factory(config)

    params = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
        return factory(config=config)

    config_param = params.get("config")
    if config_param and config_param.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    ):
        return factory(config=config)

    if any(
        param.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        for param in params.values()
    ):
        return factory(config)

    factory_module = getattr(factory, "__module__", "<unknown-module>")
    factory_name = getattr(factory, "__name__", factory.__class__.__name__)
    raise ValueError(
        f"{CLIENT_STORAGE_FACTORY_ENV}='{factory_module}:{factory_name}' "
        "does not accept a configuration argument."
    )


def build_oauth_client_storage_from_env() -> AsyncKeyValue | None:
    """Build OAuth client storage backend from env vars.

    Modes:
    - ``default`` (or unset): let FastMCP use its default encrypted storage.
    - ``factory``: load a custom factory callable and use its returned storage.
    """

    mode = os.getenv(CLIENT_STORAGE_MODE_ENV, "default").strip().lower()
    if mode in {"", "default"}:
        return None

    if mode != "factory":
        raise ValueError(
            f"Unsupported {CLIENT_STORAGE_MODE_ENV}='{mode}'. "
            "Supported modes: default, factory."
        )

    import_path = os.getenv(CLIENT_STORAGE_FACTORY_ENV, "").strip()
    if not import_path:
        raise ValueError(
            f"{CLIENT_STORAGE_FACTORY_ENV} is required when "
            f"{CLIENT_STORAGE_MODE_ENV}=factory."
        )

    config = _parse_factory_config(os.getenv(CLIENT_STORAGE_CONFIG_JSON_ENV, ""))
    factory = _load_storage_factory(import_path)

    try:
        storage = _invoke_storage_factory(factory, config)
    except Exception as exc:
        raise ValueError(
            "Failed to create OAuth client storage from "
            f"{CLIENT_STORAGE_FACTORY_ENV}='{import_path}': {exc}"
        ) from exc

    _validate_storage_candidate(storage)
    logger.info(
        "Using custom OAuth client storage factory from %s.",
        CLIENT_STORAGE_FACTORY_ENV,
    )
    return storage
