"""Tests for CONFLUENCE_SPACES_FILTER resolution in ScopeMixin and search."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from requests import Response
from requests.exceptions import HTTPError

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.exceptions import ScopeViolationError

BASE = "https://example.atlassian.net/wiki"


def _fetcher(
    spaces_filter: str | None = "ALLOWED", auth_type: str = "basic"
) -> ConfluenceFetcher:
    kwargs: dict[str, Any] = {"username": "u", "api_token": "t"}
    if auth_type == "oauth":
        kwargs = {"oauth_config": MagicMock(cloud_id="c")}
    fetcher = ConfluenceFetcher(
        config=ConfluenceConfig(
            url=BASE, auth_type=auth_type, spaces_filter=spaces_filter, **kwargs
        )
    )
    backend = MagicMock()
    backend.url = BASE
    fetcher.confluence = backend
    return fetcher


def _route(fetcher: ConfluenceFetcher, responses: dict[str, Any]) -> list[str]:
    seen: list[str] = []

    def get(url: str, params: Any = None) -> Any:
        seen.append(url)
        payload = responses.get(url)
        if payload is None:
            response = Response()
            response.status_code = 404
            raise HTTPError(response=response)
        if isinstance(payload, Exception):
            raise payload
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    fetcher.confluence._session.get.side_effect = get
    return seen


def test_no_filter_makes_no_api_calls() -> None:
    fetcher = _fetcher(None)
    fetcher.ensure_content_allowed("1")
    fetcher.ensure_space_allowed("ANY")
    assert fetcher.confluence.method_calls == []


def test_v1_content_resolves_space() -> None:
    fetcher = _fetcher()
    _route(fetcher, {f"{BASE}/rest/api/content/1": {"space": {"key": "allowed"}}})
    fetcher.ensure_content_allowed("1")
    _route(fetcher, {f"{BASE}/rest/api/content/2": {"space": {"key": "SECRET"}}})
    with pytest.raises(ScopeViolationError, match="CONFLUENCE_SPACES_FILTER"):
        fetcher.ensure_content_allowed("2")


def test_lookup_failure_denies() -> None:
    fetcher = _fetcher()
    _route(fetcher, {})
    with pytest.raises(ScopeViolationError, match="could not be verified"):
        fetcher.ensure_content_allowed("404")


def test_v2_attachment_resolves_through_parent_page() -> None:
    fetcher = _fetcher(auth_type="oauth")
    seen = _route(
        fetcher,
        {
            f"{BASE}/api/v2/attachments/att9": {"pageId": "77"},
            f"{BASE}/api/v2/pages/77": {"spaceId": "5"},
            f"{BASE}/api/v2/spaces/5": {"key": "SECRET"},
        },
    )
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_content_allowed("att9")
    assert f"{BASE}/api/v2/pages/att9" in seen  # tried before attachments


def test_v2_server_error_is_not_skipped() -> None:
    fetcher = _fetcher(auth_type="oauth")
    response = Response()
    response.status_code = 500
    _route(fetcher, {f"{BASE}/api/v2/pages/1": HTTPError(response=response)})
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_content_allowed("1")


def test_space_id_without_key_denies() -> None:
    # ConfluenceV2Adapter falls back to the ID when the key lookup fails; the
    # scope check must not.
    fetcher = _fetcher()
    _route(fetcher, {f"{BASE}/api/v2/spaces/5": {"id": "5"}})
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_space_id_allowed("5")


def test_global_template_is_allowed_space_template_is_checked() -> None:
    fetcher = _fetcher()
    _route(
        fetcher,
        {
            f"{BASE}/rest/api/template/g1": {"templateId": "g1"},
            f"{BASE}/rest/api/template/s1": {"space": {"key": "SECRET"}},
        },
    )
    fetcher.ensure_template_allowed("g1")
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_template_allowed("s1")


def test_search_rejects_unbalanced_cql_under_filter() -> None:
    fetcher = _fetcher()
    with pytest.raises(Exception, match="CQL query rejected"):
        fetcher.search("type = page) OR (space = SECRET")
    fetcher.confluence.cql.assert_not_called()


def test_caller_spaces_filter_cannot_inject_cql() -> None:
    fetcher = _fetcher()
    fetcher.confluence.cql.return_value = {"results": []}
    fetcher.search("type = page", spaces_filter="NOPE) OR (space = SECRET")
    cql = fetcher.confluence.cql.call_args.kwargs["cql"]
    assert cql == (
        '((type = page) AND (space = ALLOWED)) AND (space = "NOPE) OR (space = SECRET")'
    )
