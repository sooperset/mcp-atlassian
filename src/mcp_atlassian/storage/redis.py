"""Redis-backed OAuth client storage factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue


def factory(config: dict[str, Any] | None = None) -> AsyncKeyValue:
    """Create a Redis-backed OAuth client storage instance.

    Args:
        config: Keyword arguments accepted by ``RedisStore``. The most useful
            option is ``url``, for example ``redis://localhost:6379/0``.

    Returns:
        An async key-value store compatible with FastMCP OAuth proxy storage.
    """
    from key_value.aio.stores.redis import RedisStore

    return RedisStore(**(config or {}))
