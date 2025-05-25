"""Module for Jira user operations."""

import logging
import re
from typing import TYPE_CHECKING, TypeVar

import requests
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.models.jira.common import JiraUser

from .client import JiraClient

if TYPE_CHECKING:
    from mcp_atlassian.models.jira.common import JiraUser

JiraUserType = TypeVar("JiraUserType", bound="JiraUser")

logger = logging.getLogger("mcp-jira")


class UsersMixin(JiraClient):
    """Mixin for Jira user operations."""

    def get_current_user_account_id(self) -> str:
        """
        Get the account ID of the current user.

        Returns:
            str: Account ID of the current user.

        Raises:
            Exception: If unable to get the current user's account ID.
        """
        if getattr(self, "_current_user_account_id", None) is not None:
            return self._current_user_account_id

        try:
            logger.debug(
                "Calling self.jira.myself() to get current user details for account ID."
            )
            myself_data = self.jira.myself()

            if not isinstance(myself_data, dict):
                error_msg = "Failed to get user data: response was not a dictionary."
                logger.error(
                    f"{error_msg} Response type: {type(myself_data)}, Response: {str(myself_data)[:200]}"
                )
                raise Exception(error_msg)

            logger.debug(f"Received myself_data: {str(myself_data)[:500]}")

            account_id = None
            if isinstance(myself_data.get("accountId"), str):
                account_id = myself_data["accountId"]
            elif isinstance(myself_data.get("key"), str):
                logger.info(
                    "Using 'key' instead of 'accountId' for Jira Data Center/Server"
                )
                account_id = myself_data["key"]
            elif isinstance(myself_data.get("name"), str):
                logger.info(
                    "Using 'name' instead of 'accountId' for Jira Data Center/Server"
                )
                account_id = myself_data["name"]

            if account_id is None:
                error_msg = f"Could not find accountId, key, or name in user data: {str(myself_data)[:200]}"
                raise ValueError(error_msg)

            self._current_user_account_id = account_id
            return account_id
        except HTTPError as http_err:
            response_content = ""
            if http_err.response is not None:
                try:
                    response_content = http_err.response.text
                except Exception:
                    response_content = "(could not decode response content)"
            logger.error(
                f"HTTPError getting current user account ID: {http_err}. Response: {response_content[:500]}"
            )
            error_msg = f"Unable to get current user account ID: {http_err}"
            raise Exception(error_msg) from http_err
        except Exception as e:
            logger.error(f"Error getting current user account ID: {e}", exc_info=True)
            error_msg = f"Unable to get current user account ID: {e}"
            raise Exception(error_msg) from e

    def _get_account_id(self, assignee: str) -> str:
        """
        Get the account ID for a username or account ID.

        Args:
            assignee (str): Username or account ID.

        Returns:
            str: Account ID.

        Raises:
            ValueError: If the account ID could not be found.
        """
        # If it looks like an account ID already, return it
        if assignee.startswith("5") and len(assignee) >= 10:
            return assignee

        account_id = self._lookup_user_directly(assignee)
        if account_id:
            return account_id

        account_id = self._lookup_user_by_permissions(assignee)
        if account_id:
            return account_id

        error_msg = f"Could not find account ID for user: {assignee}"
        raise ValueError(error_msg)

    def _lookup_user_directly(self, username: str) -> str | None:
        """
        Look up a user account ID directly.

        Args:
            username (str): Username to look up.

        Returns:
            Optional[str]: Account ID if found, None otherwise.
        """
        try:
            params = {}
            if self.config.is_cloud:
                params["query"] = username
            else:
                params["username"] = username

            response = self.jira.user_find_by_user_string(**params, start=0, limit=1)
            if not isinstance(response, list):
                msg = f"Unexpected return value type from `jira.user_find_by_user_string`: {type(response)}"
                logger.error(msg)
                return None

            for user in response:
                if (
                    user.get("displayName", "").lower() == username.lower()
                    or user.get("name", "").lower() == username.lower()
                    or user.get("emailAddress", "").lower() == username.lower()
                ):
                    if self.config.is_cloud:
                        if "accountId" in user:
                            return user["accountId"]
                    else:
                        if "name" in user:
                            logger.info(
                                "Using 'name' for assignee field in Jira Data Center/Server"
                            )
                            return user["name"]
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
        """
        Look up a user account ID by permissions.

        Args:
            username (str): Username to look up.

        Returns:
            Optional[str]: Account ID if found, None otherwise.
        """
        try:
            url = f"{self.config.url}/rest/api/2/user/permission/search"
            params = {"query": username, "permissions": "BROWSE"}

            auth = None
            headers = {}
            if self.config.auth_type == "pat":
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
                    if self.config.is_cloud:
                        if "accountId" in user:
                            return user["accountId"]
                    else:
                        if "name" in user:
                            logger.info(
                                "Using 'name' for assignee field in Jira Data Center/Server"
                            )
                            return user["name"]
                        elif "key" in user:
                            logger.info(
                                "Using 'key' as fallback for assignee name in Jira Data Center/Server"
                            )
                            return user["key"]
            return None
        except Exception as e:
            logger.info(f"Error looking up user by permissions: {str(e)}")
            return None

    def _determine_user_api_params(self, identifier: str) -> dict[str, str]:
        """
        Determines the correct API parameter and value for the jira.user() call based on the identifier and instance type.

        Args:
            identifier (str): User identifier (accountId, username, key, or email).

        Returns:
            Dict[str, str]: A dictionary containing the single keyword argument for self.jira.user().

        Raises:
            ValueError: If a usable parameter cannot be determined.
        """
        api_kwargs: dict[str, str] = {}

        # Cloud: identifier is accountId
        if self.config.is_cloud and (
            re.match(r"^[0-9a-f]{24}$", identifier) or re.match(r"^\d+:\w+", identifier)
        ):
            api_kwargs["account_id"] = identifier
            logger.debug(f"Determined param: account_id='{identifier}' (Cloud)")
        # Server/DC: username, key, or email
        elif not self.config.is_cloud:
            if "@" in identifier:
                api_kwargs["username"] = identifier
                logger.debug(
                    f"Determined param: username='{identifier}' (Server/DC email - might not work)"
                )
            elif "-" in identifier and any(c.isdigit() for c in identifier):
                api_kwargs["key"] = identifier
                logger.debug(f"Determined param: key='{identifier}' (Server/DC)")
            else:
                api_kwargs["username"] = identifier
                logger.debug(f"Determined param: username='{identifier}' (Server/DC)")
        # Cloud: identifier is email
        elif self.config.is_cloud and "@" in identifier:
            try:
                resolved_id = self._lookup_user_directly(identifier)
                if resolved_id and (
                    re.match(r"^[0-9a-f]{24}$", resolved_id)
                    or re.match(r"^\d+:\w+", resolved_id)
                ):
                    api_kwargs["account_id"] = resolved_id
                    logger.debug(
                        f"Resolved email '{identifier}' to accountId '{resolved_id}'. Determined param: account_id (Cloud)"
                    )
                else:
                    raise ValueError(
                        f"Could not resolve email '{identifier}' to a valid account ID for Jira Cloud."
                    )
            except Exception as e:
                logger.warning(f"Failed to resolve email '{identifier}': {e}")
                raise ValueError(
                    f"Could not resolve email '{identifier}' to a valid account ID for Jira Cloud."
                ) from e
        # Cloud: identifier is not accountId or email, try to resolve
        else:
            logger.debug(
                f"Identifier '{identifier}' on Cloud is not an account ID or email. Attempting resolution."
            )
            try:
                account_id_resolved = self._get_account_id(identifier)
                api_kwargs["account_id"] = account_id_resolved
                logger.debug(
                    f"Resolved identifier '{identifier}' to accountId '{account_id_resolved}'. Determined param: account_id (Cloud)"
                )
            except ValueError as e:
                logger.error(
                    f"Could not resolve identifier '{identifier}' to a usable format (accountId/username/key)."
                )
                raise ValueError(
                    f"Could not determine how to look up user '{identifier}'."
                ) from e

        if not api_kwargs:
            logger.error(
                f"Logic failed to determine API parameters for identifier '{identifier}'"
            )
            raise ValueError(
                f"Could not determine the correct parameter to use for identifier '{identifier}'."
            )

        return api_kwargs

    def get_user_profile_by_identifier(self, identifier: str) -> "JiraUser":
        """
        Retrieve Jira user profile information by identifier.

        Args:
            identifier (str): User identifier (accountId, username, key, or email).

        Returns:
            JiraUser: JiraUser model with profile information.

        Raises:
            ValueError: If the user cannot be found or identifier cannot be resolved.
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: For other API errors.
        """
        api_kwargs = self._determine_user_api_params(identifier)

        try:
            logger.debug(f"Calling self.jira.user() with parameters: {api_kwargs}")
            user_data = self.jira.user(**api_kwargs)
            if not isinstance(user_data, dict):
                logger.error(
                    f"User lookup for '{identifier}' returned unexpected type: {type(user_data)}. Data: {user_data}"
                )
                raise ValueError(f"User '{identifier}' not found or lookup failed.")
            return JiraUser.from_api_response(user_data)
        except HTTPError as http_err:
            if http_err.response is not None:
                response_text = http_err.response.text[:200]
                status_code = http_err.response.status_code
                if status_code == 404:
                    raise ValueError(f"User '{identifier}' not found.") from http_err
                elif status_code in [401, 403]:
                    logger.error(
                        f"Authentication/Permission error for '{identifier}': {status_code}"
                    )
                    raise MCPAtlassianAuthenticationError(
                        f"Permission denied accessing user '{identifier}'."
                    ) from http_err
                else:
                    logger.error(
                        f"HTTP error {status_code} for '{identifier}': {http_err}. Response: {response_text}"
                    )
                    raise Exception(
                        f"API error getting user profile for '{identifier}': {http_err}"
                    ) from http_err
            else:
                logger.error(
                    f"Network or unknown HTTP error (no response object) for '{identifier}': {http_err}"
                )
                raise Exception(
                    f"Network error getting user profile for '{identifier}': {http_err}"
                ) from http_err
        except Exception as e:
            logger.exception(
                f"Unexpected error getting/processing user profile for '{identifier}':"
            )
            raise Exception(
                f"Error processing user profile for '{identifier}': {str(e)}"
            ) from e
