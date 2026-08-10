"""Common models shared across AIO Tests entities."""

from typing import Any

from ..base import ApiModel


class AIOEntity(ApiModel):
    """A named, identified AIO Tests lookup value.

    Covers the ``ID``/``name``/``description`` shape used by case statuses,
    priorities, types, script types and automation statuses.
    """

    id: int | None = None
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
    is_archived: bool | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOEntity":
        """Create an entity from an AIO Tests API response.

        Args:
            data: Raw entity payload.
            **kwargs: Unused, accepted for interface compatibility.

        Returns:
            The parsed entity.
        """
        if not isinstance(data, dict):
            return cls()
        return cls(
            id=data.get("ID"),
            name=data.get("name"),
            description=data.get("description"),
            is_default=data.get("isDefault"),
            is_archived=data.get("isArchived"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the populated entity fields.
        """
        result: dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        if self.name is not None:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.is_default is not None:
            result["is_default"] = self.is_default
        if self.is_archived is not None:
            result["is_archived"] = self.is_archived
        return result


class AIOTag(ApiModel):
    """A tag defined for a Jira project in AIO Tests."""

    id: int | None = None
    name: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOTag":
        """Create a tag from an AIO Tests API response.

        Accepts both the bare ``Tag`` shape and the ``CaseTag`` wrapper returned
        on case details, which nests the tag under a ``tag`` key.

        Args:
            data: Raw tag payload.
            **kwargs: Unused, accepted for interface compatibility.

        Returns:
            The parsed tag.
        """
        if not isinstance(data, dict):
            return cls()
        if "tag" in data and isinstance(data["tag"], dict):
            data = data["tag"]
        return cls(id=data.get("ID"), name=data.get("name"))

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the tag ID and name.
        """
        result: dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        if self.name is not None:
            result["name"] = self.name
        return result


class AIOFolder(ApiModel):
    """A single AIO Tests folder without its children."""

    id: int | None = None
    name: str | None = None
    description: str | None = None
    parent_id: int | None = None
    path: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOFolder":
        """Create a folder from an AIO Tests API response.

        Args:
            data: Raw folder payload.
            **kwargs: Optional ``path`` giving the full folder path.

        Returns:
            The parsed folder.
        """
        if not isinstance(data, dict):
            return cls()
        return cls(
            id=data.get("ID"),
            name=data.get("name"),
            description=data.get("description"),
            parent_id=data.get("parentID"),
            path=kwargs.get("path"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the populated folder fields.
        """
        result: dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        if self.name is not None:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.path:
            result["path"] = self.path
        return result


class AIOFolderTree(AIOFolder):
    """An AIO Tests folder together with its descendants."""

    children: list["AIOFolderTree"] = []

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOFolderTree":
        """Create a folder tree from an AIO Tests API response.

        The API omits ``parentID`` on nested folders, so the parent ID and the
        full path are derived while walking the tree.

        Args:
            data: Raw folder payload, possibly containing a ``children`` list.
            **kwargs: Optional ``parent_path`` and ``parent_id`` for nested nodes.

        Returns:
            The parsed folder tree.
        """
        if not isinstance(data, dict):
            return cls()
        name = data.get("name") or ""
        parent_path = kwargs.get("parent_path") or ""
        path = f"{parent_path}/{name}" if parent_path else f"/{name}"
        folder = cls(
            id=data.get("ID"),
            name=data.get("name"),
            description=data.get("description"),
            parent_id=data.get("parentID", kwargs.get("parent_id")),
            path=path,
        )
        children = data.get("children") or []
        folder.children = [
            cls.from_api_response(child, parent_path=path, parent_id=folder.id)
            for child in children
            if isinstance(child, dict)
        ]
        return folder

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary including nested children.

        Returns:
            Dictionary with the folder fields and a ``children`` list.
        """
        result = super().to_simplified_dict()
        if self.children:
            result["children"] = [child.to_simplified_dict() for child in self.children]
        return result

    def flatten(self) -> list[AIOFolder]:
        """Flatten the tree into a list of folders with resolved paths.

        Returns:
            All folders in the tree, parents before children.
        """
        folders: list[AIOFolder] = [
            AIOFolder(
                id=self.id,
                name=self.name,
                description=self.description,
                parent_id=self.parent_id,
                path=self.path,
            )
        ]
        for child in self.children:
            folders.extend(child.flatten())
        return folders


AIOFolderTree.model_rebuild()
