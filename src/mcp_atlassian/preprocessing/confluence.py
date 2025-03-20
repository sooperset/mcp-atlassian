"""Confluence-specific text preprocessing module."""

import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup
from markdown import markdown  # type: ignore

from ..utils import HTMLProcessor, MarkdownOptimizer, TextChunker
from .base import BasePreprocessor

if TYPE_CHECKING:
    pass

logger = logging.getLogger("mcp-atlassian")


class ConfluencePreprocessor(BasePreprocessor):
    """
    Implementation of text preprocessor for Confluence.

    Handles Confluence-specific functionality such as
    converting markdown to Confluence storage format.
    """

    def __init__(self, base_url: str = "", confluence_client: Any = None) -> None:
        """
        Initialize Confluence text preprocessor.

        Args:
            base_url: Base URL for Confluence API server
            confluence_client: Optional Confluence client for user lookups
        """
        super().__init__(base_url, confluence_client)
        self.text_chunker = TextChunker(chunk_size=8000, overlap=300)
        self.large_text_threshold = 15000  # Threshold for incremental processing

    def markdown_to_confluence_storage(self, markdown_content: str) -> str:
        """
        Convert markdown content to Confluence storage format.

        Uses a temporary HTML file and the Confluence API to convert.

        Args:
            markdown_content: Markdown content to convert

        Returns:
            Content in Confluence storage format
        """
        if not markdown_content:
            return ""

        # Optimize markdown before converting it
        markdown_content = MarkdownOptimizer.remove_empty_markdown_links(
            markdown_content
        )
        markdown_content = MarkdownOptimizer.optimize_markdown_tables(markdown_content)

        # For large content, use incremental processing
        if len(markdown_content) > self.large_text_threshold:
            return self._convert_large_markdown(markdown_content)

        # Convert markdown to HTML
        try:
            # We're using a simpler markdown conversion here
            html_content = markdown(
                markdown_content,
                extensions=[
                    "markdown.extensions.tables",
                    "markdown.extensions.fenced_code",
                ],
            )

            # Create a temporary file for the conversion process
            with tempfile.NamedTemporaryFile(
                suffix=".html", mode="w+", delete=False
            ) as temp_file:
                temp_file.write(html_content)
                temp_file_path = temp_file.name

            # Use Confluence API to convert HTML to storage format
            if self.confluence_client:
                try:
                    storage_format = self._convert_html_to_storage(
                        html_content, temp_file_path
                    )
                    return storage_format
                except Exception as e:
                    logger.error(f"Error converting HTML to storage format: {str(e)}")
                    return html_content
            else:
                logger.warning("No Confluence client provided, returning HTML content")
                return html_content

        except Exception as e:
            logger.error(f"Error in markdown_to_confluence_storage: {str(e)}")
            return markdown_content
        finally:
            # Cleanup: Remove temporary file if it exists
            if "temp_file_path" in locals() and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}")

    def _convert_large_markdown(self, markdown_content: str) -> str:
        """
        Converts large markdown content to Confluence storage format incrementally.

        Args:
            markdown_content: Markdown content

        Returns:
            Content in Confluence storage format
        """
        # Divide markdown into logical blocks
        chunks = self.text_chunker.chunk_text(markdown_content, preserve_newlines=True)

        # Process each chunk separately
        processed_chunks = []
        for chunk in chunks:
            # Convert to HTML
            html_chunk = markdown(
                chunk,
                extensions=[
                    "markdown.extensions.tables",
                    "markdown.extensions.fenced_code",
                ],
            )

            # Convert to storage format
            if self.confluence_client:
                try:
                    # Create temporary file for the chunk
                    with tempfile.NamedTemporaryFile(
                        suffix=".html", mode="w+", delete=False
                    ) as temp_file:
                        temp_file.write(html_chunk)
                        temp_file_path = temp_file.name

                    storage_format = self._convert_html_to_storage(
                        html_chunk, temp_file_path
                    )
                    processed_chunks.append(storage_format)

                    # Clean up the temporary file
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(
                        f"Error converting chunk to storage format: {str(e)}"
                    )
                    processed_chunks.append(html_chunk)
            else:
                processed_chunks.append(html_chunk)

        # Join the processed chunks
        return "".join(processed_chunks)

    def _convert_html_to_storage(self, html_content: str, temp_file_path: str) -> str:
        """
        Convert HTML to Confluence Storage format using the API.

        Args:
            html_content: HTML content to convert
            temp_file_path: Path to temporary file

        Returns:
            Confluence storage format content
        """
        if not self.confluence_client:
            return html_content

        try:
            # Use the Confluence API endpoint to convert HTML to storage format
            if hasattr(self.confluence_client, "confluence"):
                api_client = self.confluence_client.confluence
                response = api_client._service_post(
                    "contentbody/convert/storage",
                    data={"value": html_content, "representation": "editor"},
                    headers={"Content-Type": "application/json"},
                )
                return response.get("value", html_content)
            else:
                logger.warning("ConfluenceClient does not have 'confluence' attribute")
                return html_content
        except Exception as e:
            logger.error(f"API error converting to storage format: {str(e)}")
            raise

    def html_to_storage(self, html_content: str) -> str:
        """
        Public method to convert HTML to Confluence Storage format.
        Creates a temporary file internally.

        Args:
            html_content: HTML content to convert

        Returns:
            Confluence storage format content
        """
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as temp_file:
            temp_file_path = temp_file.name

        try:
            return self._convert_html_to_storage(html_content, temp_file_path)
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def extract_excerpt_from_html(
        self, html_content: str, max_length: int = 300
    ) -> str:
        """
        Extracts a section of HTML content to use as a summary/snippet.

        Args:
            html_content: HTML content
            max_length: Maximum length of the extracted section

        Returns:
            Summarized text extracted from HTML
        """
        return HTMLProcessor.generate_excerpt(html_content, max_length)

    def clean_confluence_html(self, html_content: str) -> str:
        """
        Cleans Confluence HTML by removing unnecessary elements.

        Args:
            html_content: Confluence HTML content

        Returns:
            Clean HTML
        """
        if not html_content:
            return ""

        # For large content, use incremental processing
        if len(html_content) > self.large_text_threshold:
            # Process HTML incrementally
            return self.text_chunker.process_text_in_chunks(
                html_content, lambda chunk: self._clean_html_chunk(chunk)
            )

        return self._clean_html_chunk(html_content)

    def _clean_html_chunk(self, html_chunk: str) -> str:
        """
        Cleans a chunk of Confluence HTML.

        Args:
            html_chunk: HTML chunk

        Returns:
            Clean HTML
        """
        try:
            # Process HTML using BeautifulSoup
            soup = BeautifulSoup(html_chunk, "html.parser")

            # Remove metadata elements
            for selector in [
                "meta",
                "script",
                "style",
                "div.confluence-information-macro",
                "ac:structured-macro",
            ]:
                for element in soup.select(selector):
                    element.decompose()

            # Remove empty elements
            for element in soup.find_all(
                lambda tag: not tag.contents and tag.name not in ["br", "img", "hr"]
            ):
                element.decompose()

            return str(soup)
        except Exception as e:
            logger.warning(f"Error cleaning HTML chunk: {str(e)}")
            return html_chunk
