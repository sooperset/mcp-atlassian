"""Common model classes for Bitbucket Server."""

from typing import Any

from ..base import BaseModel


class BitbucketServerUser(BaseModel):
    """Bitbucket Server user model."""

    id: int | None = None
    name: str | None = None
    display_name: str | None = None
    email_address: str | None = None
    active: bool | None = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerUser":
        """Create user model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerUser instance
        """
        return cls(
            id=data.get("id"),
            name=data.get("name"),
            display_name=data.get("displayName"),
            email_address=data.get("emailAddress"),
            active=data.get("active"),
        )


class BitbucketServerRepository(BaseModel):
    """Bitbucket Server repository model."""

    id: int | None = None
    slug: str | None = None
    name: str | None = None
    project_key: str | None = None
    project_name: str | None = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerRepository":
        """Create repository model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerRepository instance
        """
        project_data = data.get("project", {})
        return cls(
            id=data.get("id"),
            slug=data.get("slug"),
            name=data.get("name"),
            project_key=project_data.get("key"),
            project_name=project_data.get("name"),
        )


class BitbucketServerRef(BaseModel):
    """Bitbucket Server reference model (branch/tag)."""

    id: str | None = None
    display_id: str | None = None
    latest_commit: str | None = None
    repository: BitbucketServerRepository | None = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "BitbucketServerRef":
        """Create reference model from raw API data.

        Args:
            data: Raw API response

        Returns:
            BitbucketServerRef instance
        """
        repo_data = data.get("repository", {})
        return cls(
            id=data.get("id"),
            display_id=data.get("displayId"),
            latest_commit=data.get("latestCommit"),
            repository=BitbucketServerRepository.from_raw(repo_data)
            if repo_data
            else None,
        )
