"""Module for Confluence label operations."""

import logging
from typing import Any

from ..models.confluence import ConfluenceLabel
from .client import ConfluenceClient
from .v2_adapter import ConfluenceV2Adapter

logger = logging.getLogger("mcp-atlassian")


class LabelsMixin(ConfluenceClient):
    """Mixin for Confluence label operations."""

    @property
    def _v2_adapter(self) -> ConfluenceV2Adapter | None:
        """Get the v2 API adapter for Cloud OAuth.

        Confluence Cloud has removed the v1 label read endpoint from the OAuth
        gateway (410 Gone), so label reads go through v2 there.

        Returns:
            ConfluenceV2Adapter instance if OAuth is configured on Cloud,
            None otherwise.
        """
        if self.config.auth_type == "oauth" and self.config.is_cloud:
            return ConfluenceV2Adapter(
                session=self.confluence._session, base_url=self.confluence.url
            )
        return None

    def get_page_labels(self, page_id: str) -> list[ConfluenceLabel]:
        """
        Get all labels for a specific page.

        Args:
            page_id: The ID of the page to get labels from

        Returns:
            List of ConfluenceLabel models containing label content and metadata

        Raises:
            Exception: If there is an error getting the label
        """
        try:
            v2_adapter = self._v2_adapter
            labels_response: Any
            if v2_adapter:
                labels_response = v2_adapter.get_page_labels(page_id)
            else:
                labels_response = self.confluence.get_page_labels(page_id=page_id)

            # Process each label
            label_models = []
            for label_data in labels_response.get("results"):
                # Create the model with the processed content
                label_model = ConfluenceLabel.from_api_response(
                    label_data,
                    base_url=self.config.url,
                )

                label_models.append(label_model)

            return label_models

        except Exception as e:
            logger.error(f"Failed fetching labels from page {page_id}: {str(e)}")
            raise Exception(
                f"Failed fetching labels from page {page_id}: {str(e)}"
            ) from e

    def add_page_label(self, page_id: str, name: str) -> list[ConfluenceLabel]:
        """
        Add a label to a Confluence page.

        Args:
            page_id: The ID of the page to update
            name: The name of the label

        Returns:
            Label model containing the updated list of labels

        Raises:
            Exception: If there is an error adding the label
        """
        try:
            logger.debug(f"Adding label with name '{name}' to page {page_id}")

            update_kwargs = {
                "page_id": page_id,
                "label": name,
            }
            response = self.confluence.set_page_label(**update_kwargs)

            # After update, refresh the page data
            return self.get_page_labels(page_id)
        except Exception as e:
            logger.error(f"Error adding label '{name}' to page {page_id}: {str(e)}")
            raise Exception(
                f"Failed to add label '{name}' to page {page_id}: {str(e)}"
            ) from e
