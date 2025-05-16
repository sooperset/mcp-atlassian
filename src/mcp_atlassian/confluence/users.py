"""Module for Confluence user operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class UsersMixin(ConfluenceClient):
    """Mixin for Confluence user operations."""

    def get_user_details_by_accountid(
        self, account_id: str, expand: str = None
    ) -> dict[str, Any]:
        """Get user details by account ID.

        Args:
            account_id: The account ID of the user.
            expand: Optional expand for get status of user. Possible param is "status". Results are "Active, Deactivated".

        Returns:
            User details as a dictionary.

        Raises:
            Various exceptions from the Atlassian API if user doesn't exist or if there are permission issues.
        """
        return self.confluence.get_user_details_by_accountid(account_id, expand)

    def get_user_details_by_username(
        self, username: str, expand: str = None
    ) -> dict[str, Any]:
        """Get user details by username.

        This is typically used for Confluence Server/DC instances where username
        might be used as an identifier.

        Args:
            username: The username of the user.
            expand: Optional expand for get status of user. Possible param is "status". Results are "Active, Deactivated".

        Returns:
            User details as a dictionary.

        Raises:
            Various exceptions from the Atlassian API if user doesn't exist or if there are permission issues.
        """
        return self.confluence.get_user_details_by_username(username, expand)

    def get_current_user_info(self) -> dict[str, Any]:
        """
        Retrieve details for the currently authenticated user by calling Confluence's '/rest/api/user/current' endpoint.

        Returns:
            dict[str, Any]: The user details as returned by the API.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails or the response is not valid user data.
        """
        try:
            user_data = self.confluence.get("rest/api/user/current")
            if not isinstance(user_data, dict):
                logger.error(
                    f"Confluence /rest/api/user/current endpoint returned non-dict data type: {type(user_data)}. "
                    f"Response text (partial): {str(user_data)[:500]}"
                )
                raise MCPAtlassianAuthenticationError(
                    "Confluence token validation failed: Did not receive valid JSON user data from /rest/api/user/current endpoint."
                )
            return user_data
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                logger.warning(
                    f"Confluence token validation failed with HTTP {http_err.response.status_code} for /rest/api/user/current."
                )
                raise MCPAtlassianAuthenticationError(
                    f"Confluence token validation failed: {http_err.response.status_code} from /rest/api/user/current"
                ) from http_err
            logger.error(
                f"HTTPError when calling Confluence /rest/api/user/current: {http_err}",
                exc_info=True,
            )
            raise MCPAtlassianAuthenticationError(
                f"Confluence token validation failed with HTTPError: {http_err}"
            ) from http_err
        except Exception as e:
            logger.error(
                f"Unexpected error fetching current Confluence user details: {e}",
                exc_info=True,
            )
            raise MCPAtlassianAuthenticationError(
                f"Confluence token validation failed: {e}"
            ) from e
