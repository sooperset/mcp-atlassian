"""Module for AIO Tests folder operations."""

import logging
from typing import Any

from ..models.aio import AIOFolder, AIOFolderTree
from .client import AIOClient
from .constants import FOLDER_ENTITY_TYPES

logger = logging.getLogger("mcp-aio")


def normalize_folder_path(folder_path: str) -> list[str]:
    """Split a folder path into its individual folder names.

    Args:
        folder_path: Path such as ``/Release 1.0/Regression`` or a single name.

    Returns:
        The folder names in top-down order.

    Raises:
        ValueError: If the path contains no usable folder name.
    """
    names = [part.strip() for part in folder_path.split("/")]
    names = [name for name in names if name]
    if not names:
        raise ValueError("Folder path must contain at least one folder name")
    return names


class FoldersMixin(AIOClient):
    """Mixin for AIO Tests folder operations."""

    _folder_tree_cache: dict[tuple[str, str], list[AIOFolderTree]]

    @staticmethod
    def _validate_folder_type(folder_type: str) -> str:
        """Validate the folder entity type.

        Args:
            folder_type: One of ``testcase``, ``testcycle`` or ``testset``.

        Returns:
            The validated folder type.

        Raises:
            ValueError: If the folder type is not supported.
        """
        if folder_type not in FOLDER_ENTITY_TYPES:
            raise ValueError(
                f"Invalid folder type '{folder_type}'. Expected one of: "
                f"{', '.join(FOLDER_ENTITY_TYPES)}"
            )
        return folder_type

    def get_folder_hierarchy(
        self,
        project_key: str,
        folder_type: str = "testcase",
        *,
        refresh: bool = False,
    ) -> list[AIOFolderTree]:
        """Retrieve the folder tree of a project.

        Args:
            project_key: Jira project key or ID.
            folder_type: Folder tree to read: ``testcase``, ``testcycle`` or
                ``testset``.
            refresh: Bypass the per-instance cache.

        Returns:
            The root folders, each carrying its descendants and full path.
        """
        folder_type = self._validate_folder_type(folder_type)
        cache = getattr(self, "_folder_tree_cache", None)
        if cache is None:
            cache = {}
            self._folder_tree_cache = cache
        cache_key = (str(project_key), folder_type)
        if not refresh and cache_key in cache:
            return cache[cache_key]

        response = self.get(self.project_path(project_key, folder_type, "folder"))
        folders = [
            AIOFolderTree.from_api_response(item)
            for item in (response or [])
            if isinstance(item, dict)
        ]
        cache[cache_key] = folders
        return folders

    def flatten_folders(
        self,
        project_key: str,
        folder_type: str = "testcase",
        *,
        refresh: bool = False,
    ) -> list[AIOFolder]:
        """Retrieve the folder tree flattened into a list with full paths.

        Args:
            project_key: Jira project key or ID.
            folder_type: Folder tree to read.
            refresh: Bypass the per-instance cache.

        Returns:
            Every folder in the tree, parents before children.
        """
        folders: list[AIOFolder] = []
        for root in self.get_folder_hierarchy(
            project_key, folder_type, refresh=refresh
        ):
            folders.extend(root.flatten())
        return folders

    def find_folder(
        self,
        project_key: str,
        folder_path: str,
        folder_type: str = "testcase",
        *,
        refresh: bool = False,
    ) -> AIOFolder | None:
        """Find a folder by full path, or by name when the name is unique.

        Args:
            project_key: Jira project key or ID.
            folder_path: Full path such as ``/Regression/Checkout``, or a folder
                name.
            folder_type: Folder tree to search.
            refresh: Bypass the per-instance cache.

        Returns:
            The matching folder, or None when no folder matches.

        Raises:
            ValueError: If a bare name matches more than one folder.
        """
        names = normalize_folder_path(folder_path)
        wanted_path = "/" + "/".join(names)
        folders = self.flatten_folders(project_key, folder_type, refresh=refresh)

        for folder in folders:
            if (folder.path or "").lower() == wanted_path.lower():
                return folder
        if len(names) > 1:
            return None

        matches = [
            folder
            for folder in folders
            if (folder.name or "").lower() == names[0].lower()
        ]
        if not matches:
            return None
        if len(matches) > 1:
            paths = ", ".join(str(folder.path) for folder in matches)
            raise ValueError(
                f"Folder name '{names[0]}' is ambiguous in project "
                f"'{project_key}'. Use a full path. Matches: {paths}"
            )
        return matches[0]

    def create_folder(
        self,
        project_key: str,
        folder_path: str,
        folder_type: str = "testcase",
        parent_folder_id: int | None = None,
    ) -> AIOFolder:
        """Create a folder hierarchy, returning the leaf folder.

        The AIO Tests API is get-or-create: existing folders in the path are
        reused and only the missing ones are created.

        Args:
            project_key: Jira project key or ID.
            folder_path: Folder name, or a path such as
                ``/Release 1.0/Regression/Checkout`` to create nested folders.
            folder_type: Folder tree to create in: ``testcase``, ``testcycle`` or
                ``testset``.
            parent_folder_id: Optional existing folder to create the path under.
                Omit to create from the top level.

        Returns:
            The leaf folder of the created (or already existing) hierarchy.
        """
        folder_type = self._validate_folder_type(folder_type)
        names = normalize_folder_path(folder_path)
        payload: dict[str, Any] = {"folderHierarchy": names}
        if parent_folder_id is not None:
            payload["baseFolderId"] = parent_folder_id

        response = self.put(
            self.project_path(project_key, folder_type, "folder", "hierarchy"),
            json=payload,
        )
        # The tree changed, so drop the cached copy for this project.
        cache = getattr(self, "_folder_tree_cache", None)
        if cache is not None:
            cache.pop((str(project_key), folder_type), None)

        folder = AIOFolder.from_api_response(
            response if isinstance(response, dict) else {}
        )
        if folder.id is not None and not folder.path:
            resolved = next(
                (
                    item
                    for item in self.flatten_folders(project_key, folder_type)
                    if item.id == folder.id
                ),
                None,
            )
            if resolved is not None:
                folder.path = resolved.path
                folder.parent_id = resolved.parent_id
        return folder

    def resolve_folder_id(
        self,
        project_key: str,
        folder: Any,
        folder_type: str = "testcase",
        *,
        create_missing: bool = False,
    ) -> int | None:
        """Resolve a folder given as an ID, a name or a path to its numeric ID.

        Args:
            project_key: Jira project key or ID.
            folder: Numeric folder ID, numeric string, folder name or path.
            folder_type: Folder tree to search.
            create_missing: Create the folder hierarchy when it does not exist.

        Returns:
            The folder ID, or None when no folder was given.

        Raises:
            ValueError: If the folder does not exist and ``create_missing`` is
                False.
        """
        if folder is None or (isinstance(folder, str) and not folder.strip()):
            return None
        if isinstance(folder, int) and not isinstance(folder, bool):
            return folder
        text = str(folder).strip()
        if text.isdigit():
            return int(text)

        found = self.find_folder(project_key, text, folder_type)
        if found is not None and found.id is not None:
            return found.id
        if not create_missing:
            raise ValueError(
                f"Folder '{text}' was not found in project '{project_key}'. "
                "Create it first with aio_create_folder, or pass a folder ID."
            )
        created = self.create_folder(project_key, text, folder_type)
        return created.id
