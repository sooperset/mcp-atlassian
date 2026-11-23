"""Resolve Confluence identifiers to spaces and enforce CONFLUENCE_SPACES_FILTER.

Content IDs (pages, blog posts, folders, attachments, comments) are resolved
through the API to the space that holds them. Cloud OAuth deployments use the
v2 API because the v1 content endpoints are not available there; every other
deployment uses v1 ``/rest/api/content/{id}?expand=space``. A check that cannot
resolve the identifier denies it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from requests.exceptions import HTTPError

from ..exceptions import ScopeViolationError
from ..utils.urls import path_segment
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")

_FILTER_NAME = "CONFLUENCE_SPACES_FILTER"

# v2 endpoints that can own a content ID, tried in order. Entries with a parent
# field are attached to another piece of content rather than to a space.
_V2_CONTENT_ENDPOINTS: tuple[str, ...] = (
    "pages",
    "blogposts",
    "folders",
    "whiteboards",
    "databases",
    "attachments",
    "footer-comments",
    "inline-comments",
)
_V2_PARENT_FIELDS: tuple[str, ...] = ("pageId", "blogPostId", "parentId")
_MAX_PARENT_HOPS = 3
_MAX_TEMPLATE_PAGES = 10


def _denied(kind: str, value: object) -> ScopeViolationError:
    return ScopeViolationError(
        f"Confluence {kind} '{value}' is outside the configured {_FILTER_NAME} "
        "or could not be verified."
    )


@contextmanager
def _denied_as(kind: str, value: object) -> Iterator[None]:
    """Report a denial of a resolved parent as a denial of the caller's value.

    The denial text names only what the caller passed, so it reads the same
    whether the object is missing or resolves outside the allowlist.
    """
    try:
        yield
    except ScopeViolationError:
        raise _denied(kind, value) from None


def allowed_space_keys(config: object) -> frozenset[str] | None:
    """Return the upper-cased CONFLUENCE_SPACES_FILTER keys of ``config``, or None."""
    raw = getattr(config, "spaces_filter", None)
    if not isinstance(raw, str):
        return None
    keys = frozenset(k.strip().upper() for k in raw.split(",") if k.strip())
    return keys or None


class ScopeMixin(ConfluenceClient):
    """Space-allowlist checks shared by every Confluence tool."""

    def allowed_spaces(self) -> frozenset[str] | None:
        """Return the upper-cased CONFLUENCE_SPACES_FILTER keys, or None."""
        return allowed_space_keys(self.config)

    def _uses_v2_for_scope(self) -> bool:
        return self.config.auth_type == "oauth" and bool(self.config.is_cloud)

    def _scope_get(self, url: str, params: dict[str, str] | None = None) -> Any:
        response = self.confluence._session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _v2_space_key(self, space_id: object) -> str:
        data = self._scope_get(
            f"{self.confluence.url.rstrip('/')}/api/v2/spaces/{path_segment(space_id)}"
        )
        key = data.get("key") if isinstance(data, dict) else None
        if not isinstance(key, str) or not key:
            msg = f"No key in v2 space response for {space_id!r}"
            raise ValueError(msg)
        return key

    def _v2_content_space_key(self, content_id: object, hops: int = 0) -> str:
        base = self.confluence.url.rstrip("/")
        segment = path_segment(content_id)
        for endpoint in _V2_CONTENT_ENDPOINTS:
            try:
                data = self._scope_get(f"{base}/api/v2/{endpoint}/{segment}")
            except HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status in (400, 404):
                    continue
                raise
            if not isinstance(data, dict):
                continue
            space_id = data.get("spaceId")
            if space_id:
                return self._v2_space_key(space_id)
            for field in _V2_PARENT_FIELDS:
                parent_id = data.get(field)
                if parent_id and hops < _MAX_PARENT_HOPS:
                    return self._v2_content_space_key(parent_id, hops + 1)
            msg = f"v2 {endpoint} {content_id!r} has no space or parent"
            raise ValueError(msg)
        msg = f"Content {content_id!r} not found through the v2 API"
        raise ValueError(msg)

    def _v1_content_space_key(self, content_id: object) -> str:
        data = self._scope_get(
            f"{self._v1_rest_base_url()}/rest/api/content/{path_segment(content_id)}",
            params={"expand": "space"},
        )
        key = ((data or {}).get("space") or {}).get("key")
        if not isinstance(key, str) or not key:
            msg = f"No space in v1 content response for {content_id!r}"
            raise ValueError(msg)
        return key

    def ensure_space_allowed(self, space_key: object) -> None:
        """Raise ScopeViolationError if ``space_key`` is not allowlisted."""
        allowed = self.allowed_spaces()
        if allowed is None:
            return
        if not isinstance(space_key, str) or space_key.strip().upper() not in allowed:
            raise _denied("space", space_key)

    def ensure_content_allowed(self, content_id: object) -> None:
        """Resolve a page, blog post, attachment or comment ID and check it."""
        if self.allowed_spaces() is None:
            return
        if content_id is None or not str(content_id).strip():
            raise _denied("content", content_id)
        try:
            if self._uses_v2_for_scope():
                space_key = self._v2_content_space_key(content_id)
            else:
                space_key = self._v1_content_space_key(content_id)
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Confluence content {content_id!r}: {e}")
            raise _denied("content", content_id) from e
        with _denied_as("content", content_id):
            self.ensure_space_allowed(space_key)

    def ensure_space_id_allowed(self, space_id: object) -> None:
        """Resolve a numeric space ID (Cloud v2) and check its key."""
        if self.allowed_spaces() is None:
            return
        try:
            space_key = self._v2_space_key(space_id)
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(f"Could not resolve Confluence space {space_id!r}: {e}")
            raise _denied("space", space_id) from e
        with _denied_as("space", space_id):
            self.ensure_space_allowed(space_key)

    def ensure_template_allowed(self, template_id: object) -> None:
        """Check a template's space; a template with no space must be global.

        A template is allowed when its response names an allowlisted space,
        or when it names no space and is listed among the global templates.
        """
        if self.allowed_spaces() is None or not self.config.is_cloud:
            # The template API is Cloud-only; the tool itself rejects DC.
            return
        base = f"{self._v1_rest_base_url()}/rest/api/template"
        try:
            data = self._scope_get(
                f"{base}/{path_segment(template_id)}", params={"expand": "space"}
            )
            if not isinstance(data, dict):
                raise ValueError("template response is not an object")
            space = data.get("space")
            if isinstance(space, dict) and space.get("key"):
                space_key = space["key"]
            elif space is None and "space" not in (data.get("_expandable") or {}):
                if not self._is_global_template(base, str(template_id).strip()):
                    raise ValueError("template has no space and is not global")
                return
            else:
                raise ValueError("template space could not be read")
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(
                f"Could not resolve Confluence template {template_id!r}: {e}"
            )
            raise _denied("template", template_id) from e
        with _denied_as("template", template_id):
            self.ensure_space_allowed(space_key)

    def _is_global_template(self, base: str, template_id: str) -> bool:
        """Return True if ``template_id`` is in the global page template list."""
        page_size = 100
        for page in range(_MAX_TEMPLATE_PAGES):
            data = self._scope_get(
                f"{base}/page",
                params={"start": str(page * page_size), "limit": str(page_size)},
            )
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                return False
            if any(
                isinstance(item, dict) and str(item.get("templateId")) == template_id
                for item in results
            ):
                return True
            if len(results) < page_size:
                return False
        return False
