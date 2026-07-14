"""Module for Jira user operations."""

import logging
import re
from typing import TYPE_CHECKING, TypeVar

from requests.exceptions import HTTPError
from unidecode import unidecode

from mcp_atlassian.models.jira.common import JiraUser
from mcp_atlassian.utils.decorators import handle_auth_errors

from .client import JiraClient

if TYPE_CHECKING:
    from mcp_atlassian.models.jira.common import JiraUser

JiraUserType = TypeVar("JiraUserType", bound="JiraUser")

logger = logging.getLogger("mcp-jira")


def normalize_text(text: str | None) -> str:
    """Normalize text for case-insensitive Unicode comparison.

    Uses unidecode for ASCII transliteration to handle characters like
    Polish "ł" matching ASCII "l", then casefold for case-insensitivity.

    Args:
        text: The text to normalize.

    Returns:
        Normalized ASCII text suitable for comparison.
    """
    if not text:
        return ""
    # Transliterate to ASCII (ł→l, ó→o, etc.) then casefold for case-insensitivity
    return unidecode(text).casefold()


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
        # If it looks like an account ID already, return it.
        # Known unprefixed Cloud account IDs use a legacy 24-char hex format
        # (e.g. "5b10ac8d82e05b22cc7d4ef5") or a "<digits>:<uuid>" format
        # (e.g. "712020:f653aab5-cc61-4c57-8fa8-f7d73b94499d").
        # An explicit "accountid:" prefix is also accepted, matching the
        # create_issue/update_issue tool schemas and supporting opaque IDs.
        if assignee.startswith("accountid:"):
            return assignee[len("accountid:") :]
        if re.fullmatch(r"[0-9a-fA-F]{24}", assignee):
            return assignee
        if re.fullmatch(r"\d+:[0-9a-fA-F][0-9a-fA-F-]{7,}", assignee):
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

            search_norm = normalize_text(username)
            for user in response:
                if (
                    normalize_text(user.get("displayName", "")) == search_norm
                    or normalize_text(user.get("name", "")) == search_norm
                    or normalize_text(user.get("emailAddress", "")) == search_norm
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

    def _resolve_server_dc_user_params(self, email: str) -> dict[str, str] | None:
        """Resolve email to Server/DC user API params via search.

        Unlike _lookup_user_directly which returns a bare string,
        this returns the correct API parameter dict, avoiding the
        need to guess whether the value is a username or key.

        Args:
            email: Email address to resolve.

        Returns:
            Dict with 'username' or 'key' param, or None if not found.
        """
        try:
            response = self.jira.user_find_by_user_string(
                username=email, start=0, limit=1
            )
            if not isinstance(response, list):
                return None

            search_norm = normalize_text(email)
            for user in response:
                if (
                    normalize_text(user.get("displayName", "")) == search_norm
                    or normalize_text(user.get("name", "")) == search_norm
                    or normalize_text(user.get("emailAddress", "")) == search_norm
                ):
                    if user.get("name"):
                        return {"username": user["name"]}
                    elif user.get("key"):
                        return {"key": user["key"]}
            return None
        except Exception as e:
            logger.info(f"Error resolving server user by email: {e}")
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

            # Use the configured Jira session so that cert, proxy, and all
            # other session-level settings (mTLS, custom headers, SSL adapters)
            # are applied consistently regardless of auth type.
            response = self.jira._session.get(url, params=params)

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
                # /rest/api/2/user?username=email won't match by email on Server/DC.
                # Use /rest/api/2/user/search first to resolve email → actual username/key.
                resolved_params = self._resolve_server_dc_user_params(identifier)
                if resolved_params:
                    api_kwargs.update(resolved_params)
                    param_name = next(iter(resolved_params))
                    logger.debug(
                        f"Resolved email '{identifier}' to {param_name}="
                        f"'{resolved_params[param_name]}' (Server/DC)"
                    )
                else:
                    # Fallback: try email as username directly (works if login name IS the email)
                    api_kwargs["username"] = identifier
                    logger.debug(
                        f"Could not resolve email '{identifier}' via search, "
                        f"trying as username directly (Server/DC)"
                    )
            else:
                # Non-email: use username= (safe default for Server/DC 7.x+)
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

    @handle_auth_errors("Jira API")
    def search_assignable_users(
        self,
        query: str,
        project_key: str | None = None,
        issue_key: str | None = None,
        limit: int = 20,
    ) -> list["JiraUser"]:
        """
        Search Jira users assignable in a given project or issue.

        Uses GET /rest/api/2/user/assignable/search — the project-scoped
        assignee picker. Unlike /user/search (needs global "Browse Users")
        or /user/picker (often locked down on hardened DC instances), this
        endpoint only requires the caller to be able to assign issues in
        the target project / browse the target issue, which any bot that
        already works with that project will have.

        Exactly one of ``project_key`` or ``issue_key`` must be provided.

        Args:
            query: Free-form text matched against username, displayName,
                and emailAddress (case-insensitive substring on Server/DC).
            project_key: Project key (e.g. "DT") to scope the search.
            issue_key: Issue key (e.g. "DT-779") to scope the search.
            limit: Maximum number of users to return (1..1000, clamped).

        Returns:
            List of JiraUser models (possibly empty). Order is preserved
            from the API.

        Raises:
            ValueError: If exactly one of project_key or issue_key is not provided.
            MCPAtlassianAuthenticationError: If authentication fails (decorator).
            Exception: For other API errors.
        """
        if bool(project_key) == bool(issue_key):
            raise ValueError(
                "Exactly one of project_key or issue_key must be provided."
            )

        limit = max(1, min(int(limit or 20), 1000))
        url = self.jira.resource_url("user/assignable/search")
        query_param = "query" if self.config.is_cloud else "username"
        params: dict[str, str | int] = {
            query_param: query,
            "maxResults": limit,
            "startAt": 0,
        }
        if issue_key:
            params["issueKey"] = issue_key
        elif project_key is not None:
            params["project"] = project_key

        try:
            data = self.jira.get(url, params=params)
        except HTTPError as http_err:
            logger.warning(
                f"jira_search_assignable_users HTTPError for query={query!r}: {http_err}"
            )
            raise
        except Exception as e:
            logger.exception(f"jira_search_assignable_users failed for query={query!r}")
            raise Exception(f"Error searching users for query '{query}': {e}") from e

        if not isinstance(data, list):
            logger.error(
                f"Unexpected response type from /user/assignable/search: {type(data)}"
            )
            return []

        users: list[JiraUser] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            users.append(JiraUser.from_api_response(raw))
        return users

    @handle_auth_errors("Jira API")
    def get_user_profile_by_identifier(self, identifier: str) -> "JiraUser":
        """
        Retrieve Jira user profile information by identifier.

        Args:
            identifier: User identifier (accountId, username,
                key, or email).

        Returns:
            JiraUser model with profile information.

        Raises:
            ValueError: If the user cannot be found or
                identifier cannot be resolved.
            MCPAtlassianAuthenticationError: If authentication
                fails.
            Exception: For other API errors.
        """
        # Handle 'me' as a special case — resolve to current user's account ID
        if identifier.lower() == "me":
            resolved_id = self.get_current_user_account_id()
            return self.get_user_profile_by_identifier(resolved_id)

        api_kwargs = self._determine_user_api_params(identifier)

        try:
            logger.debug(f"Calling self.jira.user() with parameters: {api_kwargs}")
            user_data = self.jira.user(**api_kwargs)
            if not isinstance(user_data, dict):
                logger.error(
                    f"User lookup for '{identifier}'"
                    " returned unexpected type:"
                    f" {type(user_data)}."
                    f" Data: {user_data}"
                )
                raise ValueError(f"User '{identifier}' not found or lookup failed.")
            return JiraUser.from_api_response(user_data)
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code == 404:
                raise ValueError(f"User '{identifier}' not found.") from http_err
            raise  # decorator handles 401/403
        except Exception as e:
            logger.exception(
                f"Unexpected error getting/processing user profile for '{identifier}':"
            )
            raise Exception(
                f"Error processing user profile for '{identifier}': {str(e)}"
            ) from e
