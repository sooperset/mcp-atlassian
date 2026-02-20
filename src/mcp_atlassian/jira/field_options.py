"""Module for Jira custom field options operations."""

import logging

from ..models.jira.field_option import FieldContext, FieldOption
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class FieldOptionsMixin(JiraClient):
    """Mixin for Jira custom field options operations.

    Provides methods to discover available options for custom fields
    (select, multi-select, radio, checkbox, cascading select).

    Cloud uses the Field Configuration Context API.
    Server/DC falls back to createmeta allowedValues.
    """

    def get_field_contexts(self, field_id: str) -> list[FieldContext]:
        """Get contexts for a custom field.

        Contexts define which projects/issue types a field applies to.
        Cloud only — Server/DC does not support this endpoint.

        Args:
            field_id: The custom field ID (e.g., 'customfield_10001')

        Returns:
            List of FieldContext objects (empty on Server/DC)
        """
        if not self.config.is_cloud:
            return []

        try:
            response = self.jira.get(
                f"rest/api/3/field/{field_id}/context",
                params={"maxResults": 100},
            )

            if not isinstance(response, dict):
                return []

            return [
                FieldContext.from_api_response(ctx)
                for ctx in response.get("values", [])
                if isinstance(ctx, dict)
            ]
        except Exception as e:
            logger.error(f"Error getting field contexts for {field_id}: {e}")
            return []

    def get_field_options(
        self,
        field_id: str,
        context_id: str | None = None,
        project_key: str | None = None,
        issue_type: str | None = None,
    ) -> list[FieldOption]:
        """Get allowed option values for a custom field.

        Cloud: Uses the Field Context Option API with pagination.
            If context_id is not provided, auto-resolves by fetching
            contexts and using the global context.
        Server/DC: Uses createmeta to get allowedValues.
            Requires project_key and issue_type parameters.

        Args:
            field_id: The custom field ID (e.g., 'customfield_10001')
            context_id: Context ID (Cloud only, auto-resolved if None)
            project_key: Project key (required for Server/DC)
            issue_type: Issue type name (required for Server/DC)

        Returns:
            List of FieldOption objects

        Raises:
            ValueError: If Server/DC and project_key/issue_type missing
        """
        if self.config.is_cloud:
            return self._get_field_options_cloud(field_id, context_id)
        else:
            return self._get_field_options_server(field_id, project_key, issue_type)

    def _get_field_options_cloud(
        self, field_id: str, context_id: str | None
    ) -> list[FieldOption]:
        """Get field options via Cloud API with pagination.

        Args:
            field_id: The custom field ID
            context_id: Context ID (auto-resolved if None)

        Returns:
            List of FieldOption objects
        """
        # Auto-resolve context if not provided
        if context_id is None:
            contexts = self.get_field_contexts(field_id)
            if not contexts:
                logger.warning(
                    f"No contexts found for field {field_id}. "
                    "Cannot retrieve options without a context."
                )
                return []

            # Prefer global context
            global_ctx = next((c for c in contexts if c.is_global_context), None)
            context_id = global_ctx.id if global_ctx else contexts[0].id

        # Paginate through all options
        all_options: list[FieldOption] = []
        start_at = 0
        max_results = 100

        while True:
            try:
                response = self.jira.get(
                    f"rest/api/3/field/{field_id}/context/{context_id}/option",
                    params={"startAt": start_at, "maxResults": max_results},
                )

                if not isinstance(response, dict):
                    break

                values = response.get("values", [])
                for item in values:
                    if isinstance(item, dict):
                        all_options.append(FieldOption.from_api_response(item))

                total = response.get("total", len(values))
                start_at += len(values)

                if start_at >= total or not values:
                    break

            except Exception as e:
                logger.error(
                    f"Error getting options for {field_id} context {context_id}: {e}"
                )
                break

        return all_options

    def _get_field_options_server(
        self,
        field_id: str,
        project_key: str | None,
        issue_type: str | None,
    ) -> list[FieldOption]:
        """Get field options via Server/DC createmeta.

        Args:
            field_id: The custom field ID
            project_key: Project key (required)
            issue_type: Issue type name (required)

        Returns:
            List of FieldOption objects

        Raises:
            ValueError: If project_key or issue_type is missing
        """
        if not project_key or not issue_type:
            msg = (
                "Server/DC requires project_key and issue_type "
                "parameters to retrieve field options. "
                "Example: get_field_options('customfield_10001', "
                "project_key='PROJ', issue_type='Bug')"
            )
            raise ValueError(msg)

        try:
            response = self.jira.get(
                "rest/api/2/issue/createmeta",
                params={
                    "projectKeys": project_key,
                    "issuetypeNames": issue_type,
                    "expand": "projects.issuetypes.fields",
                },
            )

            if not isinstance(response, dict):
                return []

            # Navigate: projects[0].issuetypes[0].fields.{field_id}.allowedValues
            projects = response.get("projects", [])
            if not projects:
                return []

            issue_types = projects[0].get("issuetypes", [])
            if not issue_types:
                return []

            fields = issue_types[0].get("fields", {})
            field_data = fields.get(field_id, {})
            allowed_values = field_data.get("allowedValues", [])

            return [
                FieldOption.from_api_response(item)
                for item in allowed_values
                if isinstance(item, dict)
            ]

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error getting options for {field_id} via createmeta: {e}")
            return []
