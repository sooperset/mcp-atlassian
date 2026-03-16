"""Module for Confluence template operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..utils.decorators import handle_auth_errors
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class TemplatesMixin(ConfluenceClient):
    """Mixin for Confluence template operations."""

    @handle_auth_errors("Confluence API")
    def list_page_templates(
        self,
        space_key: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """List page content templates, optionally scoped to a space.

        When ``space_key`` is omitted, global templates are returned.  Pass a
        space key to retrieve templates defined within that space.

        Args:
            space_key: Optional space key to filter templates.  ``None``
                returns global templates.
            limit: Maximum number of templates to return (default 25).

        Returns:
            List of template dicts, each containing at minimum:
            ``templateId``, ``name``, ``templateType``, and ``description``.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If the API call fails.
        """
        try:
            results: list[dict[str, Any]] = self.confluence.get_content_templates(
                space=space_key,
                limit=limit,
            )
            return results
        except HTTPError:
            raise
        except Exception as e:
            logger.error(f"Error listing templates: {str(e)}")
            raise Exception(f"Failed to list page templates: {str(e)}") from e

    @handle_auth_errors("Confluence API")
    def get_page_template(self, template_id: str) -> dict[str, Any]:
        """Get a single content template by ID, including its body.

        Args:
            template_id: The ID of the template to retrieve.

        Returns:
            Template dict containing ``templateId``, ``name``,
            ``templateType``, ``description``, and ``body`` (storage format).

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If the API call fails or the template is not found.
        """
        try:
            return self.confluence.get_content_template(template_id)  # type: ignore[no-any-return]
        except HTTPError:
            raise
        except Exception as e:
            logger.error(f"Error fetching template {template_id}: {str(e)}")
            raise Exception(
                f"Failed to get template {template_id}: {str(e)}"
            ) from e

    @handle_auth_errors("Confluence API")
    def create_page_from_template(
        self,
        space_key: str,
        title: str,
        template_id: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Confluence page pre-populated with a template's body.

        Fetches the template's storage-format body and creates a page with
        that content.  The caller can rename the page and edit it afterwards.

        Args:
            space_key: Key of the space in which to create the page.
            title: Title for the new page.
            template_id: ID of the template whose body to use.
            parent_id: Optional parent page ID.

        Returns:
            Dict with ``id``, ``title``, ``url``, and ``space_key`` of the
            newly created page.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: If the template fetch or page creation fails.
        """
        try:
            template = self.confluence.get_content_template(template_id)

            body_obj = template.get("body", {})
            # Templates store content under body.storage.value (same as pages)
            body_value: str = body_obj.get("storage", {}).get("value", "")

            result = self.confluence.create_page(
                space=space_key,
                title=title,
                body=body_value,
                parent_id=parent_id,
                representation="storage",
            )

            page_id: str = result.get("id", "")
            base_url = self.config.url.rstrip("/")
            page_url = f"{base_url}/wiki/spaces/{space_key}/pages/{page_id}"

            return {
                "id": page_id,
                "title": result.get("title", title),
                "url": page_url,
                "space_key": space_key,
            }
        except HTTPError:
            raise
        except Exception as e:
            logger.error(
                f"Error creating page from template {template_id}: {str(e)}"
            )
            raise Exception(
                f"Failed to create page from template {template_id}: {str(e)}"
            ) from e
