"""
Bitbucket pull request models.

This module provides Pydantic models for Bitbucket pull requests.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import EMPTY_STRING, UNKNOWN

logger = logging.getLogger(__name__)


class BitbucketPullRequest(ApiModel):
    """
    Model representing a Bitbucket pull request.

    This model contains information about a Bitbucket pull request,
    supporting both Cloud and Server/Data Center formats.
    """

    id: int | str = 0
    title: str = UNKNOWN
    description: str | None = None
    state: str = EMPTY_STRING
    source_branch: str = EMPTY_STRING
    destination_branch: str = EMPTY_STRING
    author_display_name: str | None = None
    created_on: str | None = None
    updated_on: str | None = None
    links: dict[str, Any] | None = None
    reviewers: list[str] | None = None
    participants_count: int = 0

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], is_cloud: bool = True, **kwargs: Any
    ) -> "BitbucketPullRequest":
        """
        Create a BitbucketPullRequest from a Bitbucket API response.

        Args:
            data: The pull request data from the Bitbucket API
            is_cloud: Whether the data is from Bitbucket Cloud or Server

        Returns:
            A BitbucketPullRequest instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        if is_cloud:
            # Bitbucket Cloud format
            pr_id = data.get("id", 0)
            title = data.get("title", UNKNOWN)
            description = data.get("description")
            state = data.get("state", EMPTY_STRING)
            created_on = data.get("created_on")
            updated_on = data.get("updated_on")
            links = data.get("links")

            # Extract source and destination branch names
            source_branch = EMPTY_STRING
            if source := data.get("source"):
                if isinstance(source, dict) and (branch := source.get("branch")):
                    if isinstance(branch, dict):
                        source_branch = branch.get("name", EMPTY_STRING)

            destination_branch = EMPTY_STRING
            if destination := data.get("destination"):
                if isinstance(destination, dict):
                    branch = destination.get("branch")
                    if branch and isinstance(branch, dict):
                        destination_branch = branch.get("name", EMPTY_STRING)

            # Extract author information
            author_display_name = None
            if author := data.get("author"):
                if isinstance(author, dict):
                    author_display_name = author.get("display_name")

            # Extract reviewers
            reviewers_list = []
            if reviewers := data.get("reviewers"):
                if isinstance(reviewers, list):
                    for reviewer in reviewers:
                        if isinstance(reviewer, dict):
                            display_name = reviewer.get("display_name")
                            if display_name:
                                reviewers_list.append(display_name)

            participants_count = data.get("participants", [])
            if isinstance(participants_count, list):
                participants_count = len(participants_count)
            else:
                participants_count = 0

            return cls(
                id=pr_id,
                title=title,
                description=description,
                state=state,
                source_branch=source_branch,
                destination_branch=destination_branch,
                author_display_name=author_display_name,
                created_on=created_on,
                updated_on=updated_on,
                links=links,
                reviewers=reviewers_list if reviewers_list else None,
                participants_count=participants_count,
            )

        else:
            # Bitbucket Server/Data Center format
            pr_id = data.get("id", 0)
            title = data.get("title", UNKNOWN)
            description = data.get("description")
            state = data.get("state", EMPTY_STRING)
            created_on = data.get("createdDate")
            updated_on = data.get("updatedDate")
            links = data.get("links")

            # Extract source and destination branch names
            source_branch = EMPTY_STRING
            if from_ref := data.get("fromRef"):
                if isinstance(from_ref, dict):
                    # Extract branch name from ref ID (refs/heads/branch-name)
                    ref_id = from_ref.get("id", "")
                    if ref_id.startswith("refs/heads/"):
                        source_branch = ref_id.replace("refs/heads/", "")

            destination_branch = EMPTY_STRING
            if to_ref := data.get("toRef"):
                if isinstance(to_ref, dict):
                    # Extract branch name from ref ID (refs/heads/branch-name)
                    ref_id = to_ref.get("id", "")
                    if ref_id.startswith("refs/heads/"):
                        destination_branch = ref_id.replace("refs/heads/", "")

            # Extract author information
            author_display_name = None
            if author := data.get("author"):
                if isinstance(author, dict) and (user := author.get("user")):
                    if isinstance(user, dict):
                        author_display_name = user.get("displayName")

            # Extract reviewers
            reviewers_list = []
            if reviewers := data.get("reviewers"):
                if isinstance(reviewers, list):
                    for reviewer in reviewers:
                        if isinstance(reviewer, dict):
                            user = reviewer.get("user")
                            if user and isinstance(user, dict):
                                display_name = user.get("displayName")
                                if display_name:
                                    reviewers_list.append(display_name)

            participants_count = data.get("participants", [])
            if isinstance(participants_count, list):
                participants_count = len(participants_count)
            else:
                participants_count = 0

            # Convert timestamps to ISO format if they're numbers
            if isinstance(created_on, int):
                from datetime import datetime, timezone

                created_on = datetime.fromtimestamp(
                    created_on / 1000, tz=timezone.utc
                ).isoformat()
            if isinstance(updated_on, int):
                from datetime import datetime, timezone

                updated_on = datetime.fromtimestamp(
                    updated_on / 1000, tz=timezone.utc
                ).isoformat()

            return cls(
                id=pr_id,
                title=title,
                description=description,
                state=state,
                source_branch=source_branch,
                destination_branch=destination_branch,
                author_display_name=author_display_name,
                created_on=created_on,
                updated_on=updated_on,
                links=links,
                reviewers=reviewers_list if reviewers_list else None,
                participants_count=participants_count,
            )

    def to_simplified_dict(self) -> dict[str, Any]:
        """
        Convert the model to a simplified dictionary for API responses.

        Returns:
            A simplified dictionary representation
        """
        result: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "state": self.state,
            "source_branch": self.source_branch,
            "destination_branch": self.destination_branch,
        }

        if self.description:
            result["description"] = self.description

        if self.author_display_name:
            result["author"] = self.author_display_name

        if self.created_on:
            result["created_on"] = self.created_on

        if self.updated_on:
            result["updated_on"] = self.updated_on

        if self.reviewers:
            result["reviewers"] = self.reviewers

        if self.participants_count > 0:
            result["participants_count"] = self.participants_count

        if self.links:
            result["links"] = self.links

        return result
