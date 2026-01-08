"""Analytics mixin for Confluence page view statistics.

This module provides functionality to retrieve page view statistics
from Confluence Cloud using the Analytics API.

Note: The Analytics API is only available for Confluence Cloud.
Server/Data Center instances do not support this API.
"""

import logging
from datetime import datetime
from typing import Any

from requests.exceptions import HTTPError

from ..models.confluence.analytics import PageViews, PageViewsBatchResponse

logger = logging.getLogger("mcp-atlassian")


class AnalyticsMixin:
    """Mixin providing Confluence page view analytics functionality.

    This mixin requires the class to have:
    - self.confluence: Atlassian Confluence client
    - self.config: ConfluenceConfig instance
    - self.v2_adapter: Optional ConfluenceV2Adapter for OAuth
    """

    # Type hints for attributes expected from the base class
    confluence: Any
    config: Any
    v2_adapter: Any

    def get_page_views(
        self,
        page_id: str,
        include_title: bool = True,
    ) -> PageViews:
        """Get view statistics for a Confluence page.

        Note: This API is only available for Confluence Cloud.

        Args:
            page_id: The ID of the page
            include_title: Whether to fetch and include the page title

        Returns:
            PageViews with view statistics

        Raises:
            ValueError: If the page is not found or API fails
            HTTPError: If authentication fails (401/403 are propagated)
        """
        if not self.config.is_cloud:
            raise ValueError(
                "Page view analytics is only available for Confluence Cloud. "
                "Server/Data Center instances do not support the Analytics API."
            )

        # Get page title if requested
        page_title = None
        if include_title:
            try:
                page_info = self.confluence.get_page_by_id(page_id, expand="title")
                page_title = page_info.get("title")
            except Exception as e:
                logger.warning(f"Could not fetch title for page {page_id}: {e}")

        # Get view statistics using v2 adapter or direct API
        try:
            if hasattr(self, "v2_adapter") and self.v2_adapter:
                views_data = self.v2_adapter.get_page_views(page_id)
            else:
                views_data = self._get_page_views_direct(page_id)

            # Parse the response
            total_views = views_data.get("count", 0)

            # Parse last viewed timestamp if available
            last_viewed = None
            last_seen_str = views_data.get("lastSeen")
            if last_seen_str:
                try:
                    # Try parsing ISO format timestamp
                    last_viewed = datetime.fromisoformat(
                        last_seen_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            return PageViews(
                page_id=page_id,
                page_title=page_title,
                total_views=total_views,
                last_viewed=last_viewed,
            )

        except HTTPError as e:
            # Propagate auth errors
            if e.response is not None and e.response.status_code in [401, 403]:
                raise
            logger.warning(f"Failed to get views for page {page_id}: {e}")
            # Return zero views on error (non-auth)
            return PageViews(
                page_id=page_id,
                page_title=page_title,
                total_views=0,
            )
        except Exception as e:
            logger.warning(f"Unexpected error getting views for page {page_id}: {e}")
            return PageViews(
                page_id=page_id,
                page_title=page_title,
                total_views=0,
            )

    def _get_page_views_direct(
        self,
        page_id: str,
    ) -> dict:
        """Get page views using direct API call.

        Args:
            page_id: The ID of the page

        Returns:
            Dictionary with view statistics

        Raises:
            HTTPError: If the API request fails
        """
        url = f"{self.confluence.url}/wiki/rest/api/analytics/content/{page_id}/views"
        response = self.confluence._session.get(url)
        response.raise_for_status()
        return response.json()

    def batch_get_page_views(
        self,
        page_ids: list[str],
        include_title: bool = True,
    ) -> PageViewsBatchResponse:
        """Get view statistics for multiple pages.

        Args:
            page_ids: List of page IDs
            include_title: Whether to fetch and include page titles

        Returns:
            PageViewsBatchResponse with results for all pages
        """
        pages: list[PageViews] = []
        errors: list[dict[str, str]] = []

        for page_id in page_ids:
            try:
                page_views = self.get_page_views(page_id, include_title=include_title)
                pages.append(page_views)
            except HTTPError as e:
                # Propagate auth errors
                if e.response is not None and e.response.status_code in [401, 403]:
                    raise
                errors.append({"page_id": page_id, "error": str(e)})
            except Exception as e:
                errors.append({"page_id": page_id, "error": str(e)})

        return PageViewsBatchResponse(
            pages=pages,
            total_count=len(page_ids),
            success_count=len(pages),
            error_count=len(errors),
            errors=errors,
        )
