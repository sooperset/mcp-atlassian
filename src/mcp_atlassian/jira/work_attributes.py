"""Mixin for Tempo Core Work Attributes operations."""

from ..models.jira import JiraWorkAttribute, JiraWorkAttributeValue
from .client import JiraClient


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
            Configured work attributes. An empty API response returns an empty
            list.

        Raises:
            NotImplementedError: If connected to Jira Cloud.
            TypeError: If Tempo returns a response with an unexpected shape.
        """
        self._ensure_server_mode()
        result = self.jira.get(  # type: ignore[attr-defined]
            "rest/tempo-core/1/work-attribute"
        )

        if not isinstance(result, list):
            raise TypeError(
                "Unexpected response type from work attributes API: "
                f"{type(result).__name__}"
            )
        if not all(isinstance(attribute, dict) for attribute in result):
            raise TypeError("Unexpected work attribute entry in Tempo response")

        return [JiraWorkAttribute.from_api_response(attribute) for attribute in result]

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
            TypeError: If Tempo returns a response with an unexpected shape.
        """
        if attribute_id <= 0:
            raise ValueError("attribute_id must be greater than zero")

        self._ensure_server_mode()
        result = self.jira.get(  # type: ignore[attr-defined]
            f"rest/tempo-core/1/work-attribute/{attribute_id}/static-list-value"
        )

        if not isinstance(result, list):
            raise TypeError(
                "Unexpected response type from work attribute values API: "
                f"{type(result).__name__}"
            )
        if not all(isinstance(value, dict) for value in result):
            raise TypeError("Unexpected work attribute value in Tempo response")

        return [JiraWorkAttributeValue.from_api_response(value) for value in result]

    def get_work_attribute_catalog(self) -> list[JiraWorkAttribute]:
        """Get work attribute definitions with static-list values populated.

        Returns:
            Configured work attributes, including values for static-list
            attributes. An empty API response returns an empty list.

        Raises:
            NotImplementedError: If connected to Jira Cloud.
            TypeError: If Tempo returns a response with an unexpected shape.
        """
        attributes = self.get_work_attributes()
        for attribute in attributes:
            attribute_type = attribute.type
            type_value = (
                attribute_type.value.upper()
                if attribute_type and attribute_type.value
                else ""
            )
            if attribute.id > 0 and type_value == "STATIC_LIST":
                attribute.static_list_values = self.get_work_attribute_values(
                    attribute.id
                )
        return attributes
