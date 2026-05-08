"""Field-level drop / mask rules with glob-style path matching.

Paths are dot-separated, with ``*`` matching a single path segment and
``**`` matching zero or more segments. List indices participate in the path
as numeric segments. Patterns are evaluated against every leaf and dict
node; rules apply to the matched value.

Examples
--------
* ``fields.reporter.emailAddress`` — exact path.
* ``fields.*.emailAddress`` — any one-segment-deep field carrying an
  ``emailAddress``.
* ``**.emailAddress`` — every ``emailAddress`` anywhere in the tree.
* ``issues.*.fields.assignee`` — assignee on every list item under
  ``issues``.
"""

from __future__ import annotations

import re
from typing import Any

from .stats import FilterStats


class _GlobMatcher:
    """Matches dot-separated paths against glob patterns segment-by-segment.

    Semantics:
      * a literal segment (``foo``) must match exactly,
      * ``*`` matches exactly one path segment,
      * ``**`` matches zero or more path segments,
      * a segment containing ``*`` (e.g. ``user_*``) is matched as a regex
        within that single segment.
    """

    def __init__(self, paths: list[str]) -> None:
        self._patterns: list[list[str]] = [p.split(".") for p in paths]
        # Pre-compile partial-wildcard segment regexes for speed.
        self._partial_segment_cache: dict[str, re.Pattern[str]] = {}

    def matches(self, path: str) -> bool:
        if not self._patterns:
            return False
        segments = path.split(".") if path else []
        return any(
            self._match(pattern=pat, segments=segments) for pat in self._patterns
        )

    def _match(self, pattern: list[str], segments: list[str]) -> bool:
        if not pattern:
            return not segments
        head = pattern[0]
        rest = pattern[1:]
        if head == "**":
            # Zero or more segments — try every possible split.
            for i in range(len(segments) + 1):
                if self._match(pattern=rest, segments=segments[i:]):
                    return True
            return False
        if not segments:
            return False
        if head == "*":
            return self._match(pattern=rest, segments=segments[1:])
        if "*" in head:
            if not self._segment_regex(head=head).match(segments[0]):
                return False
            return self._match(pattern=rest, segments=segments[1:])
        if head == segments[0]:
            return self._match(pattern=rest, segments=segments[1:])
        return False

    def _segment_regex(self, head: str) -> re.Pattern[str]:
        cached = self._partial_segment_cache.get(head)
        if cached is not None:
            return cached
        compiled = re.compile("^" + re.escape(head).replace(r"\*", ".*") + "$")
        self._partial_segment_cache[head] = compiled
        return compiled


class FieldFilter:
    """Drops or masks fields by glob path within a serialized response."""

    def __init__(
        self,
        drop_paths: list[str],
        mask_paths: list[str],
        mask_token: str,
    ) -> None:
        self._drop_matcher: _GlobMatcher = _GlobMatcher(paths=drop_paths)
        self._mask_matcher: _GlobMatcher = _GlobMatcher(paths=mask_paths)
        self._mask_token: str = mask_token
        self._has_rules: bool = bool(drop_paths or mask_paths)

    @property
    def has_rules(self) -> bool:
        return self._has_rules

    def apply(self, value: Any, *, stats: FilterStats | None = None) -> Any:
        if not self._has_rules:
            return value
        return self._walk(value=value, path="", stats=stats)

    def _walk(self, value: Any, path: str, stats: FilterStats | None) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                if self._drop_matcher.matches(path=child_path):
                    if stats is not None:
                        stats.fields_dropped += 1
                    continue
                if self._mask_matcher.matches(path=child_path):
                    result[key] = self._mask_token
                    if stats is not None:
                        stats.fields_masked += 1
                    continue
                result[key] = self._walk(value=child, path=child_path, stats=stats)
            return result
        if isinstance(value, list):
            walked: list[Any] = []
            for index, item in enumerate(value):
                child_path = f"{path}.{index}" if path else str(index)
                if self._drop_matcher.matches(path=child_path):
                    if stats is not None:
                        stats.fields_dropped += 1
                    continue
                if self._mask_matcher.matches(path=child_path):
                    walked.append(self._mask_token)
                    if stats is not None:
                        stats.fields_masked += 1
                    continue
                walked.append(self._walk(value=item, path=child_path, stats=stats))
            return walked
        return value


def build_field_filter(
    drop_fields: dict[str, list[str]],
    mask_fields: dict[str, list[str]],
    mask_token: str,
    resource_type: str | None,
) -> FieldFilter:
    """Build a ``FieldFilter`` for the given tool's resource type.

    Rules apply when (a) the resource type is known and present in the map,
    or (b) the special key ``"*"`` is present in the map (applies to all
    resource types).
    """
    drops: list[str] = []
    masks: list[str] = []
    if resource_type is not None and resource_type in drop_fields:
        drops.extend(drop_fields[resource_type])
    if "*" in drop_fields:
        drops.extend(drop_fields["*"])
    if resource_type is not None and resource_type in mask_fields:
        masks.extend(mask_fields[resource_type])
    if "*" in mask_fields:
        masks.extend(mask_fields["*"])
    return FieldFilter(drop_paths=drops, mask_paths=masks, mask_token=mask_token)
