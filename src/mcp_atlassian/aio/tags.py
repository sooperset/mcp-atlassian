"""Module for AIO Tests tag operations."""

import logging
from typing import Any

from ..models.aio import AIOTag
from .client import AIOClient

logger = logging.getLogger("mcp-aio")


class TagsMixin(AIOClient):
    """Mixin for AIO Tests tag operations."""

    def get_tags(self, project_key: str) -> list[AIOTag]:
        """Retrieve every tag defined for a project.

        Args:
            project_key: Jira project key or ID.

        Returns:
            The tags configured in AIO Tests for the project.
        """
        response = self.get(self.project_path(project_key, "tag"))
        return [
            AIOTag.from_api_response(item)
            for item in (response or [])
            if isinstance(item, dict)
        ]

    def create_tags(self, project_key: str, names: list[str]) -> list[AIOTag]:
        """Create tags in a project.

        Args:
            project_key: Jira project key or ID.
            names: Names of the tags to create.

        Returns:
            The newly created tags.
        """
        response = self.post(
            self.project_path(project_key, "tag"),
            json=[{"name": name} for name in names],
        )
        return [
            AIOTag.from_api_response(item)
            for item in (response or [])
            if isinstance(item, dict)
        ]

    def resolve_tags(
        self, project_key: str, tags: list[Any], *, create_missing: bool = True
    ) -> list[dict[str, Any]]:
        """Resolve tag names or IDs into the payload shape used by case APIs.

        Args:
            project_key: Jira project key or ID.
            tags: Tag names, numeric IDs or numeric strings.
            create_missing: Create tags that the project does not define yet.
                A case cannot reference a tag that does not exist.

        Returns:
            A list of ``{"tag": {"ID": ..., "name": ...}}`` entries.

        Raises:
            ValueError: If a tag is unknown and ``create_missing`` is False.
        """
        if not tags:
            return []
        existing = {
            (tag.name or "").lower(): tag for tag in self.get_tags(project_key) if tag
        }
        by_id = {tag.id: tag for tag in existing.values() if tag.id is not None}

        resolved: list[dict[str, Any]] = []
        missing: list[str] = []
        for value in tags:
            if isinstance(value, int) and not isinstance(value, bool):
                tag = by_id.get(value)
                resolved.append(
                    {"tag": {"ID": value, "name": tag.name} if tag else {"ID": value}}
                )
                continue
            text = str(value).strip()
            if not text:
                continue
            if text.isdigit():
                tag = by_id.get(int(text))
                resolved.append(
                    {
                        "tag": {"ID": int(text), "name": tag.name}
                        if tag
                        else {"ID": int(text)}
                    }
                )
                continue
            tag = existing.get(text.lower())
            if tag is not None:
                resolved.append({"tag": {"ID": tag.id, "name": tag.name}})
            else:
                missing.append(text)
                resolved.append({"tag": {"name": text}})

        if missing:
            if not create_missing:
                raise ValueError(
                    f"Unknown tags for project '{project_key}': {', '.join(missing)}"
                )
            logger.info(
                f"Creating {len(missing)} new AIO Tests tag(s) in '{project_key}': "
                f"{', '.join(missing)}"
            )
            created = {
                (tag.name or "").lower(): tag
                for tag in self.create_tags(project_key, missing)
            }
            for entry in resolved:
                tag_payload = entry["tag"]
                if "ID" in tag_payload:
                    continue
                created_tag = created.get(str(tag_payload.get("name", "")).lower())
                if created_tag is not None:
                    tag_payload["ID"] = created_tag.id

        return resolved
