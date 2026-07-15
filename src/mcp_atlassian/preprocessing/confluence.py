"""Confluence-specific text preprocessing module."""

import logging
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag
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

    # Use a private-use sequence that is absent from the converted HTML so
    # restoring an opt-out task list cannot remove user-supplied characters.
    _TASK_MARKER_PREFIX = "\ue000"
    _TASK_MARKER_PATTERN = re.compile(r"(<li\b[^>]*>)(\[[ xX]\])")

    def __init__(self, base_url: str) -> None:
        """
        Initialize the Confluence text preprocessor.

        Args:
            base_url: Base URL for Confluence API
        """
        super().__init__(base_url=base_url)

    # Table width and layout keyed by the caller-supplied table_layout value.
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
        apply_task_lists: bool = True,
        table_layout: str | None = None,
    ) -> str:
        """
        Convert Markdown content to Confluence storage format (XHTML)

        Args:
            markdown_content: Markdown text to convert
            enable_heading_anchors: Whether to enable automatic heading anchor
                generation (default: False)
            apply_task_lists: Whether to convert GFM task-list items
                (``- [ ]`` / ``- [x]``) to Confluence ``ac:task-list`` macros
                (default: True)
            table_layout: Optional table width preset applied to all tables in the output.
                Values: 'full-width' (1800 px), 'wide' (960 px), or 'default'
                (760 px / Confluence default).
                When None, tables retain the default 760 px width emitted by the converter.

        Returns:
            Confluence storage format (XHTML) string
        """
        try:
            # First convert markdown to HTML
            html_content = self._fix_attachment_images(
                markdown_to_html(markdown_content)
            )
            task_marker_prefix: str | None = None
            if not apply_task_lists:
                task_marker_prefix = self._get_task_list_marker_prefix(html_content)
                html_content = self._protect_task_list_markers(
                    html_content, task_marker_prefix
                )

            with tempfile.TemporaryDirectory() as temp_dir:
                root_dir = Path(temp_dir)
                path = root_dir / "temp.md"
                path.write_text(markdown_content, encoding="utf-8")

                # Parse the HTML into an element tree
                root = elements_from_strings([html_content])

                parsed_url = urlparse(self.base_url)
                base_path = parsed_url.path or "/wiki/"
                if not base_path.endswith("/"):
                    base_path += "/"

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
                        base_path=base_path,
                        space_key=None,
                    ),
                    page_metadata=ConfluencePageCollection(),
                    user_metadata=ConfluenceUserCollection(),
                )

                # Transform the HTML to Confluence storage format
                converter.visit(root)

                # Convert the element tree back to a string
                storage_format = self._fix_attachment_images(
                    str(elements_to_string(root))
                )
                if task_marker_prefix is not None:
                    storage_format = self._restore_task_list_markers(
                        storage_format, task_marker_prefix
                    )
                if apply_task_lists:
                    storage_format = self._normalize_task_list_bodies(storage_format)

                if apply_task_lists:
                    storage_format = self._apply_task_lists(storage_format)
                if table_layout is not None and table_layout in self._TABLE_WIDTHS:
                    storage_format = self._apply_table_layout(
                        storage_format, table_layout
                    )
                return storage_format

        except Exception as e:
            logger.error(f"Error converting markdown to Confluence storage format: {e}")
            logger.exception(e)

            # Fall back to a simpler method if the conversion fails
            html_content = markdown_to_html(markdown_content)

            # This creates a proper Confluence storage format document
            storage_format = self._fix_attachment_images(f"""<p>{html_content}</p>""")
            if apply_task_lists:
                storage_format = self._apply_task_lists(storage_format)
            if table_layout is not None and table_layout in self._TABLE_WIDTHS:
                storage_format = self._apply_table_layout(storage_format, table_layout)

            return storage_format

    @classmethod
    def _get_task_list_marker_prefix(cls, html_content: str) -> str:
        """Return a private-use marker sequence absent from the HTML."""
        marker_prefix = cls._TASK_MARKER_PREFIX
        while marker_prefix in html_content:
            marker_prefix += cls._TASK_MARKER_PREFIX
        return marker_prefix

    @classmethod
    def _protect_task_list_markers(cls, html_content: str, marker_prefix: str) -> str:
        """Prevent md2conf from converting task lists when requested."""
        return cls._TASK_MARKER_PATTERN.sub(rf"\1{marker_prefix}\2", html_content)

    @classmethod
    def _restore_task_list_markers(cls, storage_html: str, marker_prefix: str) -> str:
        """Remove task-list conversion sentinels from converted HTML."""
        return storage_html.replace(marker_prefix, "")

    @staticmethod
    def _normalize_task_list_bodies(storage_html: str) -> str:
        """Match legacy task-body whitespace after md2conf 0.6 conversion."""
        return re.sub(r"(<ac:task-body>)[ \t]+", r"\1", storage_html)

    @classmethod
    def _apply_task_lists(cls, storage_html: str) -> str:
        """Convert GFM-style task list items to Confluence ac:task-list macros.

        md2conf renders GFM task list items (``- [ ]`` / ``- [x]``) as plain
        ``<ul><li>`` elements with the checkbox marker as literal text.
        Confluence needs ``<ac:task-list>`` / ``<ac:task>`` elements to render
        interactive checkboxes.

        Only converts unnested ``<ul>`` blocks whose every direct ``<li>``
        begins with a checkbox marker. Mixed and nested lists are left unchanged.

        Args:
            storage_html: Confluence storage-format string to post-process.

        Returns:
            Updated storage-format string with task lists converted.
        """
        if "<ul" not in storage_html.lower() or "[" not in storage_html:
            return storage_html

        marker_pattern = re.compile(
            r"^\s*\[(?P<checked>[ xX])\](?:[ \t]+|$)(?P<body>.*)$",
            re.DOTALL,
        )
        soup = BeautifulSoup(storage_html, "html.parser")
        rewritten = False

        for unordered_list in soup.find_all("ul"):
            if not isinstance(unordered_list, Tag):
                continue
            if unordered_list.find("ul") or unordered_list.find_parent("ul"):
                continue

            items = unordered_list.find_all("li", recursive=False)
            if not items:
                continue

            matches: list[tuple[Tag, NavigableString, re.Match[str]]] = []
            for item in items:
                if not isinstance(item, Tag):
                    break
                first_content = next(
                    (
                        child
                        for child in item.contents
                        if not isinstance(child, NavigableString) or str(child).strip()
                    ),
                    None,
                )
                if not isinstance(first_content, NavigableString):
                    break
                match = marker_pattern.match(str(first_content))
                if match is None:
                    break
                matches.append((item, first_content, match))

            if len(matches) != len(items):
                continue

            task_list = soup.new_tag("ac:task-list")
            for item, marker_text, match in matches:
                marker_text.replace_with(match.group("body"))

                task = soup.new_tag("ac:task")
                status = soup.new_tag("ac:task-status")
                status.string = (
                    "complete"
                    if match.group("checked").lower() == "x"
                    else "incomplete"
                )
                body = soup.new_tag("ac:task-body")
                while item.contents:
                    body.append(item.contents[0].extract())
                task.extend((status, body))
                task_list.append(task)

            unordered_list.replace_with(task_list)
            rewritten = True

        return str(soup) if rewritten else storage_html

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
