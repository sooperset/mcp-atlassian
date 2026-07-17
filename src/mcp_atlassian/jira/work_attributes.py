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

    def get_work_attributes(self) -> list[JiraWorkAttribute]:
        """
        Get all Tempo Work Attribute types.

        Returns a list of all configured work attribute types.
        Each attribute defines a category that can be assigned to
        worklog entries (e.g., "Work Mode", "Cost Category").

        Returns:
            List of JiraWorkAttribute models

        Raises:
            Exception: If there's an error fetching work attributes
        """
        try:
            url = "/rest/tempo-core/1/work-attribute"
            result = self.jira.get(url)  # type: ignore[attr-defined]

            if not isinstance(result, list):
                logger.warning(
                    "Unexpected response type from work attributes API: %s",
                    type(result),
                )
                return []

            return [JiraWorkAttribute.from_api_response(attr) for attr in result]
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
            Exception: If there's an error fetching attribute values
        """
        try:
            url = f"/rest/tempo-core/1/work-attribute/{attribute_id}/values"
            result = self.jira.get(url)  # type: ignore[attr-defined]

            if not isinstance(result, list):
                logger.warning(
                    "Unexpected response type from work attribute values API: %s",
                    type(result),
                )
                return []

            return [JiraWorkAttributeValue.from_api_response(value) for value in result]
        except Exception as e:
            logger.warning(
                "Error fetching work attribute values for id=%s: %s",
                attribute_id,
                str(e),
            )
            return []
