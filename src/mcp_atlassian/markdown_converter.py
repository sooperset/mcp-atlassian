import logging
import tempfile
from pathlib import Path

from md2conf.converter import (
    ConfluenceConverterOptions,
    ConfluenceStorageFormatConverter,
    elements_from_string,
    markdown_to_html,
)

# Configure logging
logger = logging.getLogger("mcp-atlassian.markdown_converter")


def markdown_to_confluence_storage(markdown_content):
    """
    Convert Markdown content to Confluence storage format (XHTML)
    
    This function uses the markdown-to-confluence library to properly convert
    Markdown to Confluence storage format. The library handles proper formatting of:
    - Headings with anchors
    - Text formatting (bold, italic, etc.)
    - Lists (ordered and unordered)
    - Code blocks with syntax highlighting
    - Tables and other Markdown elements
    
    Args:
        markdown_content: The markdown content to convert
        
    Returns:
        String in Confluence storage format (XHTML with Confluence macros)
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
            options = ConfluenceConverterOptions(ignore_invalid_url=True, heading_anchors=True, render_mermaid=False)

            # Create a converter
            converter = ConfluenceStorageFormatConverter(
                options=options, path=Path(temp_dir) / "temp.md", root_dir=Path(temp_dir), page_metadata={}
            )

            # Transform the HTML to Confluence storage format
            converter.visit(root)

            # Convert the element tree back to a string
            from md2conf.converter import elements_to_string

            storage_format = elements_to_string(root)

            return storage_format
        finally:
            # Clean up the temporary directory
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error converting markdown to Confluence storage format: {e}")
        logger.exception(e)

        # Fall back to a simpler method if the conversion fails
        html_content = markdown_to_html(markdown_content)

        # Use a different approach that doesn't rely on the HTML macro
        # This creates a proper Confluence storage format document
        storage_format = f"""<p>{html_content}</p>"""

        return storage_format
