"""Confluence-specific text preprocessing module."""

import html
import logging
import shutil
import tempfile
from pathlib import Path

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

    def __init__(self, base_url: str) -> None:
        """
        Initialize the Confluence text preprocessor.

        Args:
            base_url: Base URL for Confluence API
        """
        super().__init__(base_url=base_url)

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

                # FIXED: Selective HTML entity decoding to avoid XML parsing issues
                # Only decode entities outside of code blocks and structured content
                decoded_storage_format = self._selective_html_decode(
                    str(storage_format)
                )

                return decoded_storage_format
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

            # FIXED: Selective HTML entity decoding in fallback case
            decoded_storage_format = self._selective_html_decode(str(storage_format))

            return decoded_storage_format

    def _selective_html_decode(self, content: str) -> str:
        """
        Selectively decode HTML entities to avoid XML parsing issues.

        Only decodes entities in text content, not inside code blocks,
        structured Confluence elements, or URL parameters where entities
        are needed for proper XML or URL structure.
        """
        import re

        # Don't decode entities inside structured macros, CDATA sections, or URLs
        # REMOVED: r'<code>.*?</code>' - we WANT HTML entities decoded in inline code
        protected_patterns = [
            r"<ac:plain-text-body>.*?</ac:plain-text-body>",  # Code macro content
            r"<ac:parameter[^>]*>.*?</ac:parameter>",  # Macro parameters
            r"<!\[CDATA\[.*?\]\]>",  # CDATA sections
            # URL parameter protection - protect URLs with query parameters
            r'https?://[^\s<>"]+&[^\s<>"]*',  # HTTP/HTTPS URLs with & parameters
            r'ftp://[^\s<>"]+&[^\s<>"]*',  # FTP URLs with & parameters
            r'file://[^\s<>"]+&[^\s<>"]*',  # File URLs with & parameters
            # More comprehensive URL protection for any protocol
            r'\w+://[^\s<>"]*&[^\s<>"]*',  # Any protocol URLs with & parameters
        ]

        # Find all protected regions
        protected_regions = []
        for pattern in protected_patterns:
            for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
                protected_regions.append((match.start(), match.end()))

        # Sort regions by start position
        protected_regions.sort()

        # Decode entities only outside protected regions
        result = ""
        last_end = 0

        for start, end in protected_regions:
            # Decode entities in unprotected content before this region
            unprotected_content = content[last_end:start]
            result += html.unescape(unprotected_content)

            # Keep protected content as-is
            result += content[start:end]
            last_end = end

        # Decode entities in remaining unprotected content
        if last_end < len(content):
            unprotected_content = content[last_end:]
            result += html.unescape(unprotected_content)

        # Apply additional XML structure fixes after HTML decoding
        result = self._fix_xml_structure(result)

        return result

    def _fix_xml_structure(self, content: str) -> str:
        """
        Fix common XML structure issues that cause parsing errors.

        Addresses:
        - Empty attribute values (ac:name="")
        - Unquoted attribute values
        - Self-closing tags that need proper closing
        """
        import re

        # Fix 1: Handle empty ac:name attributes by moving content to attribute
        # Pattern: <ac:parameter ac:name="">content</ac:parameter> -> <ac:parameter ac:name="content"></ac:parameter>

        # Fix ac:parameter with empty ac:name
        def fix_parameter_name(match):
            full_match = match.group(0)
            content = match.group(1).strip()
            if content:
                return f'<ac:parameter ac:name="{content}"></ac:parameter>'
            else:
                return '<ac:parameter ac:name="unnamed"></ac:parameter>'

        content = re.sub(
            r'<ac:parameter\s+ac:name="">([^<]*)</ac:parameter>',
            fix_parameter_name,
            content,
        )

        # Also handle structured-macro anchor patterns
        def fix_anchor_name(match):
            content = match.group(1).strip()
            if content:
                return f'<ac:structured-macro ac:name="anchor" ac:schema-version="1"><ac:parameter ac:name="{content}"></ac:parameter></ac:structured-macro>'
            else:
                return '<ac:structured-macro ac:name="anchor" ac:schema-version="1"><ac:parameter ac:name="unnamed"></ac:parameter></ac:structured-macro>'

        content = re.sub(
            r'<ac:structured-macro\s+ac:name="anchor"\s+ac:schema-version="1"><ac:parameter\s+ac:name="">([^<]*)</ac:parameter></ac:structured-macro>',
            fix_anchor_name,
            content,
        )

        # Fix 2: More careful attribute quoting to avoid double quotes
        def quote_unquoted_attrs(match):
            attr_name = match.group(1)
            attr_value = match.group(2)

            # Skip if already quoted, is a URL, or contains problematic characters
            if (
                attr_value.startswith('"')
                or attr_value.startswith("'")
                or "://" in attr_value
                or attr_value.startswith("http")
            ):
                return match.group(0)

            # Handle values that contain HTML tags - don't quote them
            if "<" in attr_value or ">" in attr_value:
                return match.group(0)

            # Only quote simple alphanumeric values and common patterns
            if re.match(r"^[a-zA-Z0-9_.-]+$", attr_value):
                return f'{attr_name}="{attr_value}"'

            return match.group(0)

        # Apply quoted attribute fix more selectively
        content = re.sub(r'(\w+)=([^"\s>]+?)(?=[\s>])', quote_unquoted_attrs, content)

        # Fix 3: Ensure self-closing tags are properly formatted
        # Convert <br> to <br/>, <hr> to <hr/> etc, but only if they're not already self-closing
        content = re.sub(
            r"<(br|hr|img|input|meta|link)(\s[^>]*)?>(?!</)", r"<\1\2/>", content
        )

        # Fix 4: Clean up double quotes that may have been introduced
        content = re.sub(r'"">', '">', content)

        # Fix 5: Ensure proper closing of common tags that should be self-closing
        content = re.sub(r"<br\s*></br>", "<br/>", content)
        content = re.sub(r"<hr\s*></hr>", "<hr/>", content)

        # Fix 6: Remove any attributes with only whitespace values
        content = re.sub(r'\s+\w+="[\s]*"', "", content)

        # Fix 7: Ensure ampersands in URLs are preserved, but escape others
        def fix_ampersands(text):
            # Protect URLs first
            url_pattern = r'(https?://[^\s<>"]*)'
            urls = re.findall(url_pattern, text)

            # Replace URLs with placeholders
            placeholder_map = {}
            for i, url in enumerate(urls):
                placeholder = f"__URL_PLACEHOLDER_{i}__"
                placeholder_map[placeholder] = url
                text = text.replace(url, placeholder, 1)

            # Now escape remaining unescaped ampersands
            text = re.sub(r"&(?![a-zA-Z]+;|#\d+;)", "&amp;", text)

            # Restore URLs
            for placeholder, url in placeholder_map.items():
                text = text.replace(placeholder, url)

            return text

        content = fix_ampersands(content)

        return content

    # Confluence-specific methods can be added here
