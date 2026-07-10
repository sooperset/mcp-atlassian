"""Module for Confluence template operations."""

from typing import Any, cast
from urllib.parse import quote

from ..utils.decorators import handle_auth_errors
from .client import ConfluenceClient
from .pages import PagesMixin


class TemplatesMixin(ConfluenceClient):
    """Mixin for Confluence template operations."""

    def _require_cloud_templates_api(self) -> None:
        """Ensure the Confluence Cloud template API is available.

        Raises:
            ValueError: If configured for Confluence Server/Data Center.
        """
        if not self.config.is_cloud:
            msg = (
                "Page template operations are only available for Confluence "
                "Cloud. Server/Data Center does not expose the template REST API."
            )
            raise ValueError(msg)

    def _get_template_api_response(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object from a Confluence template endpoint.

        The explicit v1 base URL is required for Cloud OAuth, whose API gateway
        needs the ``/wiki`` product prefix. The upstream convenience methods do
        not add that prefix for gateway URLs.

        Args:
            path: REST path below the Confluence v1 API base URL.
            params: Optional query parameters.

        Returns:
            Parsed JSON response object.

        Raises:
            HTTPError: If the API request fails.
            ValueError: If the API returns a non-object JSON response.
        """
        self._require_cloud_templates_api()
        response = self.confluence._session.get(
            f"{self._v1_rest_base_url()}{path}",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            msg = "Confluence template API returned a non-object response"
            raise ValueError(msg)
        return cast(dict[str, Any], data)

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
            HTTPError: If the API request fails.
            ValueError: If the API response has an unexpected shape.
        """
        params: dict[str, Any] = {"limit": limit}
        if space_key:
            params["spaceKey"] = space_key

        data = self._get_template_api_response(
            "/rest/api/template/page",
            params=params,
        )
        results = data.get("results", [])
        if not isinstance(results, list) or not all(
            isinstance(item, dict) for item in results
        ):
            msg = "Confluence template list response has invalid results"
            raise ValueError(msg)
        return cast(list[dict[str, Any]], results)

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
            HTTPError: If the API request fails or the template is not found.
            ValueError: If the API response has an unexpected shape.
        """
        encoded_template_id = quote(template_id, safe="")
        return self._get_template_api_response(
            f"/rest/api/template/{encoded_template_id}"
        )

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
            HTTPError: If the template fetch fails.
            ValueError: If the template has no storage-format body.
            Exception: If page creation fails.
        """
        template = self.get_page_template(template_id)
        body = template.get("body")
        storage = body.get("storage") if isinstance(body, dict) else None
        body_value = storage.get("value") if isinstance(storage, dict) else None
        if not isinstance(body_value, str):
            msg = f"Template {template_id} has no storage-format body"
            raise ValueError(msg)

        page = PagesMixin.create_page(
            cast(PagesMixin, self),
            space_key=space_key,
            title=title,
            body=body_value,
            parent_id=parent_id,
            is_markdown=False,
            content_representation="storage",
        )
        return {
            "id": page.id,
            "title": page.title,
            "url": page.url,
            "space_key": space_key,
        }
