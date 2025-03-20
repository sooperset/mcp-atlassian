"""Module for Confluence space operations."""

import asyncio
import logging
from typing import Any, cast

import requests

from ..utils import cached
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class SpacesMixin(ConfluenceClient):
    """Mixin for Confluence space operations."""

    @cached("confluence_spaces", 3600)  # Cache for 1 hour
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
        # Cast the return value to the expected type
        return cast(dict[str, object], spaces)

    @cached("confluence_user_contributed_spaces", 1800)  # Cache for 30 minutes
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

                # Only add if we found a space key and it's not already in our results
                if space_key and space_key not in spaces:
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

    def get_multiple_spaces_parallel(self, space_keys: list[str]) -> dict[str, Any]:
        """
        Get information for multiple spaces in parallel.

        Args:
            space_keys: List of space keys to fetch

        Returns:
            Dictionary mapping space keys to space information
        """

        # Helper function to get a specific space
        def get_space(space_key: str) -> dict[str, Any]:
            try:
                return self.confluence.get_space(space_key)
            except Exception as e:
                logger.warning(f"Error fetching space {space_key}: {e}")
                return None

        # Prepare data for parallel requests
        request_data = [(get_space, [key], {}) for key in space_keys]

        # Execute requests in parallel
        results = self.parallel_requests(request_data)

        # Build the result dictionary
        spaces_dict = {}
        for i, space_key in enumerate(space_keys):
            spaces_dict[space_key] = results[i]

        return spaces_dict

    async def get_multiple_spaces_async(self, space_keys: list[str]) -> dict[str, Any]:
        """
        Get information for multiple spaces asynchronously.

        Args:
            space_keys: List of space keys to fetch

        Returns:
            Dictionary mapping space keys to space information
        """

        # Helper function to get a specific space
        def get_space(space_key: str) -> dict[str, Any]:
            try:
                return self.confluence.get_space(space_key)
            except Exception as e:
                logger.warning(f"Error fetching space {space_key}: {e}")
                return None

        # Create tasks for each space
        tasks = []
        for key in space_keys:
            tasks.append(self.async_request(get_space, key))

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build the result dictionary
        spaces_dict = {}
        for i, space_key in enumerate(space_keys):
            result = results[i]
            if isinstance(result, Exception):
                logger.warning(f"Error fetching space {space_key}: {str(result)}")
                spaces_dict[space_key] = None
            else:
                spaces_dict[space_key] = result

        return spaces_dict
