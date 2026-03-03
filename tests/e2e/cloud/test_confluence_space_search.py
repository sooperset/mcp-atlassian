"""E2E: CQL space-type search returns results (regression #907)."""

from __future__ import annotations

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

pytestmark = pytest.mark.cloud_e2e


class TestConfluenceCQLSpaceSearch:
    """CQL type=space searches return results (not empty list).

    Regression for https://github.com/sooperset/mcp-atlassian/issues/907
    Root cause: search.py excerpt-matching uses 'content' key but space
    results use 'space' key — no match found, results silently empty.
    """

    def test_cql_type_space_returns_results(
        self,
        confluence_fetcher: ConfluenceFetcher,
    ) -> None:
        results = confluence_fetcher.search(cql="type=space", limit=10)
        assert len(results) > 0, (
            "CQL type=space returned no results — space result processing broken"
        )
