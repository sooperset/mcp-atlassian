"""Tests for the Confluence Analytics mixin."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.analytics import AVAILABLE_METRICS, AnalyticsMixin
from mcp_atlassian.confluence.config import AnalyticsConfig
from mcp_atlassian.models.confluence import (
    AnalyticsNotAvailableError,
    EngagementScoreMetric,
    PageAnalyticsBatchResponse,
    PageAnalyticsResponse,
    PageViewsBatchResponse,
    PageViewsResponse,
    SpaceAnalyticsResponse,
    SpacePageSummary,
    SpaceSummary,
    StalenessMetric,
    ViewerDiversityMetric,
    ViewVelocityMetric,
)


class TestAnalyticsModels:
    """Tests for the analytics Pydantic models."""

    def test_page_views_response_creation(self):
        """Test PageViewsResponse model creation."""
        response = PageViewsResponse(
            page_id="123456",
            page_title="Test Page",
            total_views=100,
            unique_viewers=25,
            from_date="2023-01-01",
            to_date="2023-12-31",
        )

        assert response.page_id == "123456"
        assert response.page_title == "Test Page"
        assert response.total_views == 100
        assert response.unique_viewers == 25
        assert response.from_date == "2023-01-01"
        assert response.to_date == "2023-12-31"

    def test_page_views_response_to_simplified_dict(self):
        """Test PageViewsResponse serialization."""
        response = PageViewsResponse(
            page_id="123456",
            page_title="Test Page",
            total_views=100,
            unique_viewers=25,
            from_date="2023-01-01",
        )

        result = response.to_simplified_dict()

        assert result["page_id"] == "123456"
        assert result["page_title"] == "Test Page"
        assert result["total_views"] == 100
        assert result["unique_viewers"] == 25
        assert result["from_date"] == "2023-01-01"
        assert "to_date" not in result  # None values should be excluded

    def test_page_views_response_without_optional_fields(self):
        """Test PageViewsResponse with minimal fields."""
        response = PageViewsResponse(
            page_id="123456",
            total_views=50,
            unique_viewers=10,
        )

        result = response.to_simplified_dict()

        assert result["page_id"] == "123456"
        assert result["total_views"] == 50
        assert result["unique_viewers"] == 10
        assert "page_title" not in result
        assert "from_date" not in result

    def test_page_views_response_from_api_response(self):
        """Test creating PageViewsResponse from API data."""
        api_data = {"count": 150}
        result = PageViewsResponse.from_api_response(
            api_data,
            page_id="789",
            page_title="API Page",
            from_date="2023-06-01",
        )

        assert result.page_id == "789"
        assert result.page_title == "API Page"
        assert result.total_views == 150
        assert result.from_date == "2023-06-01"

    def test_page_views_batch_response_creation(self):
        """Test PageViewsBatchResponse model creation."""
        pages = [
            PageViewsResponse(page_id="1", total_views=100, unique_viewers=20),
            PageViewsResponse(page_id="2", total_views=200, unique_viewers=40),
        ]

        batch = PageViewsBatchResponse(
            pages=pages,
            total_count=3,
            success_count=2,
            error_count=1,
            errors=[{"page_id": "3", "error": "Not found"}],
            from_date="2023-01-01",
        )

        assert batch.total_count == 3
        assert batch.success_count == 2
        assert batch.error_count == 1
        assert len(batch.pages) == 2
        assert len(batch.errors) == 1

    def test_page_views_batch_response_to_simplified_dict(self):
        """Test PageViewsBatchResponse serialization."""
        pages = [
            PageViewsResponse(page_id="1", total_views=100, unique_viewers=20),
        ]

        batch = PageViewsBatchResponse(
            pages=pages,
            total_count=2,
            success_count=1,
            error_count=1,
            errors=[{"page_id": "2", "error": "Error"}],
        )

        result = batch.to_simplified_dict()

        assert result["total_count"] == 2
        assert result["success_count"] == 1
        assert result["error_count"] == 1
        assert len(result["pages"]) == 1
        assert len(result["errors"]) == 1


class TestAnalyticsMixin:
    """Tests for the AnalyticsMixin class."""

    def test_analytics_not_available_on_server(self):
        """Test that analytics raises error on Server/DC."""
        # Create a mixin-like object with server config
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = False

        # Test the property directly by calling the getter function
        with pytest.raises(AnalyticsNotAvailableError) as exc_info:
            AnalyticsMixin._analytics_adapter.fget(mixin)

        assert "Cloud" in str(exc_info.value)
        assert "Server/Data Center" in str(exc_info.value)

    def test_get_page_views_cloud_success(self):
        """Test successful page view retrieval on Cloud."""
        # Create a mock adapter with proper return values
        mock_adapter = MagicMock()
        mock_adapter.get_content_views.return_value = {"count": 150}
        mock_adapter.get_content_viewers.return_value = {"count": 30}

        patch_target = "mcp_atlassian.confluence.analytics.ConfluenceV2Adapter"
        with patch(patch_target) as adapter_class:
            adapter_class.return_value = mock_adapter

            # Create a class that includes the property
            class MockMixin:
                @property
                def _analytics_adapter(self):
                    return adapter_class()

            mixin = MockMixin()
            mixin.config = MagicMock()
            mixin.config.is_cloud = True
            mixin.confluence = MagicMock()
            mixin.confluence._session = MagicMock()
            mixin.confluence.url = "https://example.atlassian.net/wiki"
            mixin.confluence.get_page_by_id.return_value = {"title": "Test Page"}

            # Call the real get_page_views method
            result = AnalyticsMixin.get_page_views(
                mixin,
                page_id="123456",
                from_date="2023-01-01",
                include_viewers=True,
            )

            assert result.page_id == "123456"
            assert result.total_views == 150
            assert result.unique_viewers == 30
            assert result.from_date == "2023-01-01"
            mock_adapter.get_content_views.assert_called_once()
            mock_adapter.get_content_viewers.assert_called_once()

    def test_get_page_views_without_viewers(self):
        """Test page view retrieval without fetching viewers."""
        mock_adapter = MagicMock()
        mock_adapter.get_content_views.return_value = {"count": 100}

        patch_target = "mcp_atlassian.confluence.analytics.ConfluenceV2Adapter"
        with patch(patch_target) as adapter_class:
            adapter_class.return_value = mock_adapter

            class MockMixin:
                @property
                def _analytics_adapter(self):
                    return adapter_class()

            mixin = MockMixin()
            mixin.config = MagicMock()
            mixin.config.is_cloud = True
            mixin.confluence = MagicMock()
            mixin.confluence._session = MagicMock()
            mixin.confluence.url = "https://example.atlassian.net/wiki"
            mixin.confluence.get_page_by_id.return_value = None

            result = AnalyticsMixin.get_page_views(
                mixin,
                page_id="123456",
                include_viewers=False,
            )

            assert result.total_views == 100
            assert result.unique_viewers == 0
            mock_adapter.get_content_viewers.assert_not_called()

    def test_batch_get_page_views_success(self):
        """Test batch page view retrieval."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.confluence = MagicMock()
        mixin.confluence._session = MagicMock()
        mixin.confluence.url = "https://example.atlassian.net/wiki"
        mixin.confluence.get_page_by_id.return_value = None

        # Mock the get_page_views method to return proper objects
        # since batch_get_page_views calls self.get_page_views
        def mock_get_page_views(page_id, from_date=None, *, include_viewers=True):
            return PageViewsResponse(
                page_id=page_id,
                total_views=50,
                unique_viewers=10 if include_viewers else 0,
                from_date=from_date,
            )

        mixin.get_page_views = mock_get_page_views

        result = AnalyticsMixin.batch_get_page_views(
            mixin,
            page_ids=["1", "2", "3"],
            from_date="2023-01-01",
        )

        assert result.total_count == 3
        assert result.success_count == 3
        assert result.error_count == 0
        assert len(result.pages) == 3

    def test_batch_get_page_views_with_errors(self):
        """Test batch page view retrieval with some errors."""

        def mock_get_page_views(page_id, from_date=None, *, include_viewers=True):
            if page_id == "2":
                raise ValueError("Page not found")
            return PageViewsResponse(
                page_id=page_id,
                total_views=50,
                unique_viewers=10,
                from_date=from_date,
            )

        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.get_page_views = mock_get_page_views

        result = AnalyticsMixin.batch_get_page_views(
            mixin,
            page_ids=["1", "2", "3"],
        )

        assert result.total_count == 3
        assert result.success_count == 2
        assert result.error_count == 1
        assert len(result.errors) == 1
        assert result.errors[0]["page_id"] == "2"

    def test_batch_get_page_views_server_error(self):
        """Test batch operation fails immediately on Server/DC."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = False

        with pytest.raises(AnalyticsNotAvailableError):
            AnalyticsMixin.batch_get_page_views(mixin, page_ids=["1", "2"])


class TestAnalyticsNotAvailableError:
    """Tests for the AnalyticsNotAvailableError exception."""

    def test_error_creation(self):
        """Test creating the error with a message."""
        error = AnalyticsNotAvailableError("Analytics not available")
        assert str(error) == "Analytics not available"

    def test_error_inheritance(self):
        """Test that the error inherits from Exception."""
        error = AnalyticsNotAvailableError("Test")
        assert isinstance(error, Exception)

    def test_error_can_be_raised_and_caught(self):
        """Test that the error can be properly raised and caught."""
        with pytest.raises(AnalyticsNotAvailableError) as exc_info:
            raise AnalyticsNotAvailableError("Cloud only feature")

        assert "Cloud only" in str(exc_info.value)


# =============================================================================
# Phase 4: Page Analytics Metric Tests
# =============================================================================


class TestAnalyticsConfig:
    """Tests for the AnalyticsConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AnalyticsConfig()
        assert config.period_days == 30
        assert "engagement_score" in config.metrics
        assert "staleness" in config.metrics

    def test_config_from_env_defaults(self):
        """Test config from environment with defaults."""
        with patch.dict("os.environ", {}, clear=True):
            config = AnalyticsConfig.from_env()
            assert config.period_days == 30
            assert config.metrics == ["engagement_score", "staleness"]

    def test_config_from_env_custom(self):
        """Test config from environment with custom values."""
        with patch.dict(
            "os.environ",
            {
                "CONFLUENCE_ANALYTICS_METRICS": "engagement_score,view_velocity",
                "CONFLUENCE_ANALYTICS_PERIOD_DAYS": "60",
            },
        ):
            config = AnalyticsConfig.from_env()
            assert config.period_days == 60
            assert "engagement_score" in config.metrics
            assert "view_velocity" in config.metrics

    def test_config_from_env_invalid_period(self):
        """Test config handles invalid period_days gracefully."""
        with patch.dict(
            "os.environ",
            {"CONFLUENCE_ANALYTICS_PERIOD_DAYS": "not_a_number"},
        ):
            config = AnalyticsConfig.from_env()
            assert config.period_days == 30  # Falls back to default


class TestEngagementScoreMetric:
    """Tests for the EngagementScoreMetric model."""

    def test_metric_creation(self):
        """Test creating an engagement score metric."""
        metric = EngagementScoreMetric(
            value=75,
            components={"view_score": 80, "viewer_score": 70, "recency_score": 75},
        )
        assert metric.value == 75
        assert metric.components["view_score"] == 80

    def test_metric_to_simplified_dict(self):
        """Test serialization."""
        metric = EngagementScoreMetric(
            value=50,
            components={"view_score": 60, "viewer_score": 40, "recency_score": 50},
        )
        result = metric.to_simplified_dict()
        assert result["value"] == 50
        assert "components" in result

    def test_metric_value_bounds(self):
        """Test that values are within 0-100."""
        metric = EngagementScoreMetric(value=0, components={})
        assert metric.value == 0

        metric = EngagementScoreMetric(value=100, components={})
        assert metric.value == 100


class TestViewVelocityMetric:
    """Tests for the ViewVelocityMetric model."""

    def test_metric_creation(self):
        """Test creating a view velocity metric."""
        metric = ViewVelocityMetric(
            trend="increasing",
            current_period_views=150,
            previous_period_views=100,
            change_percent=50.0,
        )
        assert metric.trend == "increasing"
        assert metric.change_percent == 50.0

    def test_metric_to_simplified_dict(self):
        """Test serialization rounds change_percent."""
        metric = ViewVelocityMetric(
            trend="stable",
            current_period_views=100,
            previous_period_views=98,
            change_percent=2.0408163265306123,
        )
        result = metric.to_simplified_dict()
        assert result["change_percent"] == 2.04  # Rounded to 2 decimals

    def test_trend_values(self):
        """Test different trend values."""
        for trend in ["increasing", "decreasing", "stable"]:
            metric = ViewVelocityMetric(
                trend=trend,
                current_period_views=0,
                previous_period_views=0,
                change_percent=0.0,
            )
            assert metric.trend == trend


class TestStalenessMetric:
    """Tests for the StalenessMetric model."""

    def test_metric_creation(self):
        """Test creating a staleness metric."""
        metric = StalenessMetric(
            days_since_last_view=5,
            days_since_last_edit=10,
            status="active",
            stale_threshold_days=90,
        )
        assert metric.status == "active"
        assert metric.days_since_last_view == 5

    def test_metric_to_simplified_dict(self):
        """Test serialization with optional fields."""
        metric = StalenessMetric(
            days_since_last_view=None,  # Never viewed
            days_since_last_edit=30,
            status="abandoned",
            stale_threshold_days=90,
        )
        result = metric.to_simplified_dict()
        assert result["status"] == "abandoned"
        assert "days_since_last_view" not in result  # None excluded
        assert result["days_since_last_edit"] == 30

    def test_status_values(self):
        """Test different status values."""
        for status in ["active", "stale", "abandoned"]:
            metric = StalenessMetric(
                status=status,
                stale_threshold_days=90,
            )
            assert metric.status == status


class TestViewerDiversityMetric:
    """Tests for the ViewerDiversityMetric model."""

    def test_metric_creation(self):
        """Test creating a viewer diversity metric."""
        metric = ViewerDiversityMetric(
            ratio=0.5,
            interpretation="moderate",
            unique_viewers=25,
            total_views=50,
        )
        assert metric.ratio == 0.5
        assert metric.interpretation == "moderate"

    def test_metric_to_simplified_dict(self):
        """Test serialization rounds ratio."""
        metric = ViewerDiversityMetric(
            ratio=0.333333333,
            interpretation="moderate",
            unique_viewers=10,
            total_views=30,
        )
        result = metric.to_simplified_dict()
        assert result["ratio"] == 0.333  # Rounded to 3 decimals

    def test_interpretation_values(self):
        """Test different interpretation values."""
        for interp in ["narrow", "moderate", "broad"]:
            metric = ViewerDiversityMetric(
                ratio=0.5,
                interpretation=interp,
                unique_viewers=0,
                total_views=0,
            )
            assert metric.interpretation == interp


class TestPageAnalyticsResponse:
    """Tests for the PageAnalyticsResponse model."""

    def test_response_creation(self):
        """Test creating a page analytics response."""
        response = PageAnalyticsResponse(
            page_id="123456",
            page_title="Test Page",
            period_days=30,
            metrics={
                "engagement_score": EngagementScoreMetric(
                    value=75, components={"view_score": 80}
                )
            },
        )
        assert response.page_id == "123456"
        assert response.period_days == 30

    def test_response_to_simplified_dict(self):
        """Test serialization includes nested metrics."""
        response = PageAnalyticsResponse(
            page_id="123",
            period_days=30,
            metrics={
                "staleness": StalenessMetric(
                    status="active",
                    stale_threshold_days=90,
                )
            },
            raw_data={"total_views": 100},
        )
        result = response.to_simplified_dict()
        assert result["page_id"] == "123"
        assert "staleness" in result["metrics"]
        assert result["raw_data"]["total_views"] == 100


class TestPageAnalyticsBatchResponse:
    """Tests for the PageAnalyticsBatchResponse model."""

    def test_batch_response_creation(self):
        """Test creating a batch analytics response."""
        pages = [
            PageAnalyticsResponse(page_id="1", period_days=30, metrics={}),
            PageAnalyticsResponse(page_id="2", period_days=30, metrics={}),
        ]
        response = PageAnalyticsBatchResponse(
            pages=pages,
            total_count=3,
            success_count=2,
            error_count=1,
            errors=[{"page_id": "3", "error": "Not found"}],
            period_days=30,
            metrics_calculated=["engagement_score"],
        )
        assert response.total_count == 3
        assert response.success_count == 2
        assert len(response.pages) == 2

    def test_batch_response_to_simplified_dict(self):
        """Test batch response serialization."""
        pages = [PageAnalyticsResponse(page_id="1", period_days=30, metrics={})]
        response = PageAnalyticsBatchResponse(
            pages=pages,
            total_count=1,
            success_count=1,
            error_count=0,
            period_days=30,
            metrics_calculated=["staleness"],
        )
        result = response.to_simplified_dict()
        assert result["total_count"] == 1
        assert result["metrics_calculated"] == ["staleness"]
        assert "errors" not in result  # Empty errors excluded


class TestMetricCalculators:
    """Tests for the metric calculation methods."""

    def test_calculate_engagement_score_high(self):
        """Test high engagement score calculation."""
        mixin = MagicMock()
        result = AnalyticsMixin._calculate_engagement_score(
            mixin,
            total_views=100,
            unique_viewers=20,
            days_since_last_view=0,
            period_days=30,
        )
        assert result.value > 50  # Should be reasonably high
        assert result.components["recency_score"] == 100  # Recent view

    def test_calculate_engagement_score_zero_views(self):
        """Test engagement score with no views."""
        mixin = MagicMock()
        result = AnalyticsMixin._calculate_engagement_score(
            mixin,
            total_views=0,
            unique_viewers=0,
            days_since_last_view=None,
            period_days=30,
        )
        assert result.value == 0
        assert result.components["view_score"] == 0
        assert result.components["recency_score"] == 0

    def test_calculate_staleness_active(self):
        """Test staleness calculation for active page."""
        mixin = MagicMock()
        mixin.confluence = MagicMock()
        mixin.confluence.get_page_by_id.return_value = None

        result = AnalyticsMixin._calculate_staleness(
            mixin,
            page_id="123",
            days_since_last_view=3,
        )
        assert result.status == "active"

    def test_calculate_staleness_stale(self):
        """Test staleness calculation for stale page."""
        mixin = MagicMock()
        mixin.confluence = MagicMock()
        mixin.confluence.get_page_by_id.return_value = None

        result = AnalyticsMixin._calculate_staleness(
            mixin,
            page_id="123",
            days_since_last_view=45,
        )
        assert result.status == "stale"

    def test_calculate_staleness_abandoned(self):
        """Test staleness calculation for abandoned page."""
        mixin = MagicMock()
        mixin.confluence = MagicMock()
        mixin.confluence.get_page_by_id.return_value = None

        result = AnalyticsMixin._calculate_staleness(
            mixin,
            page_id="123",
            days_since_last_view=120,
        )
        assert result.status == "abandoned"

    def test_calculate_staleness_never_viewed(self):
        """Test staleness calculation for never-viewed page."""
        mixin = MagicMock()
        mixin.confluence = MagicMock()
        mixin.confluence.get_page_by_id.return_value = None

        result = AnalyticsMixin._calculate_staleness(
            mixin,
            page_id="123",
            days_since_last_view=None,
        )
        assert result.status == "abandoned"

    def test_calculate_viewer_diversity_narrow(self):
        """Test viewer diversity calculation - narrow audience."""
        mixin = MagicMock()
        result = AnalyticsMixin._calculate_viewer_diversity(
            mixin,
            total_views=100,
            unique_viewers=10,  # 10% ratio
        )
        assert result.interpretation == "narrow"
        assert result.ratio == 0.1

    def test_calculate_viewer_diversity_moderate(self):
        """Test viewer diversity calculation - moderate audience."""
        mixin = MagicMock()
        result = AnalyticsMixin._calculate_viewer_diversity(
            mixin,
            total_views=100,
            unique_viewers=50,  # 50% ratio
        )
        assert result.interpretation == "moderate"
        assert result.ratio == 0.5

    def test_calculate_viewer_diversity_broad(self):
        """Test viewer diversity calculation - broad audience."""
        mixin = MagicMock()
        result = AnalyticsMixin._calculate_viewer_diversity(
            mixin,
            total_views=100,
            unique_viewers=80,  # 80% ratio
        )
        assert result.interpretation == "broad"
        assert result.ratio == 0.8

    def test_calculate_viewer_diversity_zero_views(self):
        """Test viewer diversity with no views."""
        mixin = MagicMock()
        result = AnalyticsMixin._calculate_viewer_diversity(
            mixin,
            total_views=0,
            unique_viewers=0,
        )
        assert result.interpretation == "narrow"
        assert result.ratio == 0.0


class TestGetPageAnalytics:
    """Tests for the get_page_analytics method."""

    def test_get_page_analytics_success(self):
        """Test successful page analytics retrieval."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.confluence = MagicMock()
        mixin.confluence.get_page_by_id.return_value = None

        # Mock get_page_views
        mixin.get_page_views = MagicMock(
            return_value=PageViewsResponse(
                page_id="123",
                page_title="Test Page",
                total_views=50,
                unique_viewers=10,
            )
        )

        with patch.object(AnalyticsConfig, "from_env") as mock_config:
            mock_config.return_value = AnalyticsConfig(
                metrics=["engagement_score", "staleness"],
                period_days=30,
            )

            result = AnalyticsMixin.get_page_analytics(
                mixin,
                page_id="123",
                include_raw_data=True,
            )

            assert result.page_id == "123"
            assert result.page_title == "Test Page"
            assert result.period_days == 30
            assert "engagement_score" in result.metrics
            assert "staleness" in result.metrics
            assert result.raw_data is not None
            assert result.raw_data["total_views"] == 50

    def test_get_page_analytics_custom_metrics(self):
        """Test analytics with custom metrics."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.confluence = MagicMock()
        mixin.confluence.get_page_by_id.return_value = None

        mixin.get_page_views = MagicMock(
            return_value=PageViewsResponse(
                page_id="123",
                total_views=100,
                unique_viewers=50,
            )
        )

        with patch.object(AnalyticsConfig, "from_env") as mock_config:
            mock_config.return_value = AnalyticsConfig()

            result = AnalyticsMixin.get_page_analytics(
                mixin,
                page_id="123",
                metrics=["viewer_diversity"],
                period_days=60,
            )

            assert result.period_days == 60
            assert "viewer_diversity" in result.metrics
            assert "engagement_score" not in result.metrics

    def test_batch_get_page_analytics_success(self):
        """Test batch analytics retrieval."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True

        def mock_get_analytics(page_id, metrics=None, period_days=None, **kwargs):
            return PageAnalyticsResponse(
                page_id=page_id,
                period_days=period_days or 30,
                metrics={
                    "engagement_score": EngagementScoreMetric(value=50, components={})
                },
            )

        mixin.get_page_analytics = mock_get_analytics

        with patch.object(AnalyticsConfig, "from_env") as mock_config:
            mock_config.return_value = AnalyticsConfig()

            result = AnalyticsMixin.batch_get_page_analytics(
                mixin,
                page_ids=["1", "2", "3"],
                metrics=["engagement_score"],
            )

            assert result.total_count == 3
            assert result.success_count == 3
            assert result.error_count == 0
            assert len(result.pages) == 3

    def test_batch_get_page_analytics_server_error(self):
        """Test batch analytics fails on Server/DC."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = False

        with pytest.raises(AnalyticsNotAvailableError):
            AnalyticsMixin.batch_get_page_analytics(
                mixin,
                page_ids=["1", "2"],
            )


class TestAvailableMetrics:
    """Tests for the available metrics list."""

    def test_available_metrics_defined(self):
        """Test that AVAILABLE_METRICS is properly defined."""
        assert "engagement_score" in AVAILABLE_METRICS
        assert "view_velocity" in AVAILABLE_METRICS
        assert "staleness" in AVAILABLE_METRICS
        assert "viewer_diversity" in AVAILABLE_METRICS
        assert len(AVAILABLE_METRICS) == 4


# =============================================================================
# Phase 5: Space Analytics Tests
# =============================================================================


class TestSpacePageSummary:
    """Tests for the SpacePageSummary model."""

    def test_model_creation(self):
        """Test creating a SpacePageSummary."""
        summary = SpacePageSummary(
            page_id="123",
            page_title="Test Page",
            total_views=100,
            unique_viewers=25,
            engagement_score=75,
            trend="increasing",
            change_percent=50.5,
        )
        assert summary.page_id == "123"
        assert summary.page_title == "Test Page"
        assert summary.engagement_score == 75
        assert summary.trend == "increasing"

    def test_to_simplified_dict(self):
        """Test serialization with optional fields."""
        summary = SpacePageSummary(
            page_id="123",
            page_title="Test Page",
            total_views=50,
            unique_viewers=10,
        )
        result = summary.to_simplified_dict()
        assert result["page_id"] == "123"
        assert result["total_views"] == 50
        assert "engagement_score" not in result  # None excluded
        assert "trend" not in result

    def test_to_simplified_dict_with_all_fields(self):
        """Test serialization with all optional fields."""
        summary = SpacePageSummary(
            page_id="456",
            page_title="Full Page",
            total_views=200,
            unique_viewers=50,
            engagement_score=85,
            trend="stable",
            change_percent=2.5,
            staleness_status="active",
            days_since_last_view=3,
        )
        result = summary.to_simplified_dict()
        assert result["engagement_score"] == 85
        assert result["trend"] == "stable"
        assert result["change_percent"] == 2.5
        assert result["staleness_status"] == "active"
        assert result["days_since_last_view"] == 3


class TestSpaceSummary:
    """Tests for the SpaceSummary model."""

    def test_model_creation(self):
        """Test creating a SpaceSummary."""
        summary = SpaceSummary(
            total_pages=50,
            pages_analyzed=45,
            total_views=1000,
            total_unique_viewers=200,
            average_views_per_page=22.22,
            average_engagement_score=65.5,
            active_pages_count=20,
            stale_pages_count=15,
            abandoned_pages_count=10,
        )
        assert summary.total_pages == 50
        assert summary.pages_analyzed == 45
        assert summary.active_pages_count == 20

    def test_to_simplified_dict(self):
        """Test serialization rounds floats."""
        summary = SpaceSummary(
            total_pages=10,
            pages_analyzed=10,
            total_views=100,
            total_unique_viewers=30,
            average_views_per_page=10.333333,
            average_engagement_score=55.555,
            active_pages_count=5,
            stale_pages_count=3,
            abandoned_pages_count=2,
        )
        result = summary.to_simplified_dict()
        assert result["average_views_per_page"] == 10.33
        assert result["average_engagement_score"] == 55.6


class TestSpaceAnalyticsResponse:
    """Tests for the SpaceAnalyticsResponse model."""

    def test_model_creation(self):
        """Test creating a SpaceAnalyticsResponse."""
        response = SpaceAnalyticsResponse(
            space_key="DEV",
            space_name="Development",
            period_days=30,
            from_date="2025-12-01",
            to_date="2025-12-30",
        )
        assert response.space_key == "DEV"
        assert response.space_name == "Development"
        assert response.period_days == 30

    def test_to_simplified_dict_minimal(self):
        """Test serialization with minimal fields."""
        response = SpaceAnalyticsResponse(
            space_key="TEST",
            period_days=30,
        )
        result = response.to_simplified_dict()
        assert result["space_key"] == "TEST"
        assert result["period_days"] == 30
        assert "space_name" not in result
        assert "summary" not in result
        assert "popular_pages" not in result

    def test_to_simplified_dict_full(self):
        """Test serialization with all fields."""
        summary = SpaceSummary(
            total_pages=10,
            pages_analyzed=10,
            total_views=100,
            total_unique_viewers=20,
            average_views_per_page=10.0,
            average_engagement_score=50.0,
            active_pages_count=5,
            stale_pages_count=3,
            abandoned_pages_count=2,
        )
        popular = [
            SpacePageSummary(
                page_id="1",
                page_title="Popular Page",
                total_views=50,
                unique_viewers=15,
            )
        ]
        response = SpaceAnalyticsResponse(
            space_key="TEST",
            space_name="Test Space",
            period_days=30,
            summary=summary,
            popular_pages=popular,
            from_date="2025-12-01",
            to_date="2025-12-30",
        )
        result = response.to_simplified_dict()
        assert result["space_name"] == "Test Space"
        assert "summary" in result
        assert result["summary"]["total_pages"] == 10
        assert len(result["popular_pages"]) == 1
        assert result["popular_pages"][0]["page_title"] == "Popular Page"


class TestGetSpaceAnalytics:
    """Tests for the get_space_analytics method."""

    def test_get_space_analytics_server_error(self):
        """Test space analytics fails on Server/DC."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = False

        with pytest.raises(AnalyticsNotAvailableError):
            AnalyticsMixin.get_space_analytics(mixin, space_key="TEST")

    def test_get_space_analytics_success(self):
        """Test successful space analytics retrieval."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.confluence = MagicMock()

        # Mock space info
        mixin.confluence.get_space.return_value = {"name": "Test Space"}

        # Mock CQL results
        mixin.confluence.cql.return_value = {
            "results": [
                {"content": {"id": "1", "title": "Page 1"}},
                {"content": {"id": "2", "title": "Page 2"}},
            ]
        }

        # Mock get_page_views
        def mock_get_page_views(page_id, from_date=None, *, include_viewers=True):
            return PageViewsResponse(
                page_id=page_id,
                page_title=f"Page {page_id}",
                total_views=50 if page_id == "1" else 10,
                unique_viewers=10 if page_id == "1" else 5,
            )

        mixin.get_page_views = mock_get_page_views

        # Mock engagement and velocity calculators
        mixin._calculate_engagement_score = MagicMock(
            return_value=EngagementScoreMetric(value=50, components={})
        )
        mixin._calculate_view_velocity = MagicMock(
            return_value=ViewVelocityMetric(
                trend="stable",
                current_period_views=50,
                previous_period_views=50,
                change_percent=0.0,
            )
        )

        with patch.object(AnalyticsConfig, "from_env") as mock_config:
            mock_config.return_value = AnalyticsConfig()

            result = AnalyticsMixin.get_space_analytics(
                mixin,
                space_key="TEST",
                limit=5,
            )

            assert result.space_key == "TEST"
            assert result.space_name == "Test Space"
            assert result.summary is not None
            assert result.summary.pages_analyzed == 2

    def test_get_space_analytics_empty_space(self):
        """Test space analytics with no pages."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.confluence = MagicMock()

        # Mock space info
        mixin.confluence.get_space.return_value = {"name": "Empty Space"}

        # Mock empty CQL results
        mixin.confluence.cql.return_value = {"results": []}

        with patch.object(AnalyticsConfig, "from_env") as mock_config:
            mock_config.return_value = AnalyticsConfig()

            result = AnalyticsMixin.get_space_analytics(
                mixin,
                space_key="EMPTY",
            )

            assert result.space_key == "EMPTY"
            assert result.summary is None  # No pages to summarize
            assert len(result.popular_pages) == 0
            assert len(result.trending_pages) == 0
            assert len(result.stale_pages) == 0

    def test_get_space_analytics_selective_includes(self):
        """Test space analytics with selective includes."""
        mixin = MagicMock()
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.confluence = MagicMock()

        mixin.confluence.get_space.return_value = {"name": "Test"}
        mixin.confluence.cql.return_value = {"results": []}

        with patch.object(AnalyticsConfig, "from_env") as mock_config:
            mock_config.return_value = AnalyticsConfig()

            result = AnalyticsMixin.get_space_analytics(
                mixin,
                space_key="TEST",
                include_summary=False,
                include_popular_pages=False,
                include_trending_pages=False,
                include_stale_pages=True,
            )

            # Should return response with only stale_pages enabled
            assert result.space_key == "TEST"
