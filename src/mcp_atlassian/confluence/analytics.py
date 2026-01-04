"""Module for Confluence analytics operations.

This module provides analytics functionality for Confluence pages,
including view counts, viewer information, and calculated engagement metrics.

Note: The Confluence Analytics API is only available on Cloud instances.
Server/Data Center deployments do not support this feature.
"""

import logging
from datetime import datetime, timedelta, timezone

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from ..models.confluence import (
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
from .client import ConfluenceClient
from .config import AnalyticsConfig
from .v2_adapter import ConfluenceV2Adapter

logger = logging.getLogger("mcp-atlassian")


# Available metrics for page analytics
AVAILABLE_METRICS = [
    "engagement_score",
    "view_velocity",
    "staleness",
    "viewer_diversity",
]


class AnalyticsMixin(ConfluenceClient):
    """Mixin for Confluence analytics operations.

    Provides methods to retrieve page view statistics and viewer information.
    These features are only available on Confluence Cloud.
    """

    @property
    def _analytics_adapter(self) -> ConfluenceV2Adapter:
        """Get the v2 adapter for analytics API calls.

        The analytics API uses the same base URL structure as the v2 API
        but is accessed via v1 endpoints (/rest/api/analytics/...).

        Returns:
            ConfluenceV2Adapter instance

        Raises:
            AnalyticsNotAvailableError: If not on Confluence Cloud
        """
        if not self.config.is_cloud:
            raise AnalyticsNotAvailableError(
                "Confluence Analytics API is only available on Cloud instances. "
                "Server/Data Center deployments do not support this feature."
            )

        return ConfluenceV2Adapter(
            session=self.confluence._session, base_url=self.confluence.url
        )

    def get_page_views(
        self,
        page_id: str,
        from_date: str | None = None,
        *,
        include_viewers: bool = True,
    ) -> PageViewsResponse:
        """Get view statistics for a Confluence page.

        Retrieves the total number of views and optionally the number of
        unique viewers for a specific page.

        Args:
            page_id: The ID of the page to get views for
            from_date: Optional start date (ISO format: YYYY-MM-DD)
            include_viewers: Whether to also fetch unique viewer count (default: True)

        Returns:
            PageViewsResponse containing view and viewer counts

        Raises:
            AnalyticsNotAvailableError: If analytics API is not available (Server/DC)
            MCPAtlassianAuthenticationError: If authentication fails (401/403)
            ValueError: If the API call fails for other reasons
        """
        try:
            adapter = self._analytics_adapter

            # Get view count
            views_data = adapter.get_content_views(page_id, from_date=from_date)
            total_views = views_data.get("count", 0)

            # Get viewer count if requested
            unique_viewers = 0
            if include_viewers:
                viewers_data = adapter.get_content_viewers(page_id, from_date=from_date)
                unique_viewers = viewers_data.get("count", 0)

            # Try to get page title
            page_title = None
            try:
                page = self.confluence.get_page_by_id(page_id)
                if page:
                    page_title = page.get("title")
            except (ValueError, KeyError, AttributeError) as e:
                logger.debug(f"Could not fetch page title for {page_id}: {e}")

            # Calculate to_date as today if not provided
            to_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

            return PageViewsResponse(
                page_id=page_id,
                page_title=page_title,
                total_views=total_views,
                unique_viewers=unique_viewers,
                from_date=from_date,
                to_date=to_date,
            )

        except AnalyticsNotAvailableError:
            raise
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Confluence Analytics API "
                    f"({http_err.response.status_code}). "
                    "Token may be expired or invalid, or you may not have "
                    "permission to access analytics."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            raise
        except Exception as e:
            logger.error(f"Error getting page views for {page_id}: {e}")
            raise

    def batch_get_page_views(
        self,
        page_ids: list[str],
        from_date: str | None = None,
        *,
        include_viewers: bool = True,
    ) -> PageViewsBatchResponse:
        """Get view statistics for multiple Confluence pages.

        Retrieves analytics data for a batch of pages. Errors for individual
        pages are captured but don't stop processing of other pages.

        Args:
            page_ids: List of page IDs to get views for
            from_date: Optional start date (ISO format: YYYY-MM-DD)
            include_viewers: Whether to also fetch unique viewer count (default: True)

        Returns:
            PageViewsBatchResponse containing results and any errors

        Raises:
            AnalyticsNotAvailableError: If analytics API is not available (Server/DC)
        """
        # Check Cloud availability once before processing
        if not self.config.is_cloud:
            raise AnalyticsNotAvailableError(
                "Confluence Analytics API is only available on Cloud instances. "
                "Server/Data Center deployments do not support this feature."
            )

        pages: list[PageViewsResponse] = []
        errors: list[dict[str, str]] = []
        to_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        for page_id in page_ids:
            try:
                result = self.get_page_views(
                    page_id=page_id,
                    from_date=from_date,
                    include_viewers=include_viewers,
                )
                pages.append(result)
            except (ValueError, AnalyticsNotAvailableError) as e:
                errors.append(
                    {
                        "page_id": page_id,
                        "error": str(e),
                    }
                )
                logger.warning(f"Failed to get views for page {page_id}: {e}")

        return PageViewsBatchResponse(
            pages=pages,
            total_count=len(page_ids),
            success_count=len(pages),
            error_count=len(errors),
            errors=errors,
            from_date=from_date,
            to_date=to_date,
        )

    # =========================================================================
    # Phase 4: Page Analytics (Calculated Metrics)
    # =========================================================================

    def _calculate_engagement_score(
        self,
        total_views: int,
        unique_viewers: int,
        days_since_last_view: int | None,
        period_days: int,
    ) -> EngagementScoreMetric:
        """Calculate engagement score for a page.

        The engagement score (0-100) is calculated as:
        - view_score (40%): views vs expected baseline
        - viewer_score (30%): unique viewers vs expected
        - recency_score (30%): decays with time since last view

        Args:
            total_views: Total view count in the period
            unique_viewers: Number of unique viewers
            days_since_last_view: Days since last view (None if never viewed)
            period_days: Analysis period in days

        Returns:
            EngagementScoreMetric with value and component breakdown
        """
        # Expected baselines based on period
        expected_views = max(1, period_days * 2)
        expected_viewers = max(1, period_days * 0.5)

        # Calculate component scores (0-100 each)
        view_score = min(100, int((total_views / expected_views) * 100))
        viewer_score = min(100, int((unique_viewers / expected_viewers) * 100))

        # Recency score decays 5 points per day without views
        if days_since_last_view is None:
            recency_score = 0  # Never viewed
        else:
            recency_score = max(0, 100 - (days_since_last_view * 5))

        # Weighted average
        engagement = int(
            (view_score * 0.4) + (viewer_score * 0.3) + (recency_score * 0.3)
        )

        return EngagementScoreMetric(
            value=engagement,
            components={
                "view_score": view_score,
                "viewer_score": viewer_score,
                "recency_score": recency_score,
            },
        )

    def _calculate_view_velocity(
        self,
        page_id: str,
        period_days: int,
    ) -> ViewVelocityMetric:
        """Calculate view velocity (trend) for a page.

        Compares current period views against previous period.

        Args:
            page_id: The page ID
            period_days: Analysis period in days

        Returns:
            ViewVelocityMetric with trend direction and change percentage
        """
        now = datetime.now(tz=timezone.utc)
        current_start = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
        previous_start = (now - timedelta(days=period_days * 2)).strftime("%Y-%m-%d")
        previous_end = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")

        # Get current period views
        try:
            adapter = self._analytics_adapter
            current_data = adapter.get_content_views(page_id, from_date=current_start)
            current_views = current_data.get("count", 0)
        except Exception as e:
            logger.debug(f"Error getting current period views for {page_id}: {e}")
            current_views = 0

        # Get previous period views
        # Note: API only supports from_date, so we get views from previous_start to now
        # and estimate previous period by subtracting current period
        try:
            adapter = self._analytics_adapter
            previous_data = adapter.get_content_views(page_id, from_date=previous_start)
            total_from_previous = previous_data.get("count", 0)
            # Estimate previous period views by subtracting current period
            previous_views = max(0, total_from_previous - current_views)
        except Exception as e:
            logger.debug(f"Error getting previous period views for {page_id}: {e}")
            previous_views = 0

        # Calculate change percentage
        if previous_views == 0:
            if current_views > 0:
                change_percent = 100.0  # New activity
                trend = "increasing"
            else:
                change_percent = 0.0
                trend = "stable"
        else:
            change_percent = ((current_views - previous_views) / previous_views) * 100

            # Determine trend (threshold: 10% change)
            if change_percent > 10:
                trend = "increasing"
            elif change_percent < -10:
                trend = "decreasing"
            else:
                trend = "stable"

        return ViewVelocityMetric(
            trend=trend,
            current_period_views=current_views,
            previous_period_views=previous_views,
            change_percent=change_percent,
        )

    def _calculate_staleness(
        self,
        page_id: str,
        days_since_last_view: int | None,
        stale_threshold_days: int = 90,
    ) -> StalenessMetric:
        """Calculate staleness metric for a page.

        Categorizes pages as active, stale, or abandoned.

        Args:
            page_id: The page ID
            days_since_last_view: Days since last view (None if never viewed)
            stale_threshold_days: Threshold for stale status (default: 90)

        Returns:
            StalenessMetric with status and days information
        """
        # Get days since last edit from page info
        days_since_last_edit = None
        try:
            page = self.confluence.get_page_by_id(page_id)
            if page:
                # Get last modified date
                last_modified = page.get("version", {}).get("when")
                if last_modified:
                    # Parse ISO format date
                    if isinstance(last_modified, str):
                        # Handle various ISO formats
                        try:
                            last_mod_dt = datetime.fromisoformat(
                                last_modified.replace("Z", "+00:00")
                            )
                            now = datetime.now(tz=timezone.utc)
                            days_since_last_edit = (now - last_mod_dt).days
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.debug(f"Could not get edit date for page {page_id}: {e}")

        # Determine staleness status
        # Active: viewed within last 7 days
        # Stale: not viewed in 7-90 days (or threshold)
        # Abandoned: not viewed in 90+ days (or threshold)
        if days_since_last_view is None:
            status = "abandoned"  # Never viewed
        elif days_since_last_view <= 7:
            status = "active"
        elif days_since_last_view <= stale_threshold_days:
            status = "stale"
        else:
            status = "abandoned"

        return StalenessMetric(
            days_since_last_view=days_since_last_view,
            days_since_last_edit=days_since_last_edit,
            status=status,
            stale_threshold_days=stale_threshold_days,
        )

    def _calculate_viewer_diversity(
        self,
        total_views: int,
        unique_viewers: int,
    ) -> ViewerDiversityMetric:
        """Calculate viewer diversity for a page.

        Measures the ratio of unique viewers to total views.

        Args:
            total_views: Total view count
            unique_viewers: Number of unique viewers

        Returns:
            ViewerDiversityMetric with ratio and interpretation
        """
        if total_views == 0:
            ratio = 0.0
            interpretation = "narrow"  # No views means no diversity
        else:
            ratio = unique_viewers / total_views

            # Interpretation thresholds:
            # narrow: < 0.3 (same people viewing repeatedly)
            # moderate: 0.3 - 0.7
            # broad: > 0.7 (many unique viewers)
            if ratio < 0.3:
                interpretation = "narrow"
            elif ratio < 0.7:
                interpretation = "moderate"
            else:
                interpretation = "broad"

        return ViewerDiversityMetric(
            ratio=ratio,
            interpretation=interpretation,
            unique_viewers=unique_viewers,
            total_views=total_views,
        )

    def get_page_analytics(
        self,
        page_id: str,
        metrics: list[str] | None = None,
        period_days: int | None = None,
        *,
        include_raw_data: bool = False,
    ) -> PageAnalyticsResponse:
        """Get calculated engagement metrics for a Confluence page.

        Fetches raw view data and calculates engagement metrics based on it.

        Args:
            page_id: The ID of the page to analyze
            metrics: List of metrics to calculate. If None, uses config defaults.
                Available: engagement_score, view_velocity, staleness, viewer_diversity
            period_days: Analysis period in days. If None, uses config default (30).
            include_raw_data: Whether to include raw view data in response.

        Returns:
            PageAnalyticsResponse with calculated metrics

        Raises:
            AnalyticsNotAvailableError: If analytics API is not available (Server/DC)
        """
        # Load config defaults
        config = AnalyticsConfig.from_env()

        if metrics is None:
            metrics = config.metrics
        if period_days is None:
            period_days = config.period_days

        # Validate metrics
        valid_metrics = [m for m in metrics if m in AVAILABLE_METRICS]
        if not valid_metrics:
            valid_metrics = ["engagement_score", "staleness"]

        # Get raw view data
        from_date = (
            datetime.now(tz=timezone.utc) - timedelta(days=period_days)
        ).strftime("%Y-%m-%d")

        try:
            views_response = self.get_page_views(
                page_id=page_id,
                from_date=from_date,
                include_viewers=True,
            )
        except AnalyticsNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"Error getting view data for {page_id}: {e}")
            raise

        total_views = views_response.total_views
        unique_viewers = views_response.unique_viewers
        page_title = views_response.page_title

        # Calculate days since last view (approximate based on view count)
        # If there are views, assume last view was recent
        # This is a simplified approach - ideally we'd have the actual last view date
        if total_views > 0:
            # Rough estimate: if views exist in period, assume recent activity
            days_since_last_view = max(0, period_days // (total_views + 1))
        else:
            days_since_last_view = None  # No views in period

        # Calculate requested metrics
        calculated_metrics: dict = {}

        if "engagement_score" in valid_metrics:
            calculated_metrics["engagement_score"] = self._calculate_engagement_score(
                total_views=total_views,
                unique_viewers=unique_viewers,
                days_since_last_view=days_since_last_view,
                period_days=period_days,
            )

        if "view_velocity" in valid_metrics:
            calculated_metrics["view_velocity"] = self._calculate_view_velocity(
                page_id=page_id,
                period_days=period_days,
            )

        if "staleness" in valid_metrics:
            calculated_metrics["staleness"] = self._calculate_staleness(
                page_id=page_id,
                days_since_last_view=days_since_last_view,
            )

        if "viewer_diversity" in valid_metrics:
            calculated_metrics["viewer_diversity"] = self._calculate_viewer_diversity(
                total_views=total_views,
                unique_viewers=unique_viewers,
            )

        # Prepare raw data if requested
        raw_data = None
        if include_raw_data:
            raw_data = {
                "total_views": total_views,
                "unique_viewers": unique_viewers,
                "from_date": from_date,
                "to_date": views_response.to_date,
            }

        return PageAnalyticsResponse(
            page_id=page_id,
            page_title=page_title,
            period_days=period_days,
            metrics=calculated_metrics,
            raw_data=raw_data,
        )

    def batch_get_page_analytics(
        self,
        page_ids: list[str],
        metrics: list[str] | None = None,
        period_days: int | None = None,
        *,
        include_raw_data: bool = False,
    ) -> PageAnalyticsBatchResponse:
        """Get calculated engagement metrics for multiple Confluence pages.

        Args:
            page_ids: List of page IDs to analyze
            metrics: List of metrics to calculate. If None, uses config defaults.
            period_days: Analysis period in days. If None, uses config default.
            include_raw_data: Whether to include raw view data in response.

        Returns:
            PageAnalyticsBatchResponse with results and any errors

        Raises:
            AnalyticsNotAvailableError: If analytics API is not available (Server/DC)
        """
        # Check Cloud availability once before processing
        if not self.config.is_cloud:
            raise AnalyticsNotAvailableError(
                "Confluence Analytics API is only available on Cloud instances. "
                "Server/Data Center deployments do not support this feature."
            )

        # Load config defaults
        config = AnalyticsConfig.from_env()
        if metrics is None:
            metrics = config.metrics
        if period_days is None:
            period_days = config.period_days

        pages: list[PageAnalyticsResponse] = []
        errors: list[dict[str, str]] = []

        for page_id in page_ids:
            try:
                result = self.get_page_analytics(
                    page_id=page_id,
                    metrics=metrics,
                    period_days=period_days,
                    include_raw_data=include_raw_data,
                )
                pages.append(result)
            except Exception as e:
                errors.append(
                    {
                        "page_id": page_id,
                        "error": str(e),
                    }
                )
                logger.warning(f"Failed to get analytics for page {page_id}: {e}")

        return PageAnalyticsBatchResponse(
            pages=pages,
            total_count=len(page_ids),
            success_count=len(pages),
            error_count=len(errors),
            errors=errors,
            period_days=period_days,
            metrics_calculated=metrics,
        )

    # =========================================================================
    # Phase 5: Space Analytics
    # =========================================================================

    def get_space_analytics(
        self,
        space_key: str,
        period_days: int | None = None,
        limit: int = 10,
        stale_threshold_days: int = 90,
        *,
        include_summary: bool = True,
        include_popular_pages: bool = True,
        include_trending_pages: bool = True,
        include_stale_pages: bool = True,
    ) -> SpaceAnalyticsResponse:
        """Get aggregated analytics for a Confluence space.

        Analyzes all pages in a space to provide insights on popular content,
        trending pages, and stale content that may need attention.

        Args:
            space_key: The key of the space to analyze (e.g., 'DEV', 'TEAM')
            period_days: Analysis period in days. If None, uses config default (30).
            limit: Maximum number of pages to return in each category (default: 10)
            stale_threshold_days: Days without views to consider a page stale (default: 90)
            include_summary: Whether to include space-level summary statistics
            include_popular_pages: Whether to include top pages by view count
            include_trending_pages: Whether to include pages with increasing views
            include_stale_pages: Whether to include pages that haven't been viewed

        Returns:
            SpaceAnalyticsResponse with space insights

        Raises:
            AnalyticsNotAvailableError: If analytics API is not available (Server/DC)
        """
        # Check Cloud availability
        if not self.config.is_cloud:
            raise AnalyticsNotAvailableError(
                "Confluence Analytics API is only available on Cloud instances. "
                "Server/Data Center deployments do not support this feature."
            )

        # Load config defaults
        config = AnalyticsConfig.from_env()
        if period_days is None:
            period_days = config.period_days

        # Calculate date range
        now = datetime.now(tz=timezone.utc)
        from_date = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        # Get space info
        space_name = None
        try:
            space = self.confluence.get_space(space_key, expand="description.plain")
            if space:
                space_name = space.get("name")
        except Exception as e:
            logger.debug(f"Could not fetch space info for {space_key}: {e}")

        # Get all pages in the space
        try:
            # Use CQL to find all pages in the space
            cql = f'space="{space_key}" AND type=page'
            pages_result = self.confluence.cql(cql, limit=500, expand="version")
            all_pages = pages_result.get("results", []) if pages_result else []
        except Exception as e:
            logger.error(f"Error fetching pages for space {space_key}: {e}")
            all_pages = []

        total_pages = len(all_pages)

        # Collect analytics for each page
        page_analytics: list[dict] = []
        for page in all_pages:
            page_id = page.get("content", {}).get("id") or page.get("id")
            page_title = page.get("content", {}).get("title") or page.get("title")

            if not page_id:
                continue

            try:
                # Get view data
                views_response = self.get_page_views(
                    page_id=str(page_id),
                    from_date=from_date,
                    include_viewers=True,
                )

                # Calculate engagement score
                total_views = views_response.total_views
                unique_viewers = views_response.unique_viewers

                # Estimate days since last view
                if total_views > 0:
                    days_since_last_view = max(0, period_days // (total_views + 1))
                else:
                    days_since_last_view = period_days  # No views = stale

                engagement = self._calculate_engagement_score(
                    total_views=total_views,
                    unique_viewers=unique_viewers,
                    days_since_last_view=days_since_last_view,
                    period_days=period_days,
                )

                # Calculate velocity
                velocity = self._calculate_view_velocity(
                    page_id=str(page_id),
                    period_days=period_days,
                )

                # Determine staleness
                if days_since_last_view <= 7:
                    staleness_status = "active"
                elif days_since_last_view <= stale_threshold_days:
                    staleness_status = "stale"
                else:
                    staleness_status = "abandoned"

                page_analytics.append(
                    {
                        "page_id": str(page_id),
                        "page_title": page_title or "Untitled",
                        "total_views": total_views,
                        "unique_viewers": unique_viewers,
                        "engagement_score": engagement.value,
                        "trend": velocity.trend,
                        "change_percent": velocity.change_percent,
                        "staleness_status": staleness_status,
                        "days_since_last_view": days_since_last_view,
                    }
                )

            except Exception as e:
                logger.debug(f"Could not get analytics for page {page_id}: {e}")
                continue

        # Build response
        popular_pages: list[SpacePageSummary] = []
        trending_pages: list[SpacePageSummary] = []
        stale_pages: list[SpacePageSummary] = []
        summary: SpaceSummary | None = None

        # Calculate summary if requested
        if include_summary and page_analytics:
            total_views = sum(p["total_views"] for p in page_analytics)
            total_unique_viewers = sum(p["unique_viewers"] for p in page_analytics)
            avg_views = total_views / len(page_analytics) if page_analytics else 0
            avg_engagement = (
                sum(p["engagement_score"] for p in page_analytics) / len(page_analytics)
                if page_analytics
                else 0
            )
            active_count = sum(
                1 for p in page_analytics if p["staleness_status"] == "active"
            )
            stale_count = sum(
                1 for p in page_analytics if p["staleness_status"] == "stale"
            )
            abandoned_count = sum(
                1 for p in page_analytics if p["staleness_status"] == "abandoned"
            )

            summary = SpaceSummary(
                total_pages=total_pages,
                pages_analyzed=len(page_analytics),
                total_views=total_views,
                total_unique_viewers=total_unique_viewers,
                average_views_per_page=avg_views,
                average_engagement_score=avg_engagement,
                active_pages_count=active_count,
                stale_pages_count=stale_count,
                abandoned_pages_count=abandoned_count,
            )

        # Get popular pages (sorted by views)
        if include_popular_pages:
            sorted_by_views = sorted(
                page_analytics, key=lambda x: x["total_views"], reverse=True
            )
            for p in sorted_by_views[:limit]:
                popular_pages.append(
                    SpacePageSummary(
                        page_id=p["page_id"],
                        page_title=p["page_title"],
                        total_views=p["total_views"],
                        unique_viewers=p["unique_viewers"],
                        engagement_score=p["engagement_score"],
                    )
                )

        # Get trending pages (increasing velocity)
        if include_trending_pages:
            trending = [p for p in page_analytics if p["trend"] == "increasing"]
            sorted_trending = sorted(
                trending, key=lambda x: x["change_percent"], reverse=True
            )
            for p in sorted_trending[:limit]:
                trending_pages.append(
                    SpacePageSummary(
                        page_id=p["page_id"],
                        page_title=p["page_title"],
                        total_views=p["total_views"],
                        unique_viewers=p["unique_viewers"],
                        trend=p["trend"],
                        change_percent=p["change_percent"],
                    )
                )

        # Get stale pages
        if include_stale_pages:
            stale = [
                p
                for p in page_analytics
                if p["staleness_status"] in ["stale", "abandoned"]
            ]
            sorted_stale = sorted(
                stale, key=lambda x: x["days_since_last_view"], reverse=True
            )
            for p in sorted_stale[:limit]:
                stale_pages.append(
                    SpacePageSummary(
                        page_id=p["page_id"],
                        page_title=p["page_title"],
                        total_views=p["total_views"],
                        unique_viewers=p["unique_viewers"],
                        staleness_status=p["staleness_status"],
                        days_since_last_view=p["days_since_last_view"],
                    )
                )

        return SpaceAnalyticsResponse(
            space_key=space_key,
            space_name=space_name,
            period_days=period_days,
            summary=summary,
            popular_pages=popular_pages,
            trending_pages=trending_pages,
            stale_pages=stale_pages,
            from_date=from_date,
            to_date=to_date,
        )
