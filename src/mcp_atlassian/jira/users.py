"""Module for Jira user operations."""

import json
import logging
import re
from typing import TYPE_CHECKING, TypeVar

import requests
from requests.exceptions import HTTPError

from .client import JiraClient

# Forward reference for JiraUser
if TYPE_CHECKING:
    from mcp_atlassian.models.jira.common import JiraUser

# Type variable for the return type
JiraUserType = TypeVar("JiraUserType", bound="JiraUser")

logger = logging.getLogger("mcp-jira")


class UsersMixin(JiraClient):
    """Mixin for Jira user operations."""

    def get_current_user_account_id(self) -> str:
        """Get the account ID of the current user.

        Returns:
            Account ID of the current user

        Raises:
            Exception: If unable to get the current user's account ID
        """
        if self._current_user_account_id is not None:
            return self._current_user_account_id

        try:
            url = f"{self.config.url.rstrip('/')}/rest/api/2/myself"
            headers = {"Accept": "application/json"}

            if self.config.auth_type == "token":
                headers["Authorization"] = f"Bearer {self.config.personal_token}"
                auth = None
            else:
                auth = (self.config.username or "", self.config.api_token or "")

            response = requests.get(
                url,
                headers=headers,
                auth=auth,
                verify=self.config.ssl_verify,
                timeout=30,
            )

            if response.status_code != 200:
                error_msg = f"Failed to get user data: HTTP {response.status_code}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Only parse the JSON, don't convert any fields to Python objects
            try:
                myself = json.loads(response.text)
            except json.JSONDecodeError as e:
                error_msg = f"Failed to parse JSON response: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Original logic to extract the ID
            account_id = None
            if isinstance(myself.get("accountId"), str):
                account_id = myself["accountId"]

            # Handle Jira Data Center/Server which may not have accountId
            # but has "key" or "name" instead
            elif isinstance(myself.get("key"), str):
                logger.info(
                    "Using 'key' instead of 'accountId' for Jira Data Center/Server"
                )
                account_id = myself["key"]

            elif isinstance(myself.get("name"), str):
                logger.info(
                    "Using 'name' instead of 'accountId' for Jira Data Center/Server"
                )
                account_id = myself["name"]

            if account_id is None:
                error_msg = "Could not find accountId, key, or name in user data"
                raise ValueError(error_msg)

            self._current_user_account_id = account_id
            return account_id
        except Exception as e:
            logger.error(f"Error getting current user account ID: {str(e)}")
            error_msg = f"Unable to get current user account ID: {str(e)}"
            raise Exception(error_msg)

    def _get_account_id(self, assignee: str) -> str:
        """Get the account ID for a username.

        Args:
            assignee: Username or account ID

        Returns:
            Account ID

        Raises:
            ValueError: If the account ID could not be found
        """
        # If it looks like an account ID already, return it
        if assignee.startswith("5") and len(assignee) >= 10:
            return assignee

        # First try direct lookup
        account_id = self._lookup_user_directly(assignee)
        if account_id:
            return account_id

        # If that fails, try permissions-based lookup
        account_id = self._lookup_user_by_permissions(assignee)
        if account_id:
            return account_id

        error_msg = f"Could not find account ID for user: {assignee}"
        raise ValueError(error_msg)

    def _lookup_user_directly(self, username: str) -> str | None:
        """Look up a user account ID directly.

        Args:
            username: Username to look up

        Returns:
            Account ID if found, None otherwise
        """
        try:
            # Try to find user
            params = {}
            if self.config.is_cloud:
                params["query"] = username
            else:
                params["username"] = username  # Use 'username' for Server/DC

            response = self.jira.user_find_by_user_string(**params, start=0, limit=1)
            if not isinstance(response, list):
                msg = f"Unexpected return value type from `jira.user_find_by_user_string`: {type(response)}"
                logger.error(msg)
                return None

            for user in response:
                # Check if user matches criteria
                if (
                    user.get("displayName", "").lower() == username.lower()
                    or user.get("name", "").lower() == username.lower()
                    or user.get("emailAddress", "").lower() == username.lower()
                ):
                    # Prioritize based on Cloud vs Server/DC for assignee field compatibility
                    if self.config.is_cloud:
                        # Cloud requires accountId
                        if "accountId" in user:
                            return user["accountId"]
                    else:
                        # Server/DC requires 'name' for the assignee field { "name": ... }
                        if "name" in user:
                            logger.info(
                                "Using 'name' for assignee field in Jira Data Center/Server"
                            )
                            return user["name"]
                        # Fallback to key if name is somehow missing (less common)
                        elif "key" in user:
                            logger.info(
                                "Using 'key' as fallback for assignee name in Jira Data Center/Server"
                            )
                            return user["key"]

            return None
        except Exception as e:
            logger.info(f"Error looking up user directly: {str(e)}")
            return None

    def _lookup_user_by_permissions(self, username: str) -> str | None:
        """Look up a user account ID by permissions.

        This is a fallback method when direct lookup fails.

        Args:
            username: Username to look up

        Returns:
            Account ID if found, None otherwise
        """
        try:
            # Try to find user who has permissions for a project
            # This approach helps when regular lookup fails due to permissions
            url = f"{self.config.url}/rest/api/2/user/permission/search"
            params = {"query": username, "permissions": "BROWSE"}

            auth = None
            headers = {}
            if self.config.auth_type == "token":
                headers["Authorization"] = f"Bearer {self.config.personal_token}"
            else:
                auth = (self.config.username or "", self.config.api_token or "")

            response = requests.get(
                url,
                params=params,
                auth=auth,
                headers=headers,
                verify=self.config.ssl_verify,
            )

            if response.status_code == 200:
                data = response.json()
                for user in data.get("users", []):
                    # Prioritize based on Cloud vs Server/DC for assignee field compatibility
                    if self.config.is_cloud:
                        # Cloud requires accountId
                        if "accountId" in user:
                            return user["accountId"]
                    else:
                        # Server/DC requires 'name' for the assignee field { "name": ... }
                        if "name" in user:
                            logger.info(
                                "Using 'name' for assignee field in Jira Data Center/Server"
                            )
                            return user["name"]
                        # Fallback to key if name is somehow missing (less common)
                        elif "key" in user:
                            logger.info(
                                "Using 'key' as fallback for assignee name in Jira Data Center/Server"
                            )
                            return user["key"]
            return None
        except Exception as e:
            logger.info(f"Error looking up user by permissions: {str(e)}")
            return None

    def get_user_profile_by_identifier(self, identifier: str) -> "JiraUser":
        """
        Retrieve Jira user profile information by identifier.

        Args:
            identifier: User identifier (accountId, username, key, or email).

        Returns:
            JiraUser model with profile information.

        Raises:
            ValueError: If the user cannot be found.
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: For other API errors.
        """
        params = {}
        # Determine the correct parameter based on identifier format and instance type
        if self.config.is_cloud and (
            re.match(r"^[0-9a-f]{24}$", identifier) or re.match(r"^\d+:\w+", identifier)
        ):
            params["accountId"] = identifier
            logger.debug(f"Treating '{identifier}' as accountId (Cloud)")
        elif not self.config.is_cloud:
            params["username"] = identifier
            logger.debug(f"Treating '{identifier}' as username (Server/DC)")
        elif (
            self.config.is_cloud
            and not re.match(r"^[0-9a-f]{24}$", identifier)
            and not re.match(r"^\d+:\w+", identifier)
        ):
            if "@" in identifier:
                try:  # Try resolving email to accountId first for Cloud
                    resolved_id = self._lookup_user_directly(identifier)
                    if resolved_id and (
                        re.match(r"^[0-9a-f]{24}$", resolved_id)
                        or re.match(r"^\d+:\w+", resolved_id)
                    ):
                        params["accountId"] = resolved_id
                        logger.debug(
                            f"Resolved email '{identifier}' to accountId '{resolved_id}' (Cloud)"
                        )
                    else:
                        params["query"] = identifier
                        logger.debug(
                            f"Searching for Cloud user profile by query: {identifier}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to resolve email '{identifier}': {e}")
                    params["query"] = identifier
            else:
                params["query"] = identifier
                logger.debug(f"Searching for Cloud user profile by query: {identifier}")
        else:
            params["query"] = identifier
            logger.warning(f"Unexpected identifier format '{identifier}', using query.")

        try:
            user_data = self.jira.user(params=params)  # type: ignore
            if not isinstance(user_data, dict):
                logger.error(
                    f"User lookup for '{identifier}' returned unexpected type: {type(user_data)}. Data: {user_data}"
                )
                raise ValueError(f"User '{identifier}' not found or lookup failed.")

            from mcp_atlassian.models.jira.common import JiraUser

            return JiraUser.from_api_response(user_data)

        except HTTPError as http_err:
            if http_err.response is not None:
                status_code = http_err.response.status_code
                if status_code == 404:
                    raise ValueError(f"User '{identifier}' not found.") from http_err
                elif status_code in [401, 403]:
                    logger.error(
                        f"Authentication/Permission error for '{identifier}': {status_code}"
                    )
                    from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

                    raise MCPAtlassianAuthenticationError(
                        f"Permission denied accessing user '{identifier}'."
                    ) from http_err
                else:
                    logger.error(
                        f"HTTP error {status_code} for '{identifier}': {http_err}"
                    )
                    raise Exception(
                        f"API error getting user profile for '{identifier}': {http_err}"
                    ) from http_err
            else:
                logger.error(
                    f"Network or unknown HTTP error for '{identifier}': {http_err}"
                )
                raise Exception(
                    f"Network error getting user profile for '{identifier}': {http_err}"
                ) from http_err
        except Exception as e:
            logger.error(f"Unexpected error for '{identifier}': {str(e)}")
            raise Exception(
                f"Error processing user profile for '{identifier}': {str(e)}"
            ) from e
