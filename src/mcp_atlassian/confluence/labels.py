"""Module for Confluence label operations."""

import logging

from ..models.confluence import ConfluenceLabel
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class LabelsMixin(ConfluenceClient):
    """Mixin for Confluence label operations."""

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
            # Get labels with expanded content
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
