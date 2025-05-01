"""
Confluence label models.
This module provides Pydantic models for Confluence page labels.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import (
    CONFLUENCE_DEFAULT_ID,
    EMPTY_STRING,
)

logger = logging.getLogger(__name__)


class ConfluenceLabel(ApiModel):
    """
    Model representing a Confluence label.
    """

    id: str = CONFLUENCE_DEFAULT_ID
    name: str = EMPTY_STRING
    prefix: str = "global"
    label: str = EMPTY_STRING
    type: str = "label"

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceLabel":
        """
        Create a ConfluenceLabel from a Confluence API response.

        Args:
            data: The label data from the Confluence API

        Returns:
            A ConfluenceLabel instance
        """
        if not data:
            return cls()

        return cls(
            id=str(data.get("id", CONFLUENCE_DEFAULT_ID)),
            name=data.get("name", EMPTY_STRING),
            prefix=data.get("prefix", "global"),
            label=data.get("label", EMPTY_STRING),
            type=data.get("type", "label"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "name": self.name,
            "prefix": self.prefix,
            "label": self.label,
        }

        return result
