"""Confluence DC auth matrix tests -- read/write ops x 3 auth methods."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig

from .conftest import AuthVariant, DCInstanceInfo, DCResourceTracker

pytestmark = pytest.mark.dc_e2e


@pytest.fixture(params=["basic", "pat", "byo_oauth"])
def confluence_auth(
    request: pytest.FixtureRequest,
    auth_variants: list[AuthVariant],
) -> ConfluenceConfig:
    """Parametrized fixture yielding ConfluenceConfig per auth method."""
    name = request.param
    for variant in auth_variants:
        if variant.name == name:
            return variant.confluence_config
    pytest.skip(f"Auth variant '{name}' not available (PAT creation may have failed)")


@pytest.fixture
def authed_confluence(
    confluence_auth: ConfluenceConfig,
) -> ConfluenceFetcher:
    """Create a ConfluenceFetcher from the parametrized auth config."""
    return ConfluenceFetcher(config=confluence_auth)


class TestConfluenceReadOperations:
    """Confluence read operations tested across all auth methods."""

    def test_get_page(
        self,
        authed_confluence: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        page = authed_confluence.get_page_content(dc_instance.test_page_id)
        assert page is not None
        assert page.id == dc_instance.test_page_id

    def test_search(
        self,
        authed_confluence: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        results = authed_confluence.search(
            cql=f"space={dc_instance.space_key} AND type=page",
            limit=5,
        )
        assert isinstance(results, list)
        assert len(results) > 0

    def test_get_spaces(
        self,
        authed_confluence: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        spaces = authed_confluence.get_spaces()
        assert isinstance(spaces, dict)
        assert "results" in spaces
        space_keys = [s["key"] for s in spaces["results"]]
        assert dc_instance.space_key in space_keys


class TestConfluenceWriteOperations:
    """Confluence write operations tested across all auth methods."""

    def test_create_and_delete_page(
        self,
        authed_confluence: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = authed_confluence.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Auth Matrix Test {uid}",
            body="<p>Created by auth matrix test.</p>",
        )
        resource_tracker.add_confluence_page(page.id)
        assert page.title == f"E2E Auth Matrix Test {uid}"

    def test_update_page(
        self,
        authed_confluence: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = authed_confluence.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Update Test {uid}",
            body="<p>Will be updated.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        updated = authed_confluence.update_page(
            page_id=page.id,
            title=f"E2E Update Test {uid}",
            body="<p>Updated content.</p>",
        )
        assert updated is not None

    def test_add_comment(
        self,
        authed_confluence: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = authed_confluence.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Comment Test {uid}",
            body="<p>For comment testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        comment = authed_confluence.add_comment(
            page_id=page.id,
            content=f"Test comment {uid}",
        )
        assert comment is not None
