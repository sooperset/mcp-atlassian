"""Module for Jira user operations."""

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
            myself = self.jira.myself()
            if "accountId" in myself:
                self._current_user_account_id = myself["accountId"]
                return self._current_user_account_id

            error_msg = "Could not find accountId in user data"
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
                if "accountId" in user and (
                    user.get("displayName", "").lower() == username.lower()
                    or user.get("name", "").lower() == username.lower()
                    or user.get("emailAddress", "").lower() == username.lower()
                ):
                    return user["accountId"]
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
                    if "accountId" in user:
                        return user["accountId"]
            return None
        except Exception as e:
            logger.info(f"Error looking up user by permissions: {str(e)}")
            return None
