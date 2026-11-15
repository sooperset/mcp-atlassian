"""Resolve Confluence identifiers to spaces and enforce CONFLUENCE_SPACES_FILTER.

Content IDs (pages, blog posts, folders, attachments, comments) are resolved
through the API to the space that holds them. Cloud OAuth deployments use the
v2 API because the v1 content endpoints are not available there; every other
deployment uses v1 ``/rest/api/content/{id}?expand=space``. A check that cannot
resolve the identifier denies it.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from requests.exceptions import HTTPError

from ..exceptions import ScopeViolationError
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


def _denied(kind: str, value: object) -> ScopeViolationError:
    return ScopeViolationError(
        f"Confluence {kind} '{value}' is outside the configured {_FILTER_NAME} "
        "or could not be verified."
    )


def _path_segment(value: object) -> str:
    return quote(str(value).strip(), safe="")


class ScopeMixin(ConfluenceClient):
    """Space-allowlist checks shared by every Confluence tool."""

    def allowed_spaces(self) -> frozenset[str] | None:
        """Return the upper-cased CONFLUENCE_SPACES_FILTER keys, or None."""
        raw = getattr(self.config, "spaces_filter", None)
        if not isinstance(raw, str):
            return None
        keys = frozenset(k.strip().upper() for k in raw.split(",") if k.strip())
        return keys or None

    def _uses_v2_for_scope(self) -> bool:
        return self.config.auth_type == "oauth" and bool(self.config.is_cloud)

    def _scope_get(self, url: str, params: dict[str, str] | None = None) -> Any:
        response = self.confluence._session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _v2_space_key(self, space_id: object) -> str:
        data = self._scope_get(
            f"{self.confluence.url.rstrip('/')}/api/v2/spaces/{_path_segment(space_id)}"
        )
        key = data.get("key") if isinstance(data, dict) else None
        if not isinstance(key, str) or not key:
            msg = f"No key in v2 space response for {space_id!r}"
            raise ValueError(msg)
        return key

    def _v2_content_space_key(self, content_id: object, hops: int = 0) -> str:
        base = self.confluence.url.rstrip("/")
        segment = _path_segment(content_id)
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
            f"{self._v1_rest_base_url()}/rest/api/content/{_path_segment(content_id)}",
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
        self.ensure_space_allowed(space_key)

    def ensure_template_allowed(self, template_id: object) -> None:
        """Check a space template's space. Global templates have no space."""
        if self.allowed_spaces() is None or not self.config.is_cloud:
            # The template API is Cloud-only; the tool itself rejects DC.
            return
        try:
            data = self._scope_get(
                f"{self._v1_rest_base_url()}/rest/api/template/"
                f"{_path_segment(template_id)}"
            )
        except Exception as e:  # noqa: BLE001 - any failure denies
            logger.warning(
                f"Could not resolve Confluence template {template_id!r}: {e}"
            )
            raise _denied("template", template_id) from e
        space = data.get("space") if isinstance(data, dict) else None
        if space:
            self.ensure_space_allowed((space or {}).get("key"))
