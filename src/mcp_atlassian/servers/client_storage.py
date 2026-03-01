"""Helpers for optional OAuth proxy client storage backends.

By default, FastMCP provides encrypted client storage. This module adds an
opt-in factory mode for advanced deployments that need custom storage.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from importlib import import_module
from typing import Any, cast

logger = logging.getLogger("mcp-atlassian.server.client_storage")

CLIENT_STORAGE_MODE_ENV = "ATLASSIAN_OAUTH_CLIENT_STORAGE_MODE"
CLIENT_STORAGE_FACTORY_ENV = "ATLASSIAN_OAUTH_CLIENT_STORAGE_FACTORY"
CLIENT_STORAGE_CONFIG_JSON_ENV = "ATLASSIAN_OAUTH_CLIENT_STORAGE_CONFIG_JSON"


def _load_storage_factory(import_path: str) -> Callable[..., Any]:
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
    return cast(Callable[..., Any], factory)


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


def _validate_storage_candidate(storage: Any) -> None:
    # Keep validation lightweight and interface-oriented.
    required_methods = ("get", "put", "delete")
    missing = [
        method
        for method in required_methods
        if not callable(getattr(storage, method, None))
    ]
    if missing:
        raise ValueError(
            "OAuth client storage factory returned an incompatible object. "
            f"Missing methods: {', '.join(missing)}"
        )


def build_oauth_client_storage_from_env() -> Any | None:
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
        if config is None:
            storage = factory()
        else:
            try:
                storage = factory(config=config)
            except TypeError:
                storage = factory(config)
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
