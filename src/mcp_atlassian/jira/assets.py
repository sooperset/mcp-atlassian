"""Module for Jira Assets (Insight) operations on Server/Data Center.

Wraps the Insight/Assets REST API exposed by Jira Service Management
Data Center. This is a DIFFERENT API surface from Jira Cloud's native
Assets API (workspace-scoped, served from
api.atlassian.com/jsm/assets/workspace/{workspaceId}/v1).

Base path is configurable because Atlassian renamed the app (JSM 5.3):
  - JSM DC >= 5.3 / Assets app:      rest/assets/1.0   (documented, default)
  - JSM DC <= 5.2 / Insight app:     rest/insight/1.0  (legacy)

Set JIRA_ASSETS_API_BASE to override (read into JiraConfig.assets_api_base).
The object search endpoint follows the base path: the Assets API serves
``aql/objects?qlQuery=`` while the legacy Insight API serves
``iql/objects?iql=``. Everything else is identical between the two.
"""

import logging
from typing import Any

from .client import JiraClient
from .config import DEFAULT_ASSETS_API_BASE

logger = logging.getLogger("mcp-jira")

__all__ = ["DEFAULT_ASSETS_API_BASE", "AssetsMixin"]


class AssetsMixin(JiraClient):
    """Mixin for Jira Assets / Insight operations (Server/Data Center)."""

    @property
    def _assets_base(self) -> str:
        """Return the Assets/Insight REST base path, without trailing slash."""
        base = getattr(self.config, "assets_api_base", None)
        if not isinstance(base, str) or not base.strip("/"):
            return DEFAULT_ASSETS_API_BASE
        return base.strip().strip("/")

    @property
    def _uses_legacy_insight_api(self) -> bool:
        """True when the configured base path targets the legacy Insight API."""
        return "insight" in self._assets_base.lower().split("/")

    def _ensure_server_mode(self) -> None:
        """Assets endpoints here target Server/Data Center only."""
        if self.config.is_cloud:
            raise NotImplementedError(
                "This Assets implementation targets the Insight/Assets REST API "
                "on Jira Server/Data Center. Jira Cloud uses a different "
                "workspace-scoped Assets API and is not supported here."
            )

    def _assets_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET against the Assets API."""
        self._ensure_server_mode()
        return self.jira.get(f"{self._assets_base}/{path.lstrip('/')}", params=params)

    def _assets_post(self, path: str, json_body: dict[str, Any]) -> Any:
        """POST against the Assets API."""
        self._ensure_server_mode()
        return self.jira.post(f"{self._assets_base}/{path.lstrip('/')}", data=json_body)

    def _assets_put(self, path: str, json_body: dict[str, Any]) -> Any:
        """PUT against the Assets API."""
        self._ensure_server_mode()
        return self.jira.put(f"{self._assets_base}/{path.lstrip('/')}", data=json_body)

    # ------------------------------------------------------------------
    # Schema / structure discovery
    # ------------------------------------------------------------------

    def list_asset_schemas(self) -> list[dict[str, Any]]:
        """List all object schemas visible to the authenticated user.

        Returns:
            List of simplified schema dicts (id, name, key, description).
        """
        response = self._assets_get("objectschema/list")
        if not isinstance(response, dict):
            logger.error("Unexpected objectschema/list payload: %s", type(response))
            return []

        schemas = response.get("objectschemas", [])
        if not isinstance(schemas, list):
            return []

        return [
            {
                "id": str(s.get("id", "")),
                "name": s.get("name"),
                "key": s.get("objectSchemaKey"),
                "description": s.get("description"),
                "object_count": s.get("objectCount"),
                "object_type_count": s.get("objectTypeCount"),
            }
            for s in schemas
            if isinstance(s, dict)
        ]

    def list_asset_object_types(self, schema_id: str) -> list[dict[str, Any]]:
        """List object types in a schema as a flat list.

        Args:
            schema_id: The object schema ID (e.g. '3').

        Returns:
            List of simplified object type dicts.
        """
        if not schema_id or not str(schema_id).strip():
            raise ValueError("schema_id is required")

        response = self._assets_get(
            f"objectschema/{str(schema_id).strip()}/objecttypes/flat"
        )
        if not isinstance(response, list):
            logger.error("Unexpected objecttypes/flat payload: %s", type(response))
            return []

        return [
            {
                "id": str(t.get("id", "")),
                "name": t.get("name"),
                "description": t.get("description"),
                "parent_object_type_id": (
                    str(t.get("parentObjectTypeId"))
                    if t.get("parentObjectTypeId") is not None
                    else None
                ),
                "object_count": t.get("objectCount"),
            }
            for t in response
            if isinstance(t, dict)
        ]

    def get_asset_object_type_attributes(
        self, object_type_id: str
    ) -> list[dict[str, Any]]:
        """Get the attribute definitions for an object type.

        This is the schema you need before creating or updating objects,
        because writes are keyed by numeric attribute ID, not by name.

        Args:
            object_type_id: The object type ID (e.g. '42').

        Returns:
            List of attribute definition dicts.
        """
        if not object_type_id or not str(object_type_id).strip():
            raise ValueError("object_type_id is required")

        response = self._assets_get(
            f"objecttype/{str(object_type_id).strip()}/attributes"
        )
        if not isinstance(response, list):
            logger.error("Unexpected objecttype attributes payload: %s", type(response))
            return []

        results = []
        for attr in response:
            if not isinstance(attr, dict):
                continue
            ref_type = attr.get("referenceObjectType") or {}
            results.append(
                {
                    "id": str(attr.get("id", "")),
                    "name": attr.get("name"),
                    "type": attr.get("type"),
                    "default_type": (attr.get("defaultType") or {}).get("name"),
                    "editable": attr.get("editable"),
                    "required": attr.get("minimumCardinality", 0) > 0,
                    "reference_object_type_id": (
                        str(ref_type.get("id")) if ref_type.get("id") else None
                    ),
                    "reference_object_type_name": ref_type.get("name"),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Object read
    # ------------------------------------------------------------------

    def search_assets_aql(
        self,
        aql: str,
        page: int = 1,
        results_per_page: int = 25,
        include_attributes: bool = True,
        schema_id: str | None = None,
    ) -> dict[str, Any]:
        """Search Assets objects using AQL/IQL.

        Args:
            aql: The AQL query string, e.g. 'objectType = "Person"
                AND "Email" LIKE "@example.com"'.
            page: 1-based page number.
            results_per_page: Objects per page (1-100 recommended).
            include_attributes: Whether to return attribute values.
            schema_id: Optional object schema ID to restrict the search to.

        Returns:
            Dict with objects list and pagination metadata.
        """
        if not aql or not aql.strip():
            raise ValueError("aql query string is required")

        # The Assets API (rest/assets) searches via aql/objects?qlQuery=;
        # the legacy Insight API (rest/insight) via iql/objects?iql=.
        if self._uses_legacy_insight_api:
            path, query_param = "iql/objects", "iql"
        else:
            path, query_param = "aql/objects", "qlQuery"

        params: dict[str, Any] = {
            query_param: aql.strip(),
            "page": max(1, int(page)),
            "resultPerPage": max(1, min(int(results_per_page), 100)),
            "includeAttributes": str(bool(include_attributes)).lower(),
            # objectTypeAttributes (attribute names) are only returned when
            # explicitly requested; without them values would be keyed by ID.
            "includeTypeAttributes": "true",
        }
        if schema_id is not None and str(schema_id).strip():
            params["objectSchemaId"] = str(schema_id).strip()

        response = self._assets_get(path, params=params)
        if not isinstance(response, dict):
            logger.error("Unexpected %s payload: %s", path, type(response))
            return {"objects": [], "total": 0, "page": page}

        objects = response.get("objectEntries", [])
        type_attrs = response.get("objectTypeAttributes", [])
        attr_names = {
            str(a.get("id")): a.get("name") for a in type_attrs if isinstance(a, dict)
        }

        return {
            "objects": [
                self._simplify_object(o, attr_names)
                for o in objects
                if isinstance(o, dict)
            ],
            "total": response.get("totalFilterCount", len(objects)),
            "page": response.get("pageNumber", page),
            # In the Insight/Assets API pageObjectSize is the number of objects
            # per page and pageSize is the total number of pages.
            "page_size": response.get("pageObjectSize"),
            "total_pages": response.get("pageSize"),
        }

    def _resolve_object_id(self, object_id: str) -> str:
        """Return the numeric object ID for an ID or object key.

        The object endpoints only accept numeric IDs, so an object key
        (e.g. 'HW-42') is resolved through an AQL lookup first.
        """
        if not object_id or not str(object_id).strip():
            raise ValueError("object_id is required")

        oid = str(object_id).strip()
        if oid.isdigit():
            return oid
        if '"' in oid or "\\" in oid:
            raise ValueError(f"Invalid object key: {oid!r}")

        result = self.search_assets_aql(
            f'Key = "{oid}"', results_per_page=1, include_attributes=False
        )
        for obj in result.get("objects", []):
            if obj.get("id"):
                return str(obj["id"])
        raise ValueError(f"Assets object not found for key {oid!r}")

    def get_asset_object(self, object_id: str) -> dict[str, Any]:
        """Get a single Assets object with its attributes.

        Args:
            object_id: The object ID (e.g. '1234') or object key (e.g. 'HW-42').

        Returns:
            Simplified object dict.
        """
        oid = self._resolve_object_id(object_id)
        obj = self._assets_get(f"object/{oid}")
        if not isinstance(obj, dict):
            logger.error("Unexpected object payload: %s", type(obj))
            return {}

        # The object response normally embeds each attribute's definition
        # (objectTypeAttribute.name). Fall back to the object type definition
        # only when a name is missing.
        attr_names: dict[str, str] = {}
        object_type = obj.get("objectType") or {}
        type_id = object_type.get("id")
        if type_id is not None and not self._attribute_names_embedded(obj):
            try:
                defs = self.get_asset_object_type_attributes(str(type_id))
                attr_names = {d["id"]: d["name"] for d in defs if d.get("id")}
            except Exception as e:  # noqa: BLE001 - degrade gracefully
                logger.warning(
                    "Could not resolve attribute names for object type %s: %s",
                    type_id,
                    e,
                )

        return self._simplify_object(obj, attr_names)

    def get_asset_object_history(self, object_id: str) -> list[dict[str, Any]]:
        """Get the change history for an Assets object.

        Args:
            object_id: The object ID or object key.

        Returns:
            List of history entry dicts.
        """
        oid = self._resolve_object_id(object_id)
        response = self._assets_get(f"object/{oid}/history")
        if not isinstance(response, list):
            return []

        return [
            {
                "id": str(h.get("id", "")),
                "actor": (h.get("actor") or {}).get("displayName"),
                "created": h.get("created"),
                "type": h.get("type"),
                "affected_attribute": h.get("affectedAttribute"),
                "old_value": h.get("oldValue"),
                "new_value": h.get("newValue"),
            }
            for h in response
            if isinstance(h, dict)
        ]

    def get_asset_object_connected_tickets(self, object_id: str) -> dict[str, Any]:
        """Get Jira issues connected to an Assets object.

        Args:
            object_id: The object ID or object key.

        Returns:
            Dict with connected ticket data.
        """
        oid = self._resolve_object_id(object_id)
        response = self._assets_get(f"objectconnectedtickets/{oid}/tickets")
        if not isinstance(response, dict):
            return {"tickets": []}
        return response

    # ------------------------------------------------------------------
    # Object write
    # ------------------------------------------------------------------

    def create_asset_object(
        self,
        object_type_id: str,
        attributes: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new Assets object.

        Args:
            object_type_id: The object type ID to create under.
            attributes: Mapping of attribute ID (as string) to value, e.g.
                {"142": "Jane Doe", "143": "jane.doe@example.com"}.
                Use get_asset_object_type_attributes() to resolve names to IDs.

        Returns:
            Simplified created object dict.
        """
        if not object_type_id or not str(object_type_id).strip():
            raise ValueError("object_type_id is required")
        if not attributes:
            raise ValueError("attributes mapping is required")

        payload = {
            "objectTypeId": str(object_type_id).strip(),
            "attributes": self._build_attribute_payload(attributes),
        }

        result = self._assets_post("object/create", payload)
        if not isinstance(result, dict):
            logger.error("Unexpected create response: %s", type(result))
            return {}
        return self._simplify_object(result, {})

    def update_asset_object(
        self,
        object_id: str,
        attributes: dict[str, Any],
        object_type_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing Assets object.

        Only the supplied attributes are sent. The REST reference does not
        state how omitted attributes are treated; in practice Insight leaves
        them unchanged.

        The documented update request body carries the object's type ID
        alongside the attributes. When it is not supplied it is read from
        the object itself first.

        Args:
            object_id: The object ID or object key to update.
            attributes: Mapping of attribute ID (as string) to new value.
            object_type_id: The object's type ID. Looked up when omitted.

        Returns:
            Simplified updated object dict.
        """
        if not attributes:
            raise ValueError("attributes mapping is required")

        oid = self._resolve_object_id(object_id)
        payload: dict[str, Any] = {
            "attributes": self._build_attribute_payload(attributes)
        }

        type_id = str(object_type_id).strip() if object_type_id else ""
        if not type_id:
            current = self._assets_get(f"object/{oid}")
            if isinstance(current, dict):
                found = (current.get("objectType") or {}).get("id")
                type_id = str(found) if found is not None else ""
        if type_id:
            payload["objectTypeId"] = type_id
        else:
            logger.warning(
                "Could not determine object type for object %s; sending update "
                "without objectTypeId",
                oid,
            )

        result = self._assets_put(f"object/{oid}", payload)
        if not isinstance(result, dict):
            logger.error("Unexpected update response: %s", type(result))
            return {}
        return self._simplify_object(result, {})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_attribute_payload(
        attributes: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Convert a flat {attr_id: value} mapping to the Insight write format.

        Values may be scalars or lists (for multi-value attributes).
        """
        payload = []
        for attr_id, value in attributes.items():
            values = value if isinstance(value, list) else [value]
            payload.append(
                {
                    "objectTypeAttributeId": str(attr_id),
                    "objectAttributeValues": [
                        {"value": "" if v is None else str(v)} for v in values
                    ],
                }
            )
        return payload

    @staticmethod
    def _attribute_names_embedded(obj: dict[str, Any]) -> bool:
        """Return True when every attribute carries its definition name."""
        for attr in obj.get("attributes", []) or []:
            if not isinstance(attr, dict):
                continue
            if not (attr.get("objectTypeAttribute") or {}).get("name"):
                return False
        return True

    @staticmethod
    def _simplify_object(
        obj: dict[str, Any], attr_names: dict[str, str]
    ) -> dict[str, Any]:
        """Flatten an Insight object response into a readable dict."""
        object_type = obj.get("objectType") or {}

        attributes: dict[str, Any] = {}
        for attr in obj.get("attributes", []) or []:
            if not isinstance(attr, dict):
                continue
            attr_id = str(attr.get("objectTypeAttributeId", ""))
            # Prefer the name embedded in the response when present,
            # otherwise fall back to the resolved lookup table.
            embedded = attr.get("objectTypeAttribute") or {}
            name = embedded.get("name") or attr_names.get(attr_id) or attr_id

            values = []
            for v in attr.get("objectAttributeValues", []) or []:
                if not isinstance(v, dict):
                    continue
                # Referenced objects carry a nested object; scalars carry
                # displayValue or value.
                referenced = v.get("referencedObject")
                if referenced and isinstance(referenced, dict):
                    values.append(
                        {
                            "id": str(referenced.get("id", "")),
                            "label": referenced.get("label"),
                            "object_key": referenced.get("objectKey"),
                        }
                    )
                else:
                    values.append(v.get("displayValue", v.get("value")))

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
