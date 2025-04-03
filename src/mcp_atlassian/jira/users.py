"""Module for Jira user operations."""

import json
import logging

import requests

from .client import JiraClient

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
            if "accountId" in myself:
                self._current_user_account_id = myself["accountId"]
                return self._current_user_account_id

            # Handle Jira Data Center/Server which may not have accountId
            # but has "key" or "name" instead
            if "key" in myself:
                logger.info(
                    "Using 'key' instead of 'accountId' for Jira Data Center/Server"
                )
                self._current_user_account_id = myself["key"]
                return self._current_user_account_id
            elif "name" in myself:
                logger.info(
                    "Using 'name' instead of 'accountId' for Jira Data Center/Server"
                )
                self._current_user_account_id = myself["name"]
                return self._current_user_account_id

            error_msg = "Could not find accountId, key, or name in user data"
            raise ValueError(error_msg)
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
            response = self.jira.user_find_by_user_string(
                query=username, start=0, limit=1
            )
            if not response:
                return None

            for user in response:
                # Check if user matches criteria
                if (
                    user.get("displayName", "").lower() == username.lower()
                    or user.get("name", "").lower() == username.lower()
                    or user.get("emailAddress", "").lower() == username.lower()
                ):
                    # Jira Cloud uses accountId
                    if "accountId" in user:
                        return user["accountId"]
                    # Jira Data Center/Server might use key
                    elif "key" in user:
                        logger.info(
                            "Using 'key' instead of 'accountId' for Jira Data Center/Server"
                        )
                        return user["key"]
                    # Last resort fallback to name
                    elif "name" in user:
                        logger.info(
                            "Using 'name' instead of 'accountId' for Jira Data Center/Server"
                        )
                        return user["name"]
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
                    # Jira Cloud uses accountId
                    if "accountId" in user:
                        return user["accountId"]
                    # Jira Data Center/Server might use key
                    elif "key" in user:
                        logger.info(
                            "Using 'key' instead of 'accountId' for Jira Data Center/Server"
                        )
                        return user["key"]
                    # Last resort fallback to name
                    elif "name" in user:
                        logger.info(
                            "Using 'name' instead of 'accountId' for Jira Data Center/Server"
                        )
                        return user["name"]
            return None
        except Exception as e:
            logger.info(f"Error looking up user by permissions: {str(e)}")
            return None
