"""Drop resources whose metadata matches the configured denylists.

The filter applies in two places:

* **Top-level**: when a tool returns a single resource (e.g.
  ``jira_get_issue`` returning one issue) and that resource matches a
  denylist, the entire payload is replaced with ``{}``.
* **List items**: when a tool returns a list of resources (e.g.
  ``jira_search`` issues, ``confluence_search`` results), each item is
  inspected and dropped if it matches.

A "match" is any of:

* Jira-style: ``project.key`` or top-level ``key`` prefix matches a denied
  project key (``DENY_PROJECT_KEYS``).
* Confluence-style: ``space.key`` matches a denied space key
  (``DENY_SPACE_KEYS``).
* Either: any item in ``labels`` (list of strings or list of dicts with
  ``name``) matches a denied label (``DENY_LABELS``).

The check is structural and metadata-based; it does not import upstream
model classes, so it survives upstream renames.

**Caveat — wrapper shapes.** Some tools (e.g. ``confluence_get_page``)
wrap the resource under a key like ``metadata`` instead of putting it at
the top level. The top-level check inspects the response root, so a
wrapped resource is not auto-dropped. Use ``PRIVACY_DROP_FIELDS`` /
``PRIVACY_MASK_FIELDS`` with paths like ``metadata.space.key`` for those.
"""

from __future__ import annotations

from typing import Any

from .stats import FilterStats


class ResourceFilter:
    """Drops resources by labels / space-keys / project-keys."""

    def __init__(
        self,
        deny_labels: list[str],
        deny_space_keys: list[str],
        deny_project_keys: list[str],
    ) -> None:
        self._deny_labels: set[str] = set(deny_labels)
        self._deny_space_keys: set[str] = set(deny_space_keys)
        self._deny_project_keys: set[str] = set(deny_project_keys)
        self._has_rules: bool = bool(
            deny_labels or deny_space_keys or deny_project_keys
        )

    @property
    def has_rules(self) -> bool:
        return self._has_rules

    def apply(self, value: Any, *, stats: FilterStats | None = None) -> Any:
        if not self._has_rules:
            return value
        # Top-level single-resource match → wipe the whole payload.
        if isinstance(value, dict) and self._is_denied(item=value):
            if stats is not None:
                stats.resources_dropped += 1
            return {}
        return self._walk(value=value, stats=stats)

    def _walk(self, value: Any, stats: FilterStats | None) -> Any:
        if isinstance(value, list):
            kept: list[Any] = []
            for item in value:
                if self._is_denied(item=item):
                    if stats is not None:
                        stats.resources_dropped += 1
                    continue
                kept.append(self._walk(value=item, stats=stats))
            return kept
        if isinstance(value, dict):
            return {
                key: self._walk(value=item, stats=stats) for key, item in value.items()
            }
        return value

    def _is_denied(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        return (
            self._matches_project_key(item=item)
            or self._matches_space_key(item=item)
            or self._matches_label(item=item)
        )

    def _matches_project_key(self, item: dict[str, Any]) -> bool:
        if not self._deny_project_keys:
            return False
        project = item.get("project")
        if isinstance(project, dict):
            project_key = project.get("key")
            if isinstance(project_key, str) and project_key in self._deny_project_keys:
                return True
        # Issue-style top-level key (e.g. "ABC-123") — the project key is
        # the prefix before the dash.
        top_key = item.get("key")
        if isinstance(top_key, str) and "-" in top_key:
            prefix = top_key.split(sep="-", maxsplit=1)[0]
            if prefix in self._deny_project_keys:
                return True
        return False

    def _matches_space_key(self, item: dict[str, Any]) -> bool:
        if not self._deny_space_keys:
            return False
        space = item.get("space")
        if isinstance(space, dict):
            space_key = space.get("key")
            if isinstance(space_key, str) and space_key in self._deny_space_keys:
                return True
        # Some Confluence simplified responses surface space_key directly.
        flat = item.get("space_key")
        if isinstance(flat, str) and flat in self._deny_space_keys:
            return True
        return False

    def _matches_label(self, item: dict[str, Any]) -> bool:
        if not self._deny_labels:
            return False
        labels = item.get("labels")
        if not isinstance(labels, list):
            return False
        for label in labels:
            if isinstance(label, str) and label in self._deny_labels:
                return True
            if (
                isinstance(label, dict)
                and isinstance(label.get("name"), str)
                and label["name"] in self._deny_labels
            ):
                return True
        return False
