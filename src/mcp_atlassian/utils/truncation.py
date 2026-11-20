"""Mark collection reads that stopped at a read limit.

Bounded readers return a :class:`TruncatedList` when they stopped before the
end of the upstream collection. It is a plain ``list`` for every other use, so
callers that do not look for the mark keep working; tool handlers check
:func:`is_truncated` and tell the caller.

``certain`` separates the two ways a read stops early: the reader saw more
items than it returned (``True``), or it stopped before it could tell whether
more exist, for example at a request limit or a repeated cursor (``False``).
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


class TruncatedList(list[T]):
    """A list read up to a limit; the upstream collection holds or may hold more."""

    truncated = True

    def __init__(self, items: list[T], *, certain: bool) -> None:
        super().__init__(items)
        self.certain = certain


def mark_truncated(items: list[T], *, certain: bool) -> list[T]:
    """Return ``items`` marked as cut short by a read limit."""
    return TruncatedList(items, certain=certain)


def is_truncated(value: Any) -> bool:
    """Return True when ``value`` came from a read that stopped early."""
    return getattr(value, "truncated", False) is True


def more_certainly_exist(value: Any) -> bool:
    """Return True when a stopped read is known to have left items behind."""
    return is_truncated(value) and getattr(value, "certain", False) is True


def merge_truncation(items: list[T], *parts: Any) -> list[T]:
    """Mark ``items`` as truncated if any of ``parts`` was, keeping certainty."""
    if not any(is_truncated(part) for part in parts):
        return items
    return mark_truncated(
        items, certain=any(more_certainly_exist(part) for part in parts)
    )
