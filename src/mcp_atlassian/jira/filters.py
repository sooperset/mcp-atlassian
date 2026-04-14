"""Module for Jira filter operations."""

import logging

from requests.exceptions import HTTPError

from ..models.jira.filter import JiraFilter
from ..utils.decorators import handle_auth_errors
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class FiltersMixin(JiraClient):
    """Mixin for Jira saved filter operations."""

    @handle_auth_errors("Jira API")
    def get_my_filters(self) -> list[JiraFilter]:
        """
        Get all filters owned by the current user.

        Returns:
            List of JiraFilter model instances.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If there is an error retrieving filters.
        """
        try:
            response = self.jira.get("rest/api/2/filter/my")

            if not isinstance(response, list):
                msg = f"Unexpected response type from filter/my: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            return [JiraFilter.from_api_response(f) for f in response]

        except HTTPError:
            raise  # let decorator handle auth errors
        except TypeError:
            raise
        except Exception as e:
            error_msg = f"Error getting my filters: {e!s}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    @handle_auth_errors("Jira API")
    def get_favourite_filters(self) -> list[JiraFilter]:
        """
        Get all favourite/starred filters for the current user.

        Returns:
            List of JiraFilter model instances.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If there is an error retrieving filters.
        """
        try:
            response = self.jira.get("rest/api/2/filter/favourite")

            if not isinstance(response, list):
                msg = (
                    f"Unexpected response type from filter/favourite: {type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            return [JiraFilter.from_api_response(f) for f in response]

        except HTTPError:
            raise  # let decorator handle auth errors
        except TypeError:
            raise
        except Exception as e:
            error_msg = f"Error getting favourite filters: {e!s}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    @handle_auth_errors("Jira API")
    def get_filter_by_id(self, filter_id: str) -> JiraFilter:
        """
        Get a specific filter by its ID.

        Args:
            filter_id: The ID of the filter.

        Returns:
            JiraFilter model instance.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            ValueError: If the filter is not found.
            Exception: If there is an error retrieving the filter.
        """
        try:
            response = self.jira.get(f"rest/api/2/filter/{filter_id}")

            if not isinstance(response, dict):
                msg = (
                    "Unexpected response type from"
                    f" filter/{filter_id}: {type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            return JiraFilter.from_api_response(response)

        except HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                error_msg = f"Filter with ID '{filter_id}' not found."
                raise ValueError(error_msg) from e
            raise  # let decorator handle auth errors
        except TypeError:
            raise
        except Exception as e:
            error_msg = f"Error getting filter {filter_id}: {e!s}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
