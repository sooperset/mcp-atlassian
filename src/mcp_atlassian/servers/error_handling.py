"""FastMCP helpers for preserving Atlassian tool error details."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from fastmcp import FastMCP
from fastmcp.decorators import get_fastmcp_meta
from fastmcp.tools.function_tool import ToolMeta

from mcp_atlassian.utils.decorators import (
    _DEPRECATED_TOOL_MARKER,
    _DEPRECATED_TOOL_REGISTRATION_HOOK,
    handle_tool_errors,
)
from mcp_atlassian.utils.toolsets import TOOLSET_TAG_PREFIX

LifespanResultT = TypeVar("LifespanResultT")


class ErrorPreservingFastMCP(FastMCP[LifespanResultT], Generic[LifespanResultT]):
    """FastMCP variant that registers tools with detailed error handling."""

    @staticmethod
    def _merge_deprecated_metadata(
        fn: Callable[..., Any], kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Keep deprecated metadata when FastMCP receives explicit tool options."""
        if not getattr(fn, _DEPRECATED_TOOL_MARKER, False):
            return kwargs

        metadata = get_fastmcp_meta(fn)
        if not isinstance(metadata, ToolMeta):
            return kwargs

        merged = dict(kwargs)
        metadata_tags = set(metadata.tags or set())
        explicit_tags = set(merged.get("tags") or set())
        if metadata_tags or explicit_tags:
            toolset_tags = {
                tag for tag in metadata_tags if tag.startswith(TOOLSET_TAG_PREFIX)
            }
            merged["tags"] = {
                tag
                for tag in explicit_tags | metadata_tags
                if not tag.startswith(TOOLSET_TAG_PREFIX)
            } | toolset_tags

        if metadata.description is not None:
            merged["description"] = metadata.description

        return merged

    def _add_deprecated_registration_hook(
        self,
        registered_fn: Any,
        fn: Callable[..., Any],
        kwargs: dict[str, Any],
    ) -> None:
        """Allow a later outer deprecated decorator to update the registered tool."""
        if not inspect.isroutine(registered_fn):
            return

        tool_name = kwargs.get("name") or getattr(fn, "__name__", None)
        version = kwargs.get("version")
        explicit_tags = set(kwargs.get("tags") or set())
        registered_tool = next(
            (
                component
                for component in self._local_provider._components.values()
                if getattr(component, "name", None) == tool_name
                and (
                    version is None
                    or str(getattr(component, "version", None)) == str(version)
                )
            ),
            None,
        )
        if registered_tool is None:
            return

        def update_registered_tool(
            deprecated_fn: Callable[..., Any], metadata: ToolMeta
        ) -> None:
            """Replace the registered callable and expose its deprecation metadata."""
            registered_tool.fn = handle_tool_errors(deprecated_fn)
            registered_tool.description = metadata.description
            metadata_tags = set(metadata.tags or set())
            toolset_tags = {
                tag for tag in metadata_tags if tag.startswith(TOOLSET_TAG_PREFIX)
            }
            registered_tool.tags = {
                tag
                for tag in explicit_tags | metadata_tags
                if not tag.startswith(TOOLSET_TAG_PREFIX)
            } | toolset_tags

        setattr(
            registered_fn,
            _DEPRECATED_TOOL_REGISTRATION_HOOK,
            update_registered_tool,
        )

    def _register_tool(self, fn: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
        """Register a function with error handling and deprecation integration."""
        registration_kwargs = self._merge_deprecated_metadata(fn, kwargs)
        registered_fn = super().tool(handle_tool_errors(fn), **registration_kwargs)
        if not getattr(fn, _DEPRECATED_TOOL_MARKER, False):
            self._add_deprecated_registration_hook(registered_fn, fn, kwargs)
        return registered_fn

    def tool(self, name_or_fn: Any = None, **kwargs: Any) -> Any:
        if inspect.isroutine(name_or_fn):
            return self._register_tool(name_or_fn, kwargs)

        if isinstance(name_or_fn, str):
            if kwargs.get("name") is not None:
                raise TypeError(
                    "Cannot specify both a name as first argument and as keyword "
                    "argument."
                )
            kwargs = {**kwargs, "name": name_or_fn}
        elif name_or_fn is not None:
            return super().tool(name_or_fn, **kwargs)

        def decorator(fn: Callable[..., Any]) -> Any:
            return self._register_tool(fn, kwargs)

        return decorator
