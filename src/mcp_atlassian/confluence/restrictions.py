"""Module for Confluence page restriction operations."""

import json
import logging
from typing import Any

from requests.exceptions import HTTPError

from ..utils.decorators import handle_auth_errors
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class RestrictionsMixin(ConfluenceClient):
    """Mixin for Confluence page restriction operations."""

    @handle_auth_errors("Confluence API")
    def get_page_restrictions(self, page_id: str) -> dict[str, Any]:
        """Get view and edit restrictions for a Confluence page.

        Returns the current restriction lists for the ``read`` and ``update``
        operations.  An empty list for an operation means the page is
        unrestricted for that operation (visible/editable by everyone).

        Args:
            page_id: The ID of the page to query.

        Returns:
            Dict with ``read`` and ``update`` keys, each containing:
            ``{"users": [...account_ids...], "groups": [...group_names...]}``

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If the API call fails.
        """
        try:
            data = self.confluence.get_all_restrictions_for_content(page_id)

            result: dict[str, Any] = {
                "read": {"users": [], "groups": []},
                "update": {"users": [], "groups": []},
            }

            if not isinstance(data, dict):
                return result

            for operation, op_key in (("read", "read"), ("update", "update")):
                op_data = data.get(operation, {})
                if not isinstance(op_data, dict):
                    continue

                restrictions = op_data.get("restrictions", {})
                if not isinstance(restrictions, dict):
                    continue

                users = restrictions.get("user", {})
                if isinstance(users, dict):
                    for u in users.get("results", []):
                        account_id = (
                            u.get("accountId") or u.get("username") or u.get("name")
                        )
                        if account_id:
                            result[op_key]["users"].append(account_id)

                groups = restrictions.get("group", {})
                if isinstance(groups, dict):
                    for g in groups.get("results", []):
                        group_name = g.get("name")
                        if group_name:
                            result[op_key]["groups"].append(group_name)

            return result
        except HTTPError:
            raise
        except Exception as e:
            logger.error(f"Error fetching restrictions for page {page_id}: {str(e)}")
            raise Exception(
                f"Failed to get restrictions for page {page_id}: {str(e)}"
            ) from e

    @handle_auth_errors("Confluence API")
    def set_page_restrictions(
        self,
        page_id: str,
        *,
        read_users: list[str] | None = None,
        read_groups: list[str] | None = None,
        edit_users: list[str] | None = None,
        edit_groups: list[str] | None = None,
    ) -> dict[str, Any]:
        """Set view and edit restrictions on a Confluence page.

        Replaces all existing restrictions with the provided lists.
        Passing empty lists for all parameters removes all restrictions
        (makes the page unrestricted).

        Confluence uses ``read`` for view access and ``update`` for edit
        access.  Users are identified by account ID (Cloud) or username
        (Server/DC); groups by group name.

        Args:
            page_id: The ID of the page to restrict.
            read_users: Account IDs (Cloud) / usernames (Server/DC) that may view the page.
            read_groups: Group names that may view the page.
            edit_users: Account IDs / usernames that may edit the page.
            edit_groups: Group names that may edit the page.

        Returns:
            Dict with the updated ``read`` and ``update`` restriction lists,
            in the same format as :meth:`get_page_restrictions`.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If the API call fails.
        """
        try:
            read_users = read_users or []
            read_groups = read_groups or []
            edit_users = edit_users or []
            edit_groups = edit_groups or []

            def _user_entry(account_id: str) -> dict[str, str]:
                # Cloud uses accountId; Server/DC uses name/username
                if self.config.is_cloud:
                    return {"type": "known", "accountId": account_id}
                return {"type": "known", "username": account_id}

            def _group_entry(name: str) -> dict[str, str]:
                return {"type": "group", "name": name}

            payload = [
                {
                    "operation": "read",
                    "restrictions": {
                        "user": [_user_entry(u) for u in read_users],
                        "group": [_group_entry(g) for g in read_groups],
                    },
                },
                {
                    "operation": "update",
                    "restrictions": {
                        "user": [_user_entry(u) for u in edit_users],
                        "group": [_group_entry(g) for g in edit_groups],
                    },
                },
            ]

            # The atlassian library's put() only accepts dict|str for data;
            # the restrictions endpoint expects a JSON array, so serialise manually.
            self.confluence.put(
                f"rest/api/content/{page_id}/restriction",
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )

            return {
                "read": {"users": read_users, "groups": read_groups},
                "update": {"users": edit_users, "groups": edit_groups},
            }
        except HTTPError:
            raise
        except Exception as e:
            logger.error(f"Error setting restrictions for page {page_id}: {str(e)}")
            raise Exception(
                f"Failed to set restrictions for page {page_id}: {str(e)}"
            ) from e
