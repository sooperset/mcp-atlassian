"""Jira Assets (Insight) discovery for Server/Data Center."""

import logging
from typing import Any

from .client import JiraClient
from .config import DEFAULT_ASSETS_API_BASE

logger = logging.getLogger("mcp-jira")

__all__ = ["DEFAULT_ASSETS_API_BASE", "AssetsMixin"]


class AssetsMixin(JiraClient):
    """Mixin for the Server/Data Center Assets discovery API."""

    @property
    def _assets_base(self) -> str:
        """Return the Assets/Insight REST base path without a trailing slash."""
        base = getattr(self.config, "assets_api_base", None)
        if not isinstance(base, str) or not base.strip("/"):
            return DEFAULT_ASSETS_API_BASE
        return base.strip().strip("/")

    @property
    def _uses_legacy_insight_api(self) -> bool:
        """Return whether the configured base targets the legacy Insight API."""
        return "insight" in self._assets_base.lower().split("/")

    def _ensure_server_mode(self) -> None:
        """Reject this Data Center API surface when configured for Jira Cloud."""
        if self.config.is_cloud:
            raise NotImplementedError(
                "This Assets implementation targets the Insight/Assets REST API "
                "on Jira Server/Data Center. Jira Cloud uses a different "
                "workspace-scoped Assets API and is not supported here."
            )

    def _assets_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Send a GET request to the configured Assets API."""
        self._ensure_server_mode()
        return self.jira.get(f"{self._assets_base}/{path.lstrip('/')}", params=params)

    @staticmethod
    def _numeric_id(value: str, name: str) -> str:
        """Normalize and validate an Assets numeric path ID."""
        normalized = str(value).strip()
        if not normalized.isdigit():
            raise ValueError(f"{name} must be a numeric ID")
        return normalized

    def list_asset_schemas(self) -> list[dict[str, Any]]:
        """List object schemas visible to the authenticated user."""
        response = self._assets_get("objectschema/list")
        if not isinstance(response, dict):
            logger.error("Unexpected objectschema/list payload: %s", type(response))
            return []

        schemas = response.get("objectschemas", [])
        if not isinstance(schemas, list):
            return []

        return [
            {
                "id": str(schema.get("id", "")),
                "name": schema.get("name"),
                "key": schema.get("objectSchemaKey"),
                "description": schema.get("description"),
                "object_count": schema.get("objectCount"),
                "object_type_count": schema.get("objectTypeCount"),
            }
            for schema in schemas
            if isinstance(schema, dict)
        ]

    def list_asset_object_types(self, schema_id: str) -> list[dict[str, Any]]:
        """List the object types in a schema as a flat list."""
        normalized_id = self._numeric_id(schema_id, "schema_id")
        response = self._assets_get(f"objectschema/{normalized_id}/objecttypes/flat")
        if not isinstance(response, list):
            logger.error("Unexpected objecttypes/flat payload: %s", type(response))
            return []

        return [
            {
                "id": str(object_type.get("id", "")),
                "name": object_type.get("name"),
                "description": object_type.get("description"),
                "parent_object_type_id": (
                    str(object_type.get("parentObjectTypeId"))
                    if object_type.get("parentObjectTypeId") is not None
                    else None
                ),
                "object_count": object_type.get("objectCount"),
            }
            for object_type in response
            if isinstance(object_type, dict)
        ]

    def get_asset_object_type_attributes(
        self, object_type_id: str
    ) -> list[dict[str, Any]]:
        """Get the attribute definitions for an object type."""
        normalized_id = self._numeric_id(object_type_id, "object_type_id")
        response = self._assets_get(f"objecttype/{normalized_id}/attributes")
        if not isinstance(response, list):
            logger.error(
                "Unexpected object type attributes payload: %s", type(response)
            )
            return []

        results = []
        for attribute in response:
            if not isinstance(attribute, dict):
                continue
            reference_type = attribute.get("referenceObjectType") or {}
            results.append(
                {
                    "id": str(attribute.get("id", "")),
                    "name": attribute.get("name"),
                    "type": attribute.get("type"),
                    "default_type": (attribute.get("defaultType") or {}).get("name"),
                    "editable": attribute.get("editable"),
                    "required": attribute.get("minimumCardinality", 0) > 0,
                    "reference_object_type_id": (
                        str(reference_type.get("id"))
                        if reference_type.get("id")
                        else None
                    ),
                    "reference_object_type_name": reference_type.get("name"),
                }
            )
        return results

    def search_assets_aql(
        self,
        aql: str,
        page: int = 1,
        results_per_page: int = 25,
    ) -> dict[str, Any]:
        """Search Assets for outcome-oriented Jira issue enrichment."""
        if not aql or not aql.strip():
            raise ValueError("aql query string is required")

        if self._uses_legacy_insight_api:
            path, query_parameter = "iql/objects", "iql"
        else:
            path, query_parameter = "aql/objects", "qlQuery"

        params: dict[str, Any] = {
            query_parameter: aql.strip(),
            "page": max(1, int(page)),
            "resultPerPage": max(1, min(int(results_per_page), 100)),
            "includeAttributes": "true",
            "includeTypeAttributes": "true",
        }
        response = self._assets_get(path, params=params)
        if not isinstance(response, dict):
            logger.error("Unexpected %s payload: %s", path, type(response))
            return {"objects": [], "total": 0, "page": page}

        objects = response.get("objectEntries", [])
        if not isinstance(objects, list):
            objects = []
        type_attributes = response.get("objectTypeAttributes", [])
        if not isinstance(type_attributes, list):
            type_attributes = []
        attribute_names = {
            str(attribute.get("id")): attribute.get("name")
            for attribute in type_attributes
            if isinstance(attribute, dict)
        }

        return {
            "objects": [
                self._simplify_object(obj, attribute_names)
                for obj in objects
                if isinstance(obj, dict)
            ],
            "total": response.get("totalFilterCount", len(objects)),
            "page": response.get("pageNumber", page),
            "page_size": response.get("pageObjectSize"),
            "total_pages": response.get("pageSize"),
        }

    @staticmethod
    def _simplify_object(
        obj: dict[str, Any], attribute_names: dict[str, str]
    ) -> dict[str, Any]:
        """Flatten an Assets object response into a readable dictionary."""
        object_type = obj.get("objectType") or {}
        attributes: dict[str, Any] = {}
        for attribute in obj.get("attributes", []) or []:
            if not isinstance(attribute, dict):
                continue
            attribute_id = str(attribute.get("objectTypeAttributeId", ""))
            embedded = attribute.get("objectTypeAttribute") or {}
            name = (
                embedded.get("name")
                or attribute_names.get(attribute_id)
                or attribute_id
            )

            values = []
            for value in attribute.get("objectAttributeValues", []) or []:
                if not isinstance(value, dict):
                    continue
                referenced = value.get("referencedObject")
                if isinstance(referenced, dict):
                    values.append(
                        {
                            "id": str(referenced.get("id", "")),
                            "label": referenced.get("label"),
                            "object_key": referenced.get("objectKey"),
                        }
                    )
                else:
                    values.append(value.get("displayValue", value.get("value")))

            if len(values) == 1:
                attributes[name] = values[0]
            elif values:
                attributes[name] = values

        return {
            "id": str(obj.get("id", "")),
            "object_key": obj.get("objectKey"),
            "label": obj.get("label"),
            "object_type_id": (
                str(object_type.get("id")) if object_type.get("id") else None
            ),
            "object_type_name": object_type.get("name"),
            "created": obj.get("created"),
            "updated": obj.get("updated"),
            "attributes": attributes,
        }
