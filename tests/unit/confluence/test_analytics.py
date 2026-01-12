"""Tests for the Confluence Analytics mixin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.confluence.analytics import AnalyticsMixin
from mcp_atlassian.models.confluence.analytics import PageViews, PageViewsBatchResponse


class TestAnalyticsMixin:
    """Tests for the AnalyticsMixin class."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = MagicMock()
        config.is_cloud = True
        return config

    @pytest.fixture
    def analytics_mixin(self, mock_config):
        """Create an AnalyticsMixin instance with mocked dependencies."""
        mixin = MagicMock(spec=AnalyticsMixin)
        mixin.config = mock_config
        mixin.confluence = MagicMock()
        mixin.v2_adapter = None

        # Bind the real methods
        mixin.get_page_views = lambda *args, **kwargs: AnalyticsMixin.get_page_views(
            mixin, *args, **kwargs
        )
        mixin.batch_get_page_views = (
            lambda *args, **kwargs: AnalyticsMixin.batch_get_page_views(
                mixin, *args, **kwargs
            )
        )
        mixin._get_page_views_direct = (
            lambda *args, **kwargs: AnalyticsMixin._get_page_views_direct(
                mixin, *args, **kwargs
            )
        )

        return mixin

    def test_get_page_views_cloud_only(self, analytics_mixin):
        """Test that get_page_views requires Cloud instance."""
        analytics_mixin.config.is_cloud = False

        with pytest.raises(ValueError) as exc_info:
            analytics_mixin.get_page_views("123456")

        assert "only available for Confluence Cloud" in str(exc_info.value)

    def test_get_page_views_basic(self, analytics_mixin):
        """Test basic page views retrieval."""
        # Mock page title fetch
        analytics_mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}

        # Mock views API response
        mock_response = MagicMock()
        mock_response.json.return_value = {"count": 42, "lastSeen": None}
        analytics_mixin.confluence._session.get.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        result = analytics_mixin.get_page_views("123456")

        assert isinstance(result, PageViews)
        assert result.page_id == "123456"
        assert result.page_title == "Test Page"
        assert result.total_views == 42

    def test_get_page_views_with_last_seen(self, analytics_mixin):
        """Test page views with last seen timestamp."""
        analytics_mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "count": 100,
            "lastSeen": "2023-06-15T10:30:00.000Z",
        }
        analytics_mixin.confluence._session.get.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        result = analytics_mixin.get_page_views("123456")

        assert result.total_views == 100
        assert result.last_viewed is not None

    def test_get_page_views_without_title(self, analytics_mixin):
        """Test page views without fetching title."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"count": 25}
        analytics_mixin.confluence._session.get.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        result = analytics_mixin.get_page_views("123456", include_title=False)

        assert result.page_id == "123456"
        assert result.page_title is None
        assert result.total_views == 25
        analytics_mixin.confluence.get_page_by_id.assert_not_called()

    def test_get_page_views_http_error_non_auth(self, analytics_mixin):
        """Test that non-auth HTTP errors return zero views."""
        analytics_mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}

        # Create HTTPError with 404 status
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = HTTPError(response=mock_response)
        analytics_mixin.confluence._session.get.side_effect = http_error

        result = analytics_mixin.get_page_views("123456")

        assert result.total_views == 0

    def test_get_page_views_http_error_auth_propagated(self, analytics_mixin):
        """Test that auth errors (401/403) are propagated."""
        analytics_mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}

        # Create HTTPError with 401 status
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = HTTPError(response=mock_response)
        analytics_mixin.confluence._session.get.side_effect = http_error

        with pytest.raises(HTTPError):
            analytics_mixin.get_page_views("123456")

    def test_batch_get_page_views(self, analytics_mixin):
        """Test batch page views retrieval."""
        analytics_mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}

        mock_response = MagicMock()
        mock_response.json.return_value = {"count": 10}
        analytics_mixin.confluence._session.get.return_value = mock_response
        mock_response.raise_for_status = MagicMock()

        result = analytics_mixin.batch_get_page_views(
            ["111", "222", "333"], include_title=False
        )

        assert isinstance(result, PageViewsBatchResponse)
        assert result.total_count == 3
        assert result.success_count == 3
        assert result.error_count == 0
        assert len(result.pages) == 3

    def test_batch_get_page_views_with_errors(self, analytics_mixin):
        """Test batch page views with some errors."""

        def mock_get_views(url, **kwargs):
            if "222" in url:
                response = MagicMock()
                response.status_code = 404
                raise HTTPError(response=response)
            response = MagicMock()
            response.json.return_value = {"count": 10}
            response.raise_for_status = MagicMock()
            return response

        analytics_mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}
        analytics_mixin.confluence._session.get.side_effect = mock_get_views

        result = analytics_mixin.batch_get_page_views(
            ["111", "222", "333"], include_title=False
        )

        # Non-auth errors should return zero views, not be counted as errors
        assert result.total_count == 3
        # Page 222 returns 0 views instead of error
        assert result.success_count == 3
        assert result.error_count == 0


class TestAnalyticsModels:
    """Tests for the Analytics Pydantic models."""

    def test_page_views_basic(self):
        """Test PageViews serialization."""
        views = PageViews(
            page_id="123456",
            page_title="Test Page",
            total_views=42,
        )

        result = views.to_simplified_dict()

        assert result["page_id"] == "123456"
        assert result["page_title"] == "Test Page"
        assert result["total_views"] == 42
        assert "unique_viewers" not in result
        assert "last_viewed" not in result

    def test_page_views_with_all_fields(self):
        """Test PageViews with all fields."""
        last_viewed = datetime(2023, 6, 15, 10, 30, tzinfo=timezone.utc)
        views = PageViews(
            page_id="123456",
            page_title="Test Page",
            total_views=100,
            unique_viewers=25,
            last_viewed=last_viewed,
        )

        result = views.to_simplified_dict()

        assert result["total_views"] == 100
        assert result["unique_viewers"] == 25
        assert "last_viewed" in result

    def test_page_views_without_title(self):
        """Test PageViews without title."""
        views = PageViews(
            page_id="123456",
            total_views=50,
        )

        result = views.to_simplified_dict()

        assert result["page_id"] == "123456"
        assert "page_title" not in result
        assert result["total_views"] == 50

    def test_page_views_batch_response(self):
        """Test PageViewsBatchResponse serialization."""
        pages = [
            PageViews(page_id="111", total_views=10),
            PageViews(page_id="222", total_views=20),
        ]

        response = PageViewsBatchResponse(
            pages=pages,
            total_count=3,
            success_count=2,
            error_count=1,
            errors=[{"page_id": "333", "error": "Not found"}],
        )

        result = response.to_simplified_dict()

        assert result["total_count"] == 3
        assert result["success_count"] == 2
        assert result["error_count"] == 1
        assert len(result["pages"]) == 2
        assert len(result["errors"]) == 1

    def test_page_views_batch_response_no_errors(self):
        """Test PageViewsBatchResponse without errors."""
        pages = [
            PageViews(page_id="111", total_views=10),
        ]

        response = PageViewsBatchResponse(
            pages=pages,
            total_count=1,
            success_count=1,
            error_count=0,
            errors=[],
        )

        result = response.to_simplified_dict()

        assert result["total_count"] == 1
        assert result["success_count"] == 1
        assert result["error_count"] == 0
        assert "errors" not in result  # Empty errors list should be omitted
