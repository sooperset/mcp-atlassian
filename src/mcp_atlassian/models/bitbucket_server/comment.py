"""Comment models for Bitbucket Server."""

from datetime import datetime, timezone
from typing import Any

from ..base import BaseModel
from .common import BitbucketServerUser


class BitbucketServerComment(BaseModel):
    """Bitbucket Server comment model."""

    id: int
    version: int | None = None
    text: str | None = None
    author: BitbucketServerUser | None = None
    created_date: datetime | None = None
    updated_date: datetime | None = None
    parent_id: int | None = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerComment":
        """Create comment model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerComment instance
        """
        author_data = data.get("author", {})

        # Convert timestamps to datetime objects
        created_date = None
        if created_timestamp := data.get("createdDate"):
            try:
                created_date = datetime.fromtimestamp(
                    created_timestamp / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError):
                pass

        updated_date = None
        if updated_timestamp := data.get("updatedDate"):
            try:
                updated_date = datetime.fromtimestamp(
                    updated_timestamp / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError):
                pass

        return cls(
            id=data.get("id"),
            version=data.get("version"),
            text=data.get("text"),
            author=BitbucketServerUser.from_raw(author_data) if author_data else None,
            created_date=created_date,
            updated_date=updated_date,
            parent_id=data.get("parent", {}).get("id") if data.get("parent") else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert comment to a simplified dictionary.

        Returns:
            Dictionary with simplified comment data
        """
        # Start with base fields, excluding None values
        result = {
            k: v
            for k, v in {
                "id": self.id,
                "text": self.text,
                "parent_id": self.parent_id,
            }.items()
            if v is not None
        }

        # Include dates as ISO strings if present
        if self.created_date:
            result["created_date"] = self.created_date.isoformat()
        if self.updated_date:
            result["updated_date"] = self.updated_date.isoformat()

        # Include nested objects if present
        if self.author:
            result["author"] = {
                k: v
                for k, v in {
                    "name": self.author.name,
                    "display_name": self.author.display_name,
                    "email_address": self.author.email_address,
                }.items()
                if v is not None
            }

        return result


class BitbucketServerCommentPage(BaseModel):
    """Bitbucket Server comment page model for paginated results."""

    start: int
    size: int
    limit: int
    is_last_page: bool
    comments: list[BitbucketServerComment]

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerCommentPage":
        """Create comment page model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerCommentPage instance
        """
        comments = []
        for comment_data in data.get("values", []):
            try:
                comments.append(BitbucketServerComment.from_raw(comment_data))
            except (ValueError, KeyError, TypeError) as e:
                # Skip invalid comments but log the error
                from ..utils.logging import get_logger

                logger = get_logger()
                logger.debug(f"Skipping invalid comment: {e}")

        return cls(
            start=data.get("start", 0),
            size=data.get("size", 0),
            limit=data.get("limit", 0),
            is_last_page=data.get("isLastPage", True),
            comments=comments,
        )
