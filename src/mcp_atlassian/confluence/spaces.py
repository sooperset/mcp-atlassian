"""Module for Confluence space operations."""

import logging
from typing import cast

import requests

from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class SpacesMixin(ConfluenceClient):
    """Mixin for Confluence space operations."""

    def get_spaces(self, start: int = 0, limit: int = 10) -> dict[str, object]:
        """
        Get all available spaces.

        Args:
            start: The starting index for pagination
            limit: Maximum number of spaces to return

        Returns:
            Dictionary containing space information with results and metadata
        """
        spaces = self.confluence.get_all_spaces(start=start, limit=limit)
        spaces_result = cast(dict[str, object], spaces)
        allowed_spaces = self._get_allowed_spaces()
        if allowed_spaces is None or not isinstance(spaces_result, dict):
            return spaces_result

        results = spaces_result.get("results")
        if not isinstance(results, list):
            return spaces_result

        filtered_results = [
            space
            for space in results
            if isinstance(space, dict)
            and str(space.get("key", "")).strip().upper() in allowed_spaces
        ]
        filtered_response = dict(spaces_result)
        filtered_response["results"] = filtered_results
        if "size" in filtered_response:
            filtered_response["size"] = len(filtered_results)
        return filtered_response

    def get_user_contributed_spaces(self, limit: int = 250) -> dict:
        """
        Get spaces the current user has contributed to.

        Args:
            limit: Maximum number of results to return

        Returns:
            Dictionary of space keys to space information
        """
        try:
            # Use CQL to find content the user has contributed to
            cql = "contributor = currentUser() order by lastmodified DESC"
            results = self.confluence.cql(cql=cql, limit=limit)

            # Extract and deduplicate spaces
            spaces = {}
            for result in results.get("results", []):
                space_key = None
                space_name = None

                # Try to extract space from container
                if "resultGlobalContainer" in result:
                    container = result.get("resultGlobalContainer", {})
                    space_name = container.get("title")
                    display_url = container.get("displayUrl", "")
                    if display_url and "/spaces/" in display_url:
                        space_key = display_url.split("/spaces/")[1].split("/")[0]

                # Try to extract from content expandable
                if (
                    not space_key
                    and "content" in result
                    and "_expandable" in result["content"]
                ):
                    expandable = result["content"].get("_expandable", {})
                    space_path = expandable.get("space", "")
                    if space_path and space_path.startswith("/rest/api/space/"):
                        space_key = space_path.split("/rest/api/space/")[1]

                # Try to extract from URL
                if not space_key and "url" in result:
                    url = result.get("url", "")
                    if url and url.startswith("/spaces/"):
                        space_key = url.split("/spaces/")[1].split("/")[0]

                allowed_spaces = self._get_allowed_spaces()
                if (
                    space_key
                    and (
                        allowed_spaces is None
                        or space_key.strip().upper() in allowed_spaces
                    )
                    and space_key not in spaces
                ):
                    # Add some defaults if we couldn't extract all fields
                    space_name = space_name or f"Space {space_key}"
                    spaces[space_key] = {"key": space_key, "name": space_name}

            return spaces

        except KeyError as e:
            logger.error(f"Missing key in Confluence spaces data: {str(e)}")
            return {}
        except ValueError as e:
            logger.error(f"Invalid value in Confluence spaces: {str(e)}")
            return {}
        except TypeError as e:
            logger.error(f"Type error when processing Confluence spaces: {str(e)}")
            return {}
        except requests.RequestException as e:
            logger.error(f"Network error when fetching spaces: {str(e)}")
            return {}
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Unexpected error fetching Confluence spaces: {str(e)}")
            logger.debug("Full exception details for Confluence spaces:", exc_info=True)
            return {}
