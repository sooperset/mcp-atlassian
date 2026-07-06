"""Confluence-specific text preprocessing module."""

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from md2conf.converter import (
    ConfluencePageCollection,
    ConfluenceStorageFormatConverter,
    ConfluenceUserCollection,
    ConverterOptions,
    attachment_name,
    elements_from_strings,
    elements_to_string,
    markdown_to_html,
)
from md2conf.metadata import ConfluenceSiteMetadata

from .base import BasePreprocessor

logger = logging.getLogger("mcp-atlassian")


class ConfluencePreprocessor(BasePreprocessor):
    """Handles text preprocessing for Confluence content."""

    def __init__(self, base_url: str) -> None:
        """
        Initialize the Confluence text preprocessor.

        Args:
            base_url: Base URL for Confluence API
        """
        super().__init__(base_url=base_url)

    def markdown_to_confluence_storage(
        self, markdown_content: str, *, enable_heading_anchors: bool = False
    ) -> str:
        """
        Convert Markdown content to Confluence storage format (XHTML)

        Args:
            markdown_content: Markdown text to convert
            enable_heading_anchors: Whether to enable automatic heading anchor generation (default: False)

        Returns:
            Confluence storage format (XHTML) string
        """
        try:
            # First convert markdown to HTML
            html_content = self._fix_attachment_images(
                markdown_to_html(markdown_content)
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                root_dir = Path(temp_dir)
                path = root_dir / "temp.md"
                path.write_text(markdown_content, encoding="utf-8")

                # Parse the HTML into an element tree
                root = elements_from_strings([html_content])

                parsed_url = urlparse(self.base_url)

                # Create converter options
                options = ConverterOptions(
                    force_valid_url=False,
                    heading_anchors=enable_heading_anchors,
                    render_mermaid=False,
                )

                # Create a converter
                converter = ConfluenceStorageFormatConverter(
                    options=options,
                    path=path,
                    root_dir=root_dir,
                    site_metadata=ConfluenceSiteMetadata(
                        domain=parsed_url.netloc,
                        base_path=parsed_url.path or "/wiki",
                        space_key=None,
                    ),
                    page_metadata=ConfluencePageCollection(),
                    user_metadata=ConfluenceUserCollection(),
                )

                # Transform the HTML to Confluence storage format
                converter.visit(root)

                # Convert the element tree back to a string
                storage_format = elements_to_string(root)

                return self._fix_attachment_images(str(storage_format))

        except Exception as e:
            logger.error(f"Error converting markdown to Confluence storage format: {e}")
            logger.exception(e)

            # Fall back to a simpler method if the conversion fails
            html_content = markdown_to_html(markdown_content)

            # Use a different approach that doesn't rely on the HTML macro
            # This creates a proper Confluence storage format document
            storage_format = f"""<p>{html_content}</p>"""

            return self._fix_attachment_images(str(storage_format))

    @staticmethod
    def _is_attachment_image_source(src: str) -> bool:
        """Return whether an image source should resolve as an attachment."""
        parsed_src = urlparse(src)
        return not parsed_src.scheme and not src.startswith(("/", "#"))

    @staticmethod
    def _fix_attachment_images(storage_html: str) -> str:
        """Replace bare-filename ``<img>`` tags with Confluence attachment macros.

        Confluence Storage Format cannot resolve bare filenames in
        ``<img src="filename.ext"/>``. Attachment references must use the
        ``ac:image`` / ``ri:attachment`` macro instead. External URLs
        (``http``/``https``/``data``) and absolute paths are left untouched.

        Args:
            storage_html: Confluence storage format HTML string.

        Returns:
            Storage HTML with bare-filename img tags replaced by attachment macros.
        """
        if "<img" not in storage_html.lower():
            return storage_html

        soup = BeautifulSoup(storage_html, "html.parser")
        rewritten = False

        for image in soup.find_all("img"):
            src = image.get("src")
            if not isinstance(src, str):
                continue
            if not ConfluencePreprocessor._is_attachment_image_source(src):
                continue

            attachment_image = soup.new_tag("ac:image")
            alt = image.get("alt", "")
            attachment_image["ac:alt"] = alt if isinstance(alt, str) else ""

            for html_attr, confluence_attr in (
                ("width", "ac:width"),
                ("height", "ac:height"),
            ):
                value = image.get(html_attr)
                if isinstance(value, str):
                    attachment_image[confluence_attr] = value

            attachment = soup.new_tag("ri:attachment")
            attachment["ri:filename"] = attachment_name(src)
            attachment_image.append(attachment)
            image.replace_with(attachment_image)
            rewritten = True

        return str(soup) if rewritten else storage_html
