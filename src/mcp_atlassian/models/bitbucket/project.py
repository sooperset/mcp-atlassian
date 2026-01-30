"""
Bitbucket project models.

This module provides Pydantic models for Bitbucket projects.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import EMPTY_STRING, UNKNOWN

logger = logging.getLogger(__name__)


class BitbucketProject(ApiModel):
    """
    Model representing a Bitbucket project.

    This model contains the basic information about a Bitbucket project,
    supporting both Cloud and Server/Data Center formats.
    """

    key: str = EMPTY_STRING
    name: str = UNKNOWN
    description: str | None = None
    is_private: bool = False
    owner_display_name: str | None = None
    uuid: str | None = None  # Cloud only
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], is_cloud: bool = True, **kwargs: Any
    ) -> "BitbucketProject":
        """
        Create a BitbucketProject from a Bitbucket API response.

        Args:
            data: The project data from the Bitbucket API
            is_cloud: Whether the data is from Bitbucket Cloud or Server

        Returns:
            A BitbucketProject instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        if is_cloud:
            # Bitbucket Cloud format
            key = data.get("key", EMPTY_STRING)
            name = data.get("name", UNKNOWN)
            description = data.get("description")
            is_private = data.get("is_private", False)
            uuid = data.get("uuid")
            links = data.get("links")

            # Extract owner information
            owner_display_name = None
            if owner := data.get("owner"):
                if isinstance(owner, dict):
                    owner_display_name = owner.get("display_name")

            return cls(
                key=key,
                name=name,
                description=description,
                is_private=is_private,
                owner_display_name=owner_display_name,
                uuid=uuid,
                links=links,
            )

        else:
            # Bitbucket Server/Data Center format
            key = data.get("key", EMPTY_STRING)
            name = data.get("name", UNKNOWN)
            description = data.get("description")
            is_private = not data.get("public", True)
            links = data.get("links")

            return cls(
                key=key,
                name=name,
                description=description,
                is_private=is_private,
                links=links,
            )

    def to_simplified_dict(self) -> dict[str, Any]:
        """
        Convert the model to a simplified dictionary for API responses.

        Returns:
            A simplified dictionary representation
        """
        result: dict[str, Any] = {
            "key": self.key,
            "name": self.name,
        }

        if self.description:
            result["description"] = self.description

        result["is_private"] = self.is_private

        if self.owner_display_name:
            result["owner"] = self.owner_display_name

        if self.uuid:
            result["uuid"] = self.uuid

        if self.links:
            result["links"] = self.links

        return result
