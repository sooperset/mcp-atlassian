"""Module for Jira Structure (Almworks) board operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError, RequestException

from ..utils.decorators import handle_auth_errors
from .client import JiraClient

logger = logging.getLogger("mcp-jira")

_SERVER_DC_PAGE_SIZE = 50


class StructuresMixin(JiraClient):
    """Mixin for Jira Structure plugin operations.

    Requires the Structure by Almworks plugin on the Jira instance.
    Uses the Structure REST API (rest/structure/2.0/).
    """

    @handle_auth_errors("Jira API")
    def get_structure(self, structure_id: int | str) -> dict[str, Any]:
        """Get metadata for a Structure board.

        Args:
            structure_id: The ID of the structure.

        Returns:
            Dictionary with structure name, description, etc.
        """
        result = self.jira.get(f"rest/structure/2.0/structure/{structure_id}")

        if not isinstance(result, dict):
            return {"structure_id": str(structure_id), "error": "Invalid response"}

        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description", ""),
            "editable": not result.get("readOnly", False),
            "is_archived": result.get("archived", result.get("isArchived", False)),
            "owner": result.get("owner"),
        }

    @handle_auth_errors("Jira API")
    def get_structure_forest(self, structure_id: int | str) -> dict[str, Any]:
        """Get the raw forest (hierarchy formula) for a Structure board.

        Returns the parsed row list with item IDs and depths, but
        without resolved issue details. Use get_structure_issues()
        for the fully resolved hierarchy.

        Args:
            structure_id: The ID of the structure.

        Returns:
            Dictionary with rows (row_id, depth, item_id, item_type)
            and metadata.
        """
        result = self.jira.post(
            "rest/structure/2.0/forest/latest",
            json={"structureId": int(structure_id)},
        )

        if not isinstance(result, dict) or "formula" not in result:
            return {"structure_id": str(structure_id), "error": "Invalid response"}

        rows = self._parse_formula(result["formula"], result.get("itemTypes"))

        return {
            "structure_id": int(structure_id),
            "total_rows": len(rows),
            "rows": rows,
            "version": result.get("version"),
        }

    @handle_auth_errors("Jira API")
    def get_structure_issues(
        self,
        structure_id: int | str,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        """Get the full resolved hierarchy for a Structure board.

        Fetches the forest, resolves all item IDs to Jira issue
        details (key, summary, status, type, project), and returns
        a flat list with depth for hierarchy reconstruction.

        Args:
            structure_id: The ID of the structure.
            max_depth: Optional maximum depth to include (0 = top level only).

        Returns:
            Dictionary with resolved issue hierarchy and structure metadata.
        """
        # Step 1: Get structure metadata
        meta = self.get_structure(structure_id)

        # Step 2: Get the forest
        forest_result = self.jira.post(
            "rest/structure/2.0/forest/latest",
            json={"structureId": int(structure_id)},
        )

        if not isinstance(forest_result, dict) or "formula" not in forest_result:
            return {
                "structure_id": int(structure_id),
                "name": meta.get("name"),
                "error": "Could not fetch forest",
            }

        rows = self._parse_formula(
            forest_result["formula"], forest_result.get("itemTypes")
        )

        # Apply depth filter
        if max_depth is not None:
            rows = [r for r in rows if r["depth"] <= max_depth]

        # Step 3: Collect issue IDs to resolve (validate numeric)
        item_ids = [
            r["item_id"] for r in rows if r.get("item_id") and r["item_id"].isdigit()
        ]
        unique_ids = list(dict.fromkeys(item_ids))

        # Step 4: Batch resolve via search_issues (respects projects_filter)
        resolved: dict[str, dict] = {}
        _fields = ["summary", "issuetype", "status", "project"]
        for i in range(0, len(unique_ids), _SERVER_DC_PAGE_SIZE):
            batch = unique_ids[i : i + _SERVER_DC_PAGE_SIZE]
            jql = f"id in ({','.join(batch)})"
            try:
                sr = self.search_issues(  # type: ignore[attr-defined]
                    jql=jql,
                    fields=_fields,
                    limit=len(batch),
                )
                for issue in sr.issues:
                    sd = issue.to_simplified_dict()
                    status = sd.get("status", {})
                    itype = sd.get("issue_type", {})
                    proj = sd.get("project", {})
                    resolved[str(issue.id)] = {
                        "key": issue.key,
                        "summary": sd.get("summary", ""),
                        "issue_type": (
                            itype.get("name", "") if isinstance(itype, dict) else ""
                        ),
                        "status": (
                            status.get("name", "") if isinstance(status, dict) else ""
                        ),
                        "status_category": (
                            str(status.get("category", ""))
                            if isinstance(status, dict)
                            else ""
                        ),
                        "project": (
                            proj.get("key", "") if isinstance(proj, dict) else ""
                        ),
                    }
            except HTTPError:
                raise
            except (
                RequestException,
                AttributeError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                logger.warning("Failed to resolve batch starting at index %d", i)

        # Step 5: Build resolved hierarchy — keep unresolved rows as
        # placeholders so callers can see the gap.
        items = []
        total_issue_rows = 0
        for row in rows:
            item_id = row.get("item_id")
            if item_id and item_id in resolved:
                total_issue_rows += 1
                items.append({"depth": row["depth"], **resolved[item_id]})
            elif item_id and item_id.isdigit():
                total_issue_rows += 1
                items.append(
                    {
                        "depth": row["depth"],
                        "key": None,
                        "summary": "[unresolved]",
                        "issue_type": "",
                        "status": "",
                        "status_category": "",
                        "project": "",
                    }
                )
            elif row.get("row_type") != "issue":
                row_type = row.get("row_type", "item")
                items.append(
                    {
                        "depth": row["depth"],
                        "key": None,
                        "summary": f"[{row_type}: {row.get('item_ref', '?')}]",
                        "issue_type": row_type,
                        "status": "",
                        "status_category": "",
                        "project": "",
                    }
                )

        resolved_count = sum(1 for i in items if i.get("key"))
        result_dict: dict[str, Any] = {
            "structure_id": int(structure_id),
            "name": meta.get("name", ""),
            "description": meta.get("description", ""),
            "total_items": len(items),
            "resolved_count": resolved_count,
            "items": items,
        }
        if resolved_count < total_issue_rows:
            result_dict["partial"] = True
            result_dict["unresolved_count"] = total_issue_rows - resolved_count
        return result_dict

    @staticmethod
    def _parse_formula(
        formula: str, item_types: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Parse a Structure forest formula string into row dicts.

        The formula format is comma-separated entries of:
          rowId:depth:itemIdentity[:rowSemantic]

        An issue identity is its numeric Jira issue ID. Other identities use
        ``itemType/itemId`` or ``itemType//stringItemId`` and are resolved via
        the response's ``itemTypes`` mapping.

        Args:
            formula: The raw formula string from the API.
            item_types: Optional mapping of numeric type IDs to type names.

        Returns:
            List of row dicts with depth, item_id, etc.  Malformed
            entries are skipped with a warning log.
        """
        rows: list[dict[str, Any]] = []
        skipped = 0
        for entry in formula.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            try:
                if len(parts) not in (3, 4):
                    skipped += 1
                    logger.debug("Skipping malformed formula entry: %s", entry)
                    continue

                row_id, depth, item_identity = parts[:3]
                row: dict[str, Any] = {
                    "row_id": row_id,
                    "depth": int(depth),
                }
                if len(parts) == 4:
                    row["row_semantic"] = parts[3]

                if item_identity.isdigit():
                    row.update(
                        {
                            "item_id": item_identity,
                            "item_type": "issue",
                            "row_type": "issue",
                        }
                    )
                else:
                    type_id = item_identity.split("/", 1)[0]
                    type_name = (item_types or {}).get(type_id, "item")
                    row_type = type_name.rsplit(":type-", 1)[-1]
                    row.update(
                        {
                            "item_ref": item_identity,
                            "item_type": type_name,
                            "row_type": row_type,
                        }
                    )
                rows.append(row)
            except (ValueError, TypeError):
                skipped += 1
                logger.debug("Skipping malformed formula entry: %s", entry)
        if skipped:
            logger.warning(
                "Skipped %d malformed formula entries during parsing", skipped
            )
        return rows
