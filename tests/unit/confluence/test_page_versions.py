"""Tests for Confluence page versions functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Context

from mcp_atlassian.models.confluence import ConfluenceVersion
from mcp_atlassian.servers.confluence import get_page_versions


class TestPageVersions:
    """Test page versions functionality."""

    @pytest.fixture
    def mock_confluence_fetcher(self):
        """Mock confluence fetcher."""
        fetcher = MagicMock()
        return fetcher

    @pytest.fixture
    def mock_context(self):
        """Mock FastMCP context."""
        return MagicMock(spec=Context)

    @pytest.fixture
    def sample_version(self):
        """Sample version data."""
        return ConfluenceVersion(
            number=1,
            when="2023-01-01T10:00:00.000Z",
            message="Initial version",
            minor_edit=False,
        )

    @pytest.mark.asyncio
    @patch("mcp_atlassian.servers.confluence.get_confluence_fetcher")
    async def test_get_page_versions_list(
        self, mock_get_fetcher, mock_context, mock_confluence_fetcher, sample_version
    ):
        """Test getting all versions of a page."""
        mock_get_fetcher.return_value = mock_confluence_fetcher
        mock_confluence_fetcher.get_page_versions.return_value = [sample_version]

        result = await get_page_versions(mock_context, "123456")

        result_data = json.loads(result)
        assert "versions" in result_data
        assert len(result_data["versions"]) == 1
        assert result_data["versions"][0]["number"] == 1

    @pytest.mark.asyncio
    @patch("mcp_atlassian.servers.confluence.get_confluence_fetcher")
    async def test_get_specific_page_version(
        self, mock_get_fetcher, mock_context, mock_confluence_fetcher, sample_version
    ):
        """Test getting a specific version of a page."""
        mock_get_fetcher.return_value = mock_confluence_fetcher
        mock_confluence_fetcher.get_page_version.return_value = sample_version

        result = await get_page_versions(mock_context, "123456", 1)

        result_data = json.loads(result)
        assert result_data["number"] == 1
        assert result_data["message"] == "Initial version"

    @pytest.mark.asyncio
    @patch("mcp_atlassian.servers.confluence.get_confluence_fetcher")
    async def test_get_page_versions_error(
        self, mock_get_fetcher, mock_context, mock_confluence_fetcher
    ):
        """Test error handling when getting page versions."""
        mock_get_fetcher.return_value = mock_confluence_fetcher
        mock_confluence_fetcher.get_page_versions.side_effect = ValueError("Page not found")

        result = await get_page_versions(mock_context, "invalid")

        result_data = json.loads(result)
        assert result_data["error"] == "operation_failed"
        assert "Page not found" in result_data["message"]
