"""Pull request models for Bitbucket Server."""

from datetime import datetime, timezone
from typing import Any, cast

from ..base import BaseModel
from .common import BitbucketServerRef, BitbucketServerRepository, BitbucketServerUser


class BitbucketServerPullRequestReviewer(BaseModel):
    """Bitbucket Server pull request reviewer model."""

    user: BitbucketServerUser | None = None
    status: str | None = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerPullRequestReviewer":
        """Create reviewer model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerPullRequestReviewer instance
        """
        user_data = data.get("user", {})
        return cls(
            user=BitbucketServerUser.from_raw(user_data) if user_data else None,
            status=data.get("status"),
        )


class BitbucketServerPullRequest(BaseModel):
    """Bitbucket Server pull request model."""

    id: int
    version: int | None = None
    title: str | None = None
    description: str | None = None
    state: str | None = None
    open: bool | None = None
    closed: bool | None = None
    created_date: datetime | None = None
    updated_date: datetime | None = None
    from_ref: BitbucketServerRef | None = None
    to_ref: BitbucketServerRef | None = None
    author: BitbucketServerUser | None = None
    reviewers: list[BitbucketServerPullRequestReviewer] | None = None
    repository: BitbucketServerRepository | None = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerPullRequest":
        """Create pull request model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerPullRequest instance
        """
        from_ref_data = data.get("fromRef", {})
        to_ref_data = data.get("toRef", {})
        author_data = data.get("author", {})
        repo_data = data.get("toRef", {}).get("repository", {})

        reviewers_list = []
        for reviewer_data in data.get("reviewers", []):
            reviewers_list.append(
                BitbucketServerPullRequestReviewer.from_raw(reviewer_data)
            )

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

        pr_id = cast(int, data.get("id"))  # Cast to satisfy mypy
        if not isinstance(pr_id, int):
            error_msg = f"Pull request ID must be an integer, got {pr_id}"
            raise ValueError(error_msg)

        return cls(
            id=pr_id,
            version=data.get("version"),
            title=data.get("title"),
            description=data.get("description"),
            state=data.get("state"),
            open=data.get("open"),
            closed=data.get("closed"),
            created_date=created_date,
            updated_date=updated_date,
            from_ref=BitbucketServerRef.from_raw(from_ref_data)
            if from_ref_data
            else None,
            to_ref=BitbucketServerRef.from_raw(to_ref_data) if to_ref_data else None,
            author=BitbucketServerUser.from_raw(author_data) if author_data else None,
            reviewers=reviewers_list,
            repository=BitbucketServerRepository.from_raw(repo_data)
            if repo_data
            else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert pull request to a simplified dictionary.

        Returns:
            Dictionary with simplified pull request data
        """
        # Start with base fields, excluding None values
        result: dict[str, Any] = {
            k: v
            for k, v in {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "state": self.state,
                "open": self.open,
                "closed": self.closed,
            }.items()
            if v is not None
        }

        # Include dates as ISO strings if present
        if self.created_date:
            result["created_date"] = self.created_date.isoformat()
        if self.updated_date:
            result["updated_date"] = self.updated_date.isoformat()

        # Include nested objects if present
        if self.from_ref:
            result["from_ref"] = {
                k: v
                for k, v in {
                    "id": self.from_ref.id,
                    "display_id": self.from_ref.display_id,
                    "latest_commit": self.from_ref.latest_commit,
                }.items()
                if v is not None
            }

        if self.to_ref:
            result["to_ref"] = {
                k: v
                for k, v in {
                    "id": self.to_ref.id,
                    "display_id": self.to_ref.display_id,
                    "latest_commit": self.to_ref.latest_commit,
                }.items()
                if v is not None
            }

        if self.author:
            result["author"] = {
                k: v
                for k, v in {
                    "id": self.author.id,
                    "name": self.author.name,
                    "display_name": self.author.display_name,
                    "email_address": self.author.email_address,
                }.items()
                if v is not None
            }

        if self.reviewers:
            result["reviewers"] = []
            for reviewer in self.reviewers:
                if not reviewer:
                    continue

                reviewer_dict: dict[str, Any] = {}
                if reviewer.status:
                    reviewer_dict["status"] = reviewer.status

                if reviewer.user:
                    reviewer_dict["user"] = {
                        k: v
                        for k, v in {
                            "name": reviewer.user.name,
                            "display_name": reviewer.user.display_name,
                        }.items()
                        if v is not None
                    }

                if reviewer_dict:  # Only add if we have data
                    result["reviewers"].append(reviewer_dict)

        return result
