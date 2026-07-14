"""FastMCP helpers for preserving Atlassian tool error details."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from fastmcp import FastMCP

from mcp_atlassian.utils.decorators import handle_tool_errors

LifespanResultT = TypeVar("LifespanResultT")


class ErrorPreservingFastMCP(FastMCP[LifespanResultT], Generic[LifespanResultT]):
    """FastMCP variant that registers tools with detailed error handling."""

    def tool(self, name_or_fn: Any = None, **kwargs: Any) -> Any:
        if inspect.isroutine(name_or_fn):
            return super().tool(handle_tool_errors(name_or_fn), **kwargs)

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
            return super(ErrorPreservingFastMCP, self).tool(
                handle_tool_errors(fn), **kwargs
            )

        return decorator
