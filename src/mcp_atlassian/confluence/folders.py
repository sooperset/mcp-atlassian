"""Module for Confluence folder operations.

Folders are a Confluence Cloud content type. They are created, read and
deleted through the v2 API; moves use the v1 content move endpoint, which
accepts folders as well as pages. The public REST API offers no way to
rename a folder.
"""

import logging

from ..models.confluence import ConfluenceFolder
from ..utils.decorators import handle_auth_errors
from .client import ConfluenceClient
from .v2_adapter import ConfluenceV2Adapter

logger = logging.getLogger("mcp-atlassian")

FOLDER_MOVE_POSITIONS = ("append", "before", "after")


class FoldersMixin(ConfluenceClient):
    """Mixin for Confluence Cloud folder operations."""

    def _folder_v2_adapter(self) -> ConfluenceV2Adapter:
        """Get a v2 API adapter for folder operations.

        Returns:
            ConfluenceV2Adapter bound to the authenticated session.

        Raises:
            ValueError: If the instance is Server/Data Center.
        """
        if not self.config.is_cloud:
            raise ValueError(
                "Folders are only available for Confluence Cloud. "
                "Server/Data Center instances do not support folders."
            )

        if self.config.auth_type == "oauth":
            base_url = self.confluence.url
        else:
            base_url = self.config.url
        return ConfluenceV2Adapter(
            session=self.confluence._session,
            base_url=base_url,
        )

    @handle_auth_errors("Confluence API")
    def create_folder(
        self,
        space_key: str,
        title: str,
        parent_id: str | None = None,
    ) -> ConfluenceFolder:
        """Create a folder in a Confluence Cloud space.

        Args:
            space_key: The key of the space to create the folder in.
            title: The title of the folder.
            parent_id: Optional parent page or folder ID. When omitted,
                Confluence places the folder under the space homepage.

        Returns:
            ConfluenceFolder model for the created folder.

        Raises:
            ValueError: If the instance is not Cloud or creation fails.
        """
        adapter = self._folder_v2_adapter()
        result = adapter.create_folder(
            space_key=space_key, title=title, parent_id=parent_id
        )
        return ConfluenceFolder.from_api_response(result, base_url=self.config.url)

    @handle_auth_errors("Confluence API")
    def get_folder(
        self, folder_id: str, include_children: bool = False
    ) -> ConfluenceFolder:
        """Get a Confluence Cloud folder by ID.

        Args:
            folder_id: The ID of the folder.
            include_children: When True, also fetch the folder's direct
                children (up to 250).

        Returns:
            ConfluenceFolder model for the folder.

        Raises:
            ValueError: If the instance is not Cloud or the folder cannot be
                retrieved.
        """
        adapter = self._folder_v2_adapter()
        folder = ConfluenceFolder.from_api_response(
            adapter.get_folder(folder_id), base_url=self.config.url
        )
        if include_children:
            children, has_more = adapter.get_folder_direct_children(folder_id)
            folder.children = children
            folder.children_has_more = has_more
        return folder

    @handle_auth_errors("Confluence API")
    def delete_folder(self, folder_id: str) -> None:
        """Delete a Confluence Cloud folder (moves it to the space trash).

        Args:
            folder_id: The ID of the folder to delete.

        Raises:
            ValueError: If the instance is not Cloud or deletion fails.
        """
        adapter = self._folder_v2_adapter()
        adapter.delete_folder(folder_id)

    @handle_auth_errors("Confluence API")
    def move_folder(
        self,
        folder_id: str,
        target_id: str,
        position: str = "append",
    ) -> ConfluenceFolder:
        """Move a Confluence Cloud folder relative to a page or folder.

        Args:
            folder_id: The ID of the folder to move.
            target_id: ID of the target page or folder.
            position: "append" (move inside the target), "before" or
                "after" (move next to the target as a sibling).

        Returns:
            ConfluenceFolder model reflecting the new location.

        Raises:
            ValueError: If the position is invalid, the instance is not
                Cloud, or the move fails.
        """
        if position not in FOLDER_MOVE_POSITIONS:
            raise ValueError(
                f"Invalid position '{position}'. "
                f"Must be one of: {', '.join(FOLDER_MOVE_POSITIONS)}."
            )

        adapter = self._folder_v2_adapter()
        adapter.move_page(page_id=folder_id, position=position, target_id=target_id)
        return ConfluenceFolder.from_api_response(
            adapter.get_folder(folder_id), base_url=self.config.url
        )
