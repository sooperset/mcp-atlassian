"""
Analytics data models for Confluence page views and engagement metrics.

This module provides Pydantic models for Confluence Analytics API responses,
including page view counts, viewer information, and batch operations.

Note: These analytics endpoints are only available on Confluence Cloud.
"""

from typing import Any

from pydantic import Field

from ..base import ApiModel


class PageViewsResponse(ApiModel):
    """
    Model representing page view analytics for a single Confluence page.

    Contains view count, viewer count, and metadata about the page.
    """

    page_id: str = Field(description="The Confluence page ID")
    page_title: str | None = Field(
        default=None, description="The page title (if available)"
    )
    total_views: int = Field(
        default=0, description="Total number of views for the page"
    )
    unique_viewers: int = Field(default=0, description="Number of unique viewers")
    from_date: str | None = Field(
        default=None, description="Start date for the analytics period (ISO format)"
    )
    to_date: str | None = Field(
        default=None, description="End date for the analytics period (ISO format)"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "PageViewsResponse":
        """Create a PageViewsResponse from API data.

        Args:
            data: Dictionary containing views and viewers data
            **kwargs: Additional context (page_id, page_title, from_date, to_date)

        Returns:
            PageViewsResponse instance
        """
        return cls(
            page_id=kwargs.get("page_id", data.get("id", "")),
            page_title=kwargs.get("page_title"),
            total_views=data.get("count", 0),
            unique_viewers=data.get("viewers", 0),
            from_date=kwargs.get("from_date"),
            to_date=kwargs.get("to_date"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "page_id": self.page_id,
            "total_views": self.total_views,
            "unique_viewers": self.unique_viewers,
        }
        if self.page_title:
            result["page_title"] = self.page_title
        if self.from_date:
            result["from_date"] = self.from_date
        if self.to_date:
            result["to_date"] = self.to_date
        return result


class PageViewsBatchResponse(ApiModel):
    """
    Model representing batch page views response for multiple pages.

    Wraps multiple PageViewsResponse objects with metadata
    about the batch operation.
    """

    pages: list[PageViewsResponse] = Field(
        default_factory=list, description="List of page view responses"
    )
    total_count: int = Field(default=0, description="Total number of pages processed")
    success_count: int = Field(
        default=0, description="Number of pages successfully processed"
    )
    error_count: int = Field(
        default=0, description="Number of pages that failed to process"
    )
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="List of errors for failed pages"
    )
    from_date: str | None = Field(
        default=None, description="Start date for the analytics period"
    )
    to_date: str | None = Field(
        default=None, description="End date for the analytics period"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "PageViewsBatchResponse":
        """Create a PageViewsBatchResponse from data."""
        pages = [
            PageViewsResponse.from_api_response(page) for page in data.get("pages", [])
        ]
        return cls(
            pages=pages,
            total_count=data.get("total_count", len(pages)),
            success_count=data.get("success_count", len(pages)),
            error_count=data.get("error_count", 0),
            errors=data.get("errors", []),
            from_date=data.get("from_date"),
            to_date=data.get("to_date"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "pages": [page.to_simplified_dict() for page in self.pages],
        }
        if self.errors:
            result["errors"] = self.errors
        if self.from_date:
            result["from_date"] = self.from_date
        if self.to_date:
            result["to_date"] = self.to_date
        return result


class AnalyticsNotAvailableError(Exception):
    """Exception raised when analytics API is not available.

    This typically happens when:
    - Using Confluence Server/Data Center (analytics is Cloud-only)
    - The user doesn't have the required permissions
    """

    pass


# =============================================================================
# Phase 4: Page Analytics Metric Models
# =============================================================================


class EngagementScoreMetric(ApiModel):
    """
    Model representing an engagement score for a Confluence page.

    The engagement score is a composite rating (0-100) based on views,
    unique viewers, and recency of activity.
    """

    value: int = Field(ge=0, le=100, description="Engagement score (0-100)")
    components: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of score components (view_score, viewer_score, recency_score)",
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "value": self.value,
            "components": self.components,
        }


class ViewVelocityMetric(ApiModel):
    """
    Model representing view velocity (trend in view activity) for a page.

    Compares current period views against previous period to determine
    if activity is increasing, decreasing, or stable.
    """

    trend: str = Field(
        description="Trend direction: 'increasing', 'decreasing', or 'stable'"
    )
    current_period_views: int = Field(
        default=0, description="Views in the current period"
    )
    previous_period_views: int = Field(
        default=0, description="Views in the previous period"
    )
    change_percent: float = Field(
        default=0.0, description="Percentage change between periods"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "trend": self.trend,
            "current_period_views": self.current_period_views,
            "previous_period_views": self.previous_period_views,
            "change_percent": round(self.change_percent, 2),
        }


class StalenessMetric(ApiModel):
    """
    Model representing content freshness for a page.

    Categorizes pages as active, stale, or abandoned based on
    days since last view and last edit.
    """

    days_since_last_view: int | None = Field(
        default=None,
        description="Days since the page was last viewed (None if never viewed)",
    )
    days_since_last_edit: int | None = Field(
        default=None, description="Days since the page was last edited"
    )
    status: str = Field(
        description="Staleness status: 'active', 'stale', or 'abandoned'"
    )
    stale_threshold_days: int = Field(
        default=90, description="Threshold in days for considering a page stale"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {
            "status": self.status,
            "stale_threshold_days": self.stale_threshold_days,
        }
        if self.days_since_last_view is not None:
            result["days_since_last_view"] = self.days_since_last_view
        if self.days_since_last_edit is not None:
            result["days_since_last_edit"] = self.days_since_last_edit
        return result


class ViewerDiversityMetric(ApiModel):
    """
    Model representing the breadth of audience for a page.

    Measures the ratio of unique viewers to total views.
    """

    ratio: float = Field(
        ge=0.0, le=1.0, description="Ratio of unique viewers to total views (0-1)"
    )
    interpretation: str = Field(
        description="Human-readable interpretation: 'narrow', 'moderate', or 'broad'"
    )
    unique_viewers: int = Field(default=0, description="Number of unique viewers")
    total_views: int = Field(default=0, description="Total number of views")

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "ratio": round(self.ratio, 3),
            "interpretation": self.interpretation,
            "unique_viewers": self.unique_viewers,
            "total_views": self.total_views,
        }


class PageAnalyticsResponse(ApiModel):
    """
    Model representing calculated analytics metrics for a single page.

    Contains computed engagement metrics based on view data.
    """

    page_id: str = Field(description="The Confluence page ID")
    page_title: str | None = Field(
        default=None, description="The page title (if available)"
    )
    period_days: int = Field(description="The analysis period in days")
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Calculated metrics (engagement_score, view_velocity, staleness, viewer_diversity)",
    )
    raw_data: dict[str, Any] | None = Field(
        default=None, description="Raw view data (if include_raw_data=True)"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "page_id": self.page_id,
            "period_days": self.period_days,
            "metrics": {},
        }
        if self.page_title:
            result["page_title"] = self.page_title

        # Convert each metric to its simplified form
        for metric_name, metric_value in self.metrics.items():
            if hasattr(metric_value, "to_simplified_dict"):
                result["metrics"][metric_name] = metric_value.to_simplified_dict()
            else:
                result["metrics"][metric_name] = metric_value

        if self.raw_data:
            result["raw_data"] = self.raw_data

        return result


class PageAnalyticsBatchResponse(ApiModel):
    """
    Model representing batch page analytics response for multiple pages.

    Wraps multiple PageAnalyticsResponse objects with metadata.
    """

    pages: list[PageAnalyticsResponse] = Field(
        default_factory=list, description="List of page analytics responses"
    )
    total_count: int = Field(default=0, description="Total number of pages processed")
    success_count: int = Field(
        default=0, description="Number of pages successfully processed"
    )
    error_count: int = Field(
        default=0, description="Number of pages that failed to process"
    )
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="List of errors for failed pages"
    )
    period_days: int = Field(description="The analysis period in days")
    metrics_calculated: list[str] = Field(
        default_factory=list, description="List of metrics that were calculated"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "period_days": self.period_days,
            "metrics_calculated": self.metrics_calculated,
            "pages": [page.to_simplified_dict() for page in self.pages],
        }
        if self.errors:
            result["errors"] = self.errors
        return result


# =============================================================================
# Phase 5: Space Analytics Models
# =============================================================================


class SpacePageSummary(ApiModel):
    """
    Model representing a page summary within space analytics.

    Used for popular_pages, trending_pages, and stale_pages lists.
    """

    page_id: str = Field(description="The Confluence page ID")
    page_title: str = Field(description="The page title")
    total_views: int = Field(default=0, description="Total views in the period")
    unique_viewers: int = Field(default=0, description="Unique viewers in the period")
    engagement_score: int | None = Field(
        default=None, description="Engagement score (0-100) if calculated"
    )
    trend: str | None = Field(
        default=None, description="View trend: 'increasing', 'decreasing', or 'stable'"
    )
    change_percent: float | None = Field(
        default=None, description="Percentage change in views from previous period"
    )
    staleness_status: str | None = Field(
        default=None, description="Staleness status: 'active', 'stale', or 'abandoned'"
    )
    days_since_last_view: int | None = Field(
        default=None, description="Days since the page was last viewed"
    )
    page_url: str | None = Field(
        default=None, description="URL to the page (if available)"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {
            "page_id": self.page_id,
            "page_title": self.page_title,
            "total_views": self.total_views,
            "unique_viewers": self.unique_viewers,
        }
        if self.engagement_score is not None:
            result["engagement_score"] = self.engagement_score
        if self.trend is not None:
            result["trend"] = self.trend
        if self.change_percent is not None:
            result["change_percent"] = round(self.change_percent, 2)
        if self.staleness_status is not None:
            result["staleness_status"] = self.staleness_status
        if self.days_since_last_view is not None:
            result["days_since_last_view"] = self.days_since_last_view
        if self.page_url is not None:
            result["page_url"] = self.page_url
        return result


class SpaceSummary(ApiModel):
    """
    Model representing aggregate statistics for a Confluence space.

    Provides overall metrics across all pages in the space.
    """

    total_pages: int = Field(default=0, description="Total number of pages in space")
    pages_analyzed: int = Field(
        default=0, description="Number of pages included in analytics"
    )
    total_views: int = Field(
        default=0, description="Total views across all analyzed pages"
    )
    total_unique_viewers: int = Field(
        default=0, description="Total unique viewers across all analyzed pages"
    )
    average_views_per_page: float = Field(
        default=0.0, description="Average views per page"
    )
    average_engagement_score: float = Field(
        default=0.0, description="Average engagement score across pages"
    )
    active_pages_count: int = Field(
        default=0, description="Number of active pages (viewed recently)"
    )
    stale_pages_count: int = Field(default=0, description="Number of stale pages")
    abandoned_pages_count: int = Field(
        default=0, description="Number of abandoned pages"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "total_pages": self.total_pages,
            "pages_analyzed": self.pages_analyzed,
            "total_views": self.total_views,
            "total_unique_viewers": self.total_unique_viewers,
            "average_views_per_page": round(self.average_views_per_page, 2),
            "average_engagement_score": round(self.average_engagement_score, 1),
            "active_pages_count": self.active_pages_count,
            "stale_pages_count": self.stale_pages_count,
            "abandoned_pages_count": self.abandoned_pages_count,
        }


class SpaceAnalyticsResponse(ApiModel):
    """
    Model representing complete analytics for a Confluence space.

    Includes space summary, popular pages, trending pages, and stale pages.
    """

    space_key: str = Field(description="The Confluence space key")
    space_name: str | None = Field(
        default=None, description="The space name (if available)"
    )
    period_days: int = Field(description="The analysis period in days")
    summary: SpaceSummary | None = Field(
        default=None, description="Aggregate space statistics"
    )
    popular_pages: list[SpacePageSummary] = Field(
        default_factory=list, description="Top pages by view count"
    )
    trending_pages: list[SpacePageSummary] = Field(
        default_factory=list, description="Pages with increasing view velocity"
    )
    stale_pages: list[SpacePageSummary] = Field(
        default_factory=list, description="Pages that haven't been viewed recently"
    )
    from_date: str | None = Field(
        default=None, description="Start date for the analytics period"
    )
    to_date: str | None = Field(
        default=None, description="End date for the analytics period"
    )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "space_key": self.space_key,
            "period_days": self.period_days,
        }
        if self.space_name:
            result["space_name"] = self.space_name
        if self.summary:
            result["summary"] = self.summary.to_simplified_dict()
        if self.popular_pages:
            result["popular_pages"] = [
                p.to_simplified_dict() for p in self.popular_pages
            ]
        if self.trending_pages:
            result["trending_pages"] = [
                p.to_simplified_dict() for p in self.trending_pages
            ]
        if self.stale_pages:
            result["stale_pages"] = [p.to_simplified_dict() for p in self.stale_pages]
        if self.from_date:
            result["from_date"] = self.from_date
        if self.to_date:
            result["to_date"] = self.to_date
        return result
