"""Confluence-specific text preprocessing module."""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from md2conf.converter import (
    ConfluenceConverterOptions,
    ConfluenceStorageFormatConverter,
    elements_from_string,
    elements_to_string,
    markdown_to_html,
)

from .base import BasePreprocessor

logger = logging.getLogger("mcp-atlassian")


class ConfluencePreprocessor(BasePreprocessor):
    """Handles text preprocessing for Confluence content."""

    def __init__(self, base_url: str, **kwargs: Any) -> None:
        """
        Initialize the Confluence text preprocessor.

        Args:
            base_url: Base URL for Confluence API
            **kwargs: Additional arguments for the base class
        """
        super().__init__(base_url=base_url, **kwargs)

    def markdown_to_confluence_storage(self, markdown_content: str) -> str:
        """
        Convert Markdown content to Confluence storage format (XHTML)

        Args:
            markdown_content: Markdown text to convert

        Returns:
            Confluence storage format (XHTML) string
        """
        try:
            # First convert markdown to HTML
            html_content = markdown_to_html(markdown_content)

            # Create a temporary directory for any potential attachments
            temp_dir = tempfile.mkdtemp()

            try:
                # Parse the HTML into an element tree
                root = elements_from_string(html_content)

                # Create converter options
                options = ConfluenceConverterOptions(
                    ignore_invalid_url=True, heading_anchors=True, render_mermaid=False
                )

                # Create a converter
                converter = ConfluenceStorageFormatConverter(
                    options=options,
                    path=Path(temp_dir) / "temp.md",
                    root_dir=Path(temp_dir),
                    page_metadata={},
                )

                # Transform the HTML to Confluence storage format
                converter.visit(root)

                # Convert the element tree back to a string
                storage_format = elements_to_string(root)

                return str(storage_format)
            finally:
                # Clean up the temporary directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Error converting markdown to Confluence storage format: {e}")
            logger.exception(e)

            # Fall back to a simpler method if the conversion fails
            html_content = markdown_to_html(markdown_content)

            # Use a different approach that doesn't rely on the HTML macro
            # This creates a proper Confluence storage format document
            storage_format = f"""<p>{html_content}</p>"""

            return str(storage_format)

    # Confluence-specific methods can be added here
