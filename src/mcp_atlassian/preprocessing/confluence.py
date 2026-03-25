"""Confluence-specific text preprocessing module."""

import logging
import re
import shutil
import tempfile
from pathlib import Path

from md2conf.converter import (
    ConfluenceConverterOptions,
    ConfluenceStorageFormatConverter,
    elements_to_string,
    markdown_to_html,
)
from md2conf.metadata import ConfluenceSiteMetadata

# Handle md2conf API changes: elements_from_string may be renamed to elements_from_strings
try:
    from md2conf.converter import elements_from_string
except ImportError:
    from md2conf.converter import elements_from_strings as elements_from_string

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

    # Table width (px) and layout name keyed by the caller-supplied table_layout value.
    _TABLE_WIDTHS: dict[str, str] = {
        "full-width": "1800",
        "wide": "960",
        "default": "760",
    }
    _TABLE_LAYOUTS: dict[str, str] = {
        "full-width": "full-width",
        "wide": "wide",
        "default": "default",
    }

    def markdown_to_confluence_storage(
        self,
        markdown_content: str,
        *,
        enable_heading_anchors: bool = False,
        table_layout: str | None = None,
        apply_task_lists: bool = True,
    ) -> str:
        """
        Convert Markdown content to Confluence storage format (XHTML)

        Args:
            markdown_content: Markdown text to convert
            enable_heading_anchors: Whether to enable automatic heading anchor
                generation (default: False)
            table_layout: Optional table width preset applied to all tables in the output.
                Values: 'full-width' (1800 px), 'wide' (960 px), 'default' (760 px / Confluence default).
                When None, tables retain the default 760 px width emitted by the converter.
            apply_task_lists: Whether to convert GFM task-list items
                (``- [ ]`` / ``- [x]``) to Confluence ``ac:task-list`` macros
                (default: True)

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
                    ignore_invalid_url=True,
                    heading_anchors=enable_heading_anchors,
                    render_mermaid=False,
                )

                # Create a converter
                converter = ConfluenceStorageFormatConverter(
                    options=options,
                    path=Path(temp_dir) / "temp.md",
                    root_dir=Path(temp_dir),
                    site_metadata=ConfluenceSiteMetadata(
                        domain="", base_path="", space_key=None
                    ),
                    page_metadata={},
                )

                # Transform the HTML to Confluence storage format
                converter.visit(root)

                # Convert the element tree back to a string
                storage_format = str(elements_to_string(root))

                if table_layout and table_layout in self._TABLE_WIDTHS:
                    storage_format = self._apply_table_layout(
                        storage_format, table_layout
                    )

                if apply_task_lists:
                    storage_format = self._apply_task_lists(storage_format)

                return self._fix_attachment_images(storage_format)
            finally:
                # Clean up the temporary directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Error converting markdown to Confluence storage format: {e}")
            logger.exception(e)

            # Fall back to a simpler method if the conversion fails
            html_content = markdown_to_html(markdown_content)

            # This creates a proper Confluence storage format document
            storage_format = f"""<p>{html_content}</p>"""

            return str(storage_format)

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

        def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
            tag = match.group(0)
            src_match = re.search(r'src="([^"]+)"', tag)
            alt_match = re.search(r'alt="([^"]+)"', tag)
            if not src_match:
                return tag
            src = src_match.group(1)
            # Leave external URLs and absolute paths untouched
            if src.startswith(("http://", "https://", "data:", "/")):
                return tag
            alt = alt_match.group(1) if alt_match else ""
            return (
                f'<ac:image ac:alt="{alt}">'
                f'<ri:attachment ri:filename="{src}"/>'
                f"</ac:image>"
            )

        return re.sub(r"<img\b[^>]*/?>", _replace, storage_html)

    @classmethod
    def _apply_table_layout(cls, storage_html: str, table_layout: str) -> str:
        """Set table width and layout attributes in Confluence storage format.

        The md2conf converter emits bare ``<table>`` tags with no width or
        layout attributes.  Confluence renders these at its default narrow
        width.  This method injects ``data-table-width`` and ``data-layout``
        attributes so tables render at the requested width.

        If attributes already exist (e.g. content edited via another tool)
        they are replaced rather than duplicated.

        Args:
            storage_html: Confluence storage-format string to post-process.
            table_layout: One of 'full-width', 'wide', or 'default'.

        Returns:
            Updated storage-format string with table width attributes set.
        """
        width = cls._TABLE_WIDTHS.get(table_layout, "760")
        layout = cls._TABLE_LAYOUTS.get(table_layout, "default")
        attrs = f'data-table-width="{width}" data-layout="{layout}"'

        def _replace_table_tag(m: re.Match) -> str:
            tag = m.group(0)
            # Strip any existing data-table-width / data-layout attributes first
            tag = re.sub(r'\s*data-table-width="[^"]*"', "", tag)
            tag = re.sub(r'\s*data-layout="[^"]*"', "", tag)
            # Inject new attributes after <table
            return re.sub(r"^<table", f"<table {attrs}", tag)

        return re.sub(r"<table\b[^>]*>", _replace_table_tag, storage_html)

    @classmethod
    def _apply_task_lists(cls, storage_html: str) -> str:
        """Convert GFM-style task list items to Confluence ac:task-list macros.

        md2conf renders GFM task list items (``- [ ]`` / ``- [x]``) as plain
        ``<ul><li>`` elements with the checkbox marker as literal text.
        Confluence needs ``<ac:task-list>`` / ``<ac:task>`` elements to render
        interactive checkboxes.

        Only converts ``<ul>`` blocks whose every ``<li>`` begins with a
        checkbox marker; mixed lists (some items without a checkbox prefix)
        are left unchanged.  Nested ``<ul>`` elements are not traversed to
        avoid partial matches.

        Args:
            storage_html: Confluence storage-format string to post-process.

        Returns:
            Updated storage-format string with task lists converted.
        """
        task_item_re = re.compile(r"^\[( |x|X)\]\s*(.*)", re.DOTALL)

        def _replace_ul(m: re.Match) -> str:
            ul_html = m.group(0)
            items = re.findall(r"<li>(.*?)</li>", ul_html, re.DOTALL)
            if not items:
                return ul_html

            task_matches = [task_item_re.match(item) for item in items]
            if not all(task_matches):
                return ul_html  # mixed list — leave as-is

            parts = ["<ac:task-list>"]
            for tm in task_matches:
                if tm is None:  # should not happen given all(task_matches) above
                    continue
                status = "complete" if tm.group(1).lower() == "x" else "incomplete"
                body = tm.group(2).strip()
                parts.append(
                    f"<ac:task>"
                    f"<ac:task-status>{status}</ac:task-status>"
                    f"<ac:task-body>{body}</ac:task-body>"
                    f"</ac:task>"
                )
            parts.append("</ac:task-list>")
            return "".join(parts)

        # Only match <ul> blocks with no nested <ul> to avoid partial tag matches.
        return re.sub(
            r"<ul>(?:(?!<ul>).)*?</ul>", _replace_ul, storage_html, flags=re.DOTALL
        )
