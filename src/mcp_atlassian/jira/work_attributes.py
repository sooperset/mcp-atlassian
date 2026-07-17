"""Mixin for Tempo Core Work Attributes operations."""

import logging

from ..models.jira import JiraWorkAttribute, JiraWorkAttributeValue
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class WorkAttributeMixin(JiraClient):
    """Mixin for Tempo Core Work Attributes operations.

    This mixin provides methods for interacting with the Tempo Core
    Work Attributes API, which allows teams to categorize and tag
    worklog entries with custom attributes.

    Note: These endpoints are only available for Jira Server/Data Center
    with the Tempo Timesheets plugin installed.
    """

    def _ensure_server_mode(self) -> None:
        """Ensure Tempo Core endpoints are used only on Jira Server/DC."""
        if self.config.is_cloud:
            raise NotImplementedError(
                "Tempo Core Work Attribute endpoints are only available on "
                "Jira Server/Data Center."
            )

    def get_work_attributes(self) -> list[JiraWorkAttribute]:
        """Get all Tempo Core work attribute definitions.

        Returns:
            Configured work attributes, or an empty list when the Tempo API
            returns an unusable response.

        Raises:
            NotImplementedError: If connected to Jira Cloud.
        """
        self._ensure_server_mode()
        try:
            url = "rest/tempo-core/1/work-attribute"
            result = self.jira.get(url)  # type: ignore[attr-defined]

            if not isinstance(result, list):
                logger.warning(
                    "Unexpected response type from work attributes API: %s",
                    type(result),
                )
                return []

            return [
                JiraWorkAttribute.from_api_response(attr)
                for attr in result
                if isinstance(attr, dict)
            ]
        except Exception as e:
            logger.warning("Error fetching work attributes: %s", str(e))
            return []

    def get_work_attribute_values(
        self,
        attribute_id: int,
    ) -> list[JiraWorkAttributeValue]:
        """
        Get all values for a specific Tempo Work Attribute.

        Args:
            attribute_id: The ID of the work attribute

        Returns:
            List of JiraWorkAttributeValue models

        Raises:
            ValueError: If attribute_id is not greater than zero.
            NotImplementedError: If connected to Jira Cloud.
        """
        if attribute_id <= 0:
            raise ValueError("attribute_id must be greater than zero")

        self._ensure_server_mode()
        try:
            url = f"rest/tempo-core/1/work-attribute/{attribute_id}/static-list-value"
            result = self.jira.get(url)  # type: ignore[attr-defined]

            if not isinstance(result, list):
                logger.warning(
                    "Unexpected response type from work attribute values API: %s",
                    type(result),
                )
                return []

            return [
                JiraWorkAttributeValue.from_api_response(value)
                for value in result
                if isinstance(value, dict)
            ]
        except Exception as e:
            logger.warning(
                "Error fetching work attribute values for id=%s: %s",
                attribute_id,
                str(e),
            )
            return []
