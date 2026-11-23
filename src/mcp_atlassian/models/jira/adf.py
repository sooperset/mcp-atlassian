"""
Atlassian Document Format (ADF) utilities.

This module provides utilities for converting between ADF and other formats.
Supports both ADF → plain text (for reading) and Markdown → ADF (for writing).
"""

import bisect
import copy
import json
import re
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any

_MEDIA_NODE_TYPES = frozenset({"media", "mediaSingle", "mediaGroup"})
_JIRA_ISSUE_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_/-])"
    r"([A-Z][A-Z0-9_]+-\d+(?:-\d+)*)"
    r"(?![A-Za-z0-9_/-])"
)
_VALID_STATUS_COLORS = frozenset(
    {"neutral", "purple", "blue", "red", "yellow", "green"}
)


class _InlineMatch:
    """A match of the inline syntax: its span and its named groups."""

    __slots__ = ("end", "groups", "start")

    def __init__(self, start: int, end: int, **groups: str | None) -> None:
        self.start = start
        self.end = end
        self.groups = groups


_LONE_STAR = re.compile(r"(?<!\*)\*(?!\*)")
_INLINE_START = re.compile(r"[\[@`{*~]")
_WORD_RUN = re.compile(r"\w+")


class _InlineScanner:
    r"""Leftmost matches of the inline syntax, as ``re.finditer`` finds them.

    The syntax was one regex of eight alternatives, tried in this order
    (pattern order matters: mention before link, bold before italic; status
    after code so a backticked ``{status:...}`` stays literal)::

        \[~accountid:(?P<wiki_mention_id>[^\]]+)\]
        @\[(?P<display_mention_text>[^\]]+)\]
            \(accountid:(?P<display_mention_id>[^)]+)\)
        `(?P<code_inner>[^`]+)`
        \{status:(?:color=(?P<status_color>\w+)\|)?title=(?P<status_title>[^}]+)\}
        \*\*(?P<bold_inner>.+?)\*\*
        ~~(?P<strike_inner>.+?)~~
        \[(?P<link_text>[^\]]+)\]\((?P<link_href>[^)]+)\)
        (?<!\*)\*(?!\*)(?P<italic_inner>.+?)(?<!\*)\*(?!\*)

    Each body ends at the first closer after it, on the same line for
    ``.+?``, so where the next closer is fixes the match. The regex found it
    by scanning on from every opener: a line of unclosed ``[`` was scanned to
    its end once for each ``[``. This scanner looks the next closer up in a
    sorted list of its positions.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self._positions: dict[str, list[int]] = {}

    def _next(self, closer: str, pos: int) -> int:
        """Return the first position >= ``pos`` of ``closer``, or -1."""
        positions = self._positions.get(closer)
        if positions is None:
            if closer == "*":
                found = _LONE_STAR.finditer(self.text)
            else:
                # Every position, also inside a run: "***" has "**" at 0 and 1.
                found = re.finditer(f"(?={re.escape(closer)})", self.text)
            positions = self._positions[closer] = [m.start() for m in found]
        index = bisect.bisect_left(positions, pos)
        return positions[index] if index < len(positions) else -1

    def _close(self, closer: str, pos: int) -> int:
        """Return the first ``closer`` after a non-empty body at ``pos``."""
        close = self._next(closer, pos)
        return close if close > pos else -1

    def _close_on_line(self, closer: str, pos: int) -> int:
        """Like ``_close``, for a body that cannot cross a line break."""
        close = self._next(closer, pos + 1)
        if close < 0:
            return -1
        newline = self._next("\n", pos)
        return close if newline < 0 or newline >= close else -1

    def match(self, start: int) -> _InlineMatch | None:
        """Return the match at ``start``, trying the alternatives in order."""
        text = self.text
        char = text[start]
        if char == "[":
            if text.startswith("[~accountid:", start):
                body = start + 12
                if (close := self._close("]", body)) >= 0:
                    return _InlineMatch(
                        start, close + 1, wiki_mention_id=text[body:close]
                    )
            return self._link(start)
        if char == "@":
            return self._display_mention(start)
        if char == "`":
            if (close := self._close("`", start + 1)) >= 0:
                return _InlineMatch(
                    start, close + 1, code_inner=text[start + 1 : close]
                )
            return None
        if char == "{":
            return self._status(start)
        if char == "*":
            if text.startswith("**", start):
                body = start + 2
                if (close := self._close_on_line("**", body)) >= 0:
                    return _InlineMatch(start, close + 2, bold_inner=text[body:close])
                return None
            if start == 0 or text[start - 1] != "*":
                body = start + 1
                if (close := self._close_on_line("*", body)) >= 0:
                    return _InlineMatch(start, close + 1, italic_inner=text[body:close])
            return None
        if text.startswith("~~", start):
            body = start + 2
            if (close := self._close_on_line("~~", body)) >= 0:
                return _InlineMatch(start, close + 2, strike_inner=text[body:close])
        return None

    def _link(self, start: int) -> _InlineMatch | None:
        text = self.text
        close = self._close("]", start + 1)
        if close < 0 or not text.startswith("(", close + 1):
            return None
        href = close + 2
        if (end := self._close(")", href)) < 0:
            return None
        return _InlineMatch(
            start,
            end + 1,
            link_text=text[start + 1 : close],
            link_href=text[href:end],
        )

    def _display_mention(self, start: int) -> _InlineMatch | None:
        text = self.text
        if not text.startswith("@[", start):
            return None
        close = self._close("]", start + 2)
        if close < 0 or not text.startswith("(accountid:", close + 1):
            return None
        account = close + 12
        if (end := self._close(")", account)) < 0:
            return None
        return _InlineMatch(
            start,
            end + 1,
            display_mention_text=text[start + 2 : close],
            display_mention_id=text[account:end],
        )

    def _status(self, start: int) -> _InlineMatch | None:
        text = self.text
        if not text.startswith("{status:", start):
            return None
        pos = start + 8
        color = None
        if text.startswith("color=", pos):
            run = _WORD_RUN.match(text, pos + 6)
            if run is None or not text.startswith("|", run.end()):
                return None
            color = run.group()
            pos = run.end() + 1
        if not text.startswith("title=", pos):
            return None
        title = pos + 6
        if (close := self._close("}", title)) < 0:
            return None
        return _InlineMatch(
            start, close + 1, status_color=color, status_title=text[title:close]
        )


def _inline_matches(text: str) -> Iterator[_InlineMatch]:
    """Yield the inline syntax matches of ``text`` from left to right."""
    scanner = _InlineScanner(text)
    pos = 0
    for candidate in _INLINE_START.finditer(text):
        start = candidate.start()
        if start < pos:
            continue
        if (found := scanner.match(start)) is not None:
            yield found
            pos = found.end


def _append_text_nodes(
    nodes: list[dict[str, Any]],
    text: str,
    jira_base_url: str = "",
    marks: list[dict[str, Any]] | None = None,
) -> None:
    """Append text nodes, linking Jira issue keys when a base URL is known."""
    if not text:
        return

    normalized_base_url = jira_base_url.rstrip("/")
    if not normalized_base_url:
        node: dict[str, Any] = {"type": "text", "text": text}
        if marks:
            node["marks"] = marks
        nodes.append(node)
        return

    pos = 0
    for match in _JIRA_ISSUE_KEY_RE.finditer(text):
        if match.start() > pos:
            node = {"type": "text", "text": text[pos : match.start()]}
            if marks:
                node["marks"] = marks
            nodes.append(node)

        issue_key = match.group(1)
        link_marks = [
            *(marks or []),
            {
                "type": "link",
                "attrs": {"href": f"{normalized_base_url}/browse/{issue_key}"},
            },
        ]
        nodes.append({"type": "text", "text": issue_key, "marks": link_marks})
        pos = match.end()

    if pos < len(text):
        node = {"type": "text", "text": text[pos:]}
        if marks:
            node["marks"] = marks
        nodes.append(node)


def _parse_inline_formatting(
    text: str, jira_base_url: str = ""
) -> list[dict[str, Any]]:
    """Parse inline Markdown formatting into ADF inline nodes.

    Handles: bold (**), italic (*), inline code (`), links ([text](url)),
    strikethrough (~~), Jira-flavored user mentions
    ([~accountid:ACCOUNT_ID] or @[Display Name](accountid:ACCOUNT_ID)), and
    status lozenges ({status:color=green|title=Done}).

    Bare Jira issue keys are converted to links when ``jira_base_url`` is set.

    The [~accountid:...] mention syntax mirrors what Jira's v2 wiki text
    returns when a real ADF mention is read back, so the read and write paths
    are symmetric. The display-name syntax also includes the mention text in
    the ADF node.

    The {status:...} syntax follows Jira wiki markup conventions. ``color`` is
    optional and falls back to "neutral" when omitted or unrecognized.

    Args:
        text: Raw text potentially containing inline Markdown formatting.
        jira_base_url: Jira base URL used to link bare issue keys.

    Returns:
        List of ADF inline nodes (text nodes with optional marks, plus
        mention nodes when [~accountid:...] or
        @[Display Name](accountid:...) is present, plus status nodes when
        {status:...} is present).
    """
    if not text:
        return []

    nodes: list[dict[str, Any]] = []
    pos = 0
    for m in _inline_matches(text):
        # Add any plain text before this match
        if m.start > pos:
            plain = text[pos : m.start]
            _append_text_nodes(nodes, plain, jira_base_url)

        if m.groups.get("wiki_mention_id") is not None:
            nodes.append(
                {
                    "type": "mention",
                    "attrs": {"id": m.groups.get("wiki_mention_id")},
                }
            )
        elif m.groups.get("display_mention_id") is not None:
            nodes.append(
                {
                    "type": "mention",
                    "attrs": {
                        "id": m.groups.get("display_mention_id"),
                        "text": f"@{m.groups.get('display_mention_text')}",
                    },
                }
            )
        elif m.groups.get("code_inner") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.groups.get("code_inner"),
                    "marks": [{"type": "code"}],
                }
            )
        elif m.groups.get("status_title") is not None:
            color = (m.groups.get("status_color") or "neutral").lower()
            if color not in _VALID_STATUS_COLORS:
                color = "neutral"
            nodes.append(
                {
                    "type": "status",
                    "attrs": {
                        "text": m.groups.get("status_title"),
                        "color": color,
                        "style": "",
                    },
                }
            )
        elif m.groups.get("bold_inner") is not None:
            _append_text_nodes(
                nodes,
                m.groups.get("bold_inner"),
                jira_base_url,
                [{"type": "strong"}],
            )
        elif m.groups.get("strike_inner") is not None:
            _append_text_nodes(
                nodes,
                m.groups.get("strike_inner"),
                jira_base_url,
                [{"type": "strike"}],
            )
        elif m.groups.get("link_text") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.groups.get("link_text"),
                    "marks": [
                        {
                            "type": "link",
                            "attrs": {"href": m.groups.get("link_href")},
                        }
                    ],
                }
            )
        elif m.groups.get("italic_inner") is not None:
            _append_text_nodes(
                nodes,
                m.groups.get("italic_inner"),
                jira_base_url,
                [{"type": "em"}],
            )

        pos = m.end

    # Remaining plain text after last match
    if pos < len(text):
        remaining = text[pos:]
        _append_text_nodes(nodes, remaining, jira_base_url)

    # If no patterns matched, return the whole thing as plain text
    if not nodes and text:
        _append_text_nodes(nodes, text, jira_base_url)

    return nodes


def _make_paragraph(text: str, jira_base_url: str = "") -> dict[str, Any]:
    """Create an ADF paragraph node from text with inline formatting."""
    content = _parse_inline_formatting(text, jira_base_url)
    if not content:
        content = [{"type": "text", "text": ""}]
    return {"type": "paragraph", "content": content}


def _make_list_item(text: str, jira_base_url: str = "") -> dict[str, Any]:
    """Create an ADF listItem node wrapping a paragraph."""
    return {"type": "listItem", "content": [_make_paragraph(text, jira_base_url)]}


def _make_task_item(
    text: str,
    checked: bool,
    local_id: str,
    jira_base_url: str = "",
) -> dict[str, Any]:
    """Create an ADF taskItem node."""
    return {
        "type": "taskItem",
        "attrs": {"localId": local_id, "state": "DONE" if checked else "TODO"},
        "content": _parse_inline_formatting(text, jira_base_url)
        or [{"type": "text", "text": text}],
    }


def markdown_to_adf(markdown_text: str, jira_base_url: str = "") -> dict[str, Any]:
    """Convert Markdown text to ADF (Atlassian Document Format) document.

    Implements a line-by-line parser that handles common Markdown constructs.
    Jira Cloud expand blocks can be written as
    ``{expand:Title}...{expand}``. No external dependencies required.

    Args:
        markdown_text: Markdown-formatted text to convert.
        jira_base_url: Jira base URL used to link bare issue keys.

    Returns:
        ADF document dict with version, type, and content keys.
    """
    doc: dict[str, Any] = {"version": 1, "type": "doc", "content": []}

    if not markdown_text:
        doc["content"].append({"type": "paragraph", "content": []})
        return doc

    lines = markdown_text.split("\n")
    scan = _BlockScan(lines)
    # Expand and panel blocks hold blocks of their own. Each open one is a
    # frame on this stack instead of a recursive call, so deep nesting
    # cannot exceed the recursion limit.
    frames = [_BlockFrame(doc["content"], 0, len(lines))]
    while frames:
        frame = frames[-1]
        inner_frame = _parse_blocks(lines, frame, scan, jira_base_url)
        if inner_frame is not None:
            frames.append(inner_frame)
            continue
        frames.pop()
        # Ensure at least one content node
        if not frame.content:
            frame.content.append({"type": "paragraph", "content": []})
    return doc


class _BlockFrame:
    """Lines ``start`` to ``end`` of a Markdown text, parsed into ``content``."""

    def __init__(self, content: list[dict[str, Any]], start: int, end: int) -> None:
        self.content = content
        self.start = start
        self.pos = start
        self.end = end

    def open_container(
        self, content: list[dict[str, Any]], opener: int, closes: list[int]
    ) -> "_BlockFrame":
        """Return the frame of the block that opens on line ``opener``.

        The block runs to its first closing line in this frame (``closes``
        gives the next closing line from each line), or to the frame's end.
        This frame resumes after the closing line.
        """
        close = min(closes[opener + 1], self.end)
        self.pos = min(close + 1, self.end)
        return _BlockFrame(content, opener + 1, close)


class _BlockScan:
    """Next closing line of an expand and of a panel block, from each line."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._expand: list[int] | None = None
        self._panel: list[int] | None = None

    def _next(self, is_close: Callable[[str], bool]) -> list[int]:
        nxt = [len(self._lines)] * (len(self._lines) + 1)
        for k in range(len(self._lines) - 1, -1, -1):
            nxt[k] = k if is_close(self._lines[k]) else nxt[k + 1]
        return nxt

    @property
    def expand_close(self) -> list[int]:
        if self._expand is None:
            self._expand = self._next(
                lambda line: re.match(r"^\{expand\}\s*$", line) is not None
            )
        return self._expand

    @property
    def panel_close(self) -> list[int]:
        if self._panel is None:
            self._panel = self._next(lambda line: line.strip() == ":::")
        return self._panel


def _parse_blocks(
    lines: list[str], frame: _BlockFrame, scan: _BlockScan, jira_base_url: str
) -> _BlockFrame | None:
    """Parse the lines of ``frame`` into its content.

    Returns the frame of an expand or panel block that opens on the way,
    with ``frame.pos`` after it, or ``None`` at the end of ``frame``.
    """
    content = frame.content
    end = frame.end
    i = frame.pos
    while i < end:
        line = lines[i]

        # --- Expand/collapse block ({expand:Title}...{expand}) ---
        expand_match = re.match(r"^\{expand(?::(.+?))?\}\s*$", line)
        if expand_match:
            inner: list[dict[str, Any]] = []
            content.append(
                {
                    "type": "expand",
                    "attrs": {"title": expand_match.group(1) or ""},
                    "content": inner,
                }
            )
            return frame.open_container(inner, i, scan.expand_close)

        # --- Fenced code block ---
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < end and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            # Skip closing ```
            if i < end:
                i += 1
            cb: dict[str, Any] = {
                "type": "codeBlock",
                "attrs": {"language": lang} if lang else {},
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            }
            content.append(cb)
            continue

        # --- Horizontal rule ---
        stripped = line.strip()
        if stripped in ("---", "***", "___") or (
            len(stripped) >= 3
            and all(c == stripped[0] for c in stripped)
            and stripped[0] in "-*_"
        ):
            # Make sure it's not a list item like "- --"
            if not line.startswith("- ") and not line.startswith("* "):
                content.append({"type": "rule"})
                i += 1
                continue

        # --- Heading ---
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            heading_node: dict[str, Any] = {
                "type": "heading",
                "attrs": {"level": level},
                "content": _parse_inline_formatting(text, jira_base_url),
            }
            content.append(heading_node)
            i += 1
            continue

        # --- Blockquote ---
        if line.startswith("> "):
            quote_lines: list[str] = []
            while i < end and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            bq_content = [_make_paragraph(ln, jira_base_url) for ln in quote_lines]
            content.append({"type": "blockquote", "content": bq_content})
            continue

        # --- Task list (- [ ] / - [x]) ---
        if re.match(r"^[-*]\s+\[[ xX]\]\s+", line):
            task_items: list[dict[str, Any]] = []
            task_counter = 0
            while i < end and re.match(r"^[-*]\s+\[[ xX]\]\s+", lines[i]):
                checked = bool(re.match(r"^[-*]\s+\[[xX]\]\s+", lines[i]))
                item_text = re.sub(r"^[-*]\s+\[[ xX]\]\s+", "", lines[i])
                task_counter += 1
                task_items.append(
                    _make_task_item(
                        item_text,
                        checked,
                        f"task-{id(content)}-{task_counter}",
                        jira_base_url,
                    )
                )
                i += 1
            content.append(
                {
                    "type": "taskList",
                    "attrs": {"localId": f"tasklist-{id(content)}-{i - frame.start}"},
                    "content": task_items,
                }
            )
            continue

        # --- Panel block ---
        panel_match = re.match(r"^:::(\w+)\s*$", line)
        if panel_match:
            panel_type = panel_match.group(1).lower()
            valid_panel_types = {"note", "info", "warning", "success", "error"}
            if panel_type in valid_panel_types:
                inner = []
                content.append(
                    {
                        "type": "panel",
                        "attrs": {"panelType": panel_type},
                        "content": inner,
                    }
                )
                return frame.open_container(inner, i, scan.panel_close)

        # --- Unordered list ---
        if re.match(r"^[-*]\s+", line):
            items: list[dict[str, Any]] = []
            while i < end and re.match(r"^[-*]\s+", lines[i]):
                item_text = re.sub(r"^[-*]\s+", "", lines[i])
                items.append(_make_list_item(item_text, jira_base_url))
                i += 1
            content.append({"type": "bulletList", "content": items})
            continue

        # --- Ordered list ---
        if re.match(r"^\d+\.\s+", line):
            items_ol: list[dict[str, Any]] = []
            while i < end:
                if re.match(r"^\d+\.\s+", lines[i]):
                    item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                    items_ol.append(_make_list_item(item_text, jira_base_url))
                    i += 1
                elif (
                    not lines[i].strip()
                    and i + 1 < end
                    and re.match(r"^\d+\.\s+", lines[i + 1])
                ):
                    i += 1
                else:
                    break
            content.append({"type": "orderedList", "content": items_ol})
            continue

        # --- Table ---
        if line.startswith("|") and "|" in line[1:]:
            table_rows: list[str] = []
            while i < end and lines[i].startswith("|"):
                table_rows.append(lines[i])
                i += 1

            # Parse rows, skip separator (|---|---|). The delimiter row is the
            # second line of a table by definition, so only that line is
            # eligible: a later row of dash-only cells is data, and a single
            # "-" is a common way to write "not applicable".
            data_rows: list[list[str]] = []
            for row_index, row_line in enumerate(table_rows):
                cells = [c.strip() for c in row_line.strip("|").split("|")]
                if row_index == 1 and all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    continue
                data_rows.append(cells)

            if data_rows:
                adf_rows: list[dict[str, Any]] = []
                for idx, cells in enumerate(data_rows):
                    cell_type = "tableHeader" if idx == 0 else "tableCell"
                    adf_cells = []
                    for cell_text in cells:
                        cell_content = _parse_inline_formatting(
                            cell_text, jira_base_url
                        )
                        if not cell_content:
                            cell_content = [{"type": "text", "text": ""}]
                        adf_cells.append(
                            {
                                "type": cell_type,
                                "content": [
                                    {"type": "paragraph", "content": cell_content}
                                ],
                            }
                        )
                    adf_rows.append({"type": "tableRow", "content": adf_cells})

                content.append(
                    {
                        "type": "table",
                        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
                        "content": adf_rows,
                    }
                )
            continue

        # --- Empty line (skip) ---
        if not stripped:
            i += 1
            continue

        # --- Paragraph (default) ---
        content.append(_make_paragraph(line, jira_base_url))
        i += 1

    frame.pos = end
    return None


def _adf_node_contains_media(node: dict[str, Any]) -> bool:
    """Return True when an ADF node contains media content."""
    if node.get("type") in _MEDIA_NODE_TYPES:
        return True

    content = node.get("content")
    if isinstance(content, list):
        return any(
            _adf_node_contains_media(child)
            for child in content
            if isinstance(child, dict)
        )

    return False


def extract_top_level_media_nodes(
    adf_document: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract top-level ADF nodes that contain media content."""
    if not isinstance(adf_document, dict):
        return []

    content = adf_document.get("content")
    if not isinstance(content, list):
        return []

    return [
        copy.deepcopy(node)
        for node in content
        if isinstance(node, dict) and _adf_node_contains_media(node)
    ]


def merge_adf_with_preserved_media(
    target_adf: dict[str, Any],
    source_adf: dict[str, Any] | None,
) -> dict[str, Any]:
    """Append existing media nodes from one ADF document into another.

    This is intentionally narrow: it preserves existing media-bearing blocks
    when a caller rewrites the surrounding description text, without attempting
    to merge all prior formatting or layout.
    """
    preserved_media = extract_top_level_media_nodes(source_adf)
    if not preserved_media:
        return target_adf

    merged = copy.deepcopy(target_adf)
    content = merged.get("content")
    if not isinstance(content, list):
        content = []
        merged["content"] = content

    existing_signatures = {
        json.dumps(node, sort_keys=True, separators=(",", ":"))
        for node in extract_top_level_media_nodes(merged)
    }
    for media_node in preserved_media:
        signature = json.dumps(media_node, sort_keys=True, separators=(",", ":"))
        if signature in existing_signatures:
            continue
        content.append(media_node)
        existing_signatures.add(signature)

    return merged


def adf_to_text(adf_content: dict | list | str | None) -> str | None:
    """
    Convert Atlassian Document Format (ADF) content to plain text.

    ADF is Jira Cloud's rich text format returned for fields like description.
    This function extracts text content from the ADF structure.

    Args:
        adf_content: ADF document (dict), content list, string, or None

    Returns:
        Plain text string or None if no content
    """
    node = _adf_text_source(adf_content)
    if not _adf_is_composite(node):
        return _adf_leaf_text(node)
    return "".join(_adf_text_pieces(node)) or None


#: ADF node types whose text does not depend on their content.
_ADF_LEAF_TYPES = frozenset(
    {"text", "hardBreak", "mention", "emoji", "date", "status", "inlineCard"}
)


def _is_leaf_type(node_type: Any) -> bool:
    """Whether ``node_type`` is in ``_ADF_LEAF_TYPES``; any value may come in."""
    return isinstance(node_type, str) and node_type in _ADF_LEAF_TYPES


def _adf_text_source(node: Any) -> Any:
    """Follow nodes whose text is their content's text, as far as they go."""
    while (
        isinstance(node, dict)
        and not _is_leaf_type(node.get("type"))
        and node.get("type") != "codeBlock"
        and node.get("content")
    ):
        node = node["content"]
    return node


def _adf_is_composite(node: Any) -> bool:
    """Whether ``node`` (from ``_adf_text_source``) is built from other nodes."""
    return isinstance(node, list) or (
        isinstance(node, dict) and node.get("type") == "codeBlock"
    )


class _Piece(str):
    """Text written as is when it comes off the ``_adf_text_pieces`` stack."""


class _ItemEnd(int):
    """End of a list item: the length the pieces had when the item began."""


_LIST_END = object()


def _adf_text_pieces(root: Any) -> list[str]:
    """Return the text of a list or codeBlock node as pieces to join.

    The walk keeps an explicit stack: deeply nested content (a list inside
    a list, many levels down) exceeded the recursion limit. Each piece is
    written once, so deep content is not copied again at every level. A list
    joins the non-empty texts of its items with newlines: the newline goes
    out before each item after the first item with text, and is taken back
    when the item has none.
    """
    pieces: list[str] = []
    stack: list[Any] = [root]
    # For each open list: whether one of its items had text, and a text
    # that is not a str (the recursive walk's join raised TypeError for it
    # once the list's items were done).
    started: list[bool] = []
    not_str: list[Any] = []
    while stack:
        entry = stack.pop()
        if isinstance(entry, _Piece):
            pieces.append(str(entry))
        elif isinstance(entry, _ItemEnd):
            if len(pieces) > entry:
                started[-1] = True
            elif started[-1]:
                pieces.pop()
        elif entry is _LIST_END:
            started.pop()
            if (value := not_str.pop()) is not None:
                "\n".join([value])
        elif isinstance(entry, list):
            started.append(False)
            not_str.append(None)
            stack.append(_LIST_END)
            for item in reversed(entry):
                stack.append(_ListItem(item))
        elif isinstance(entry, _ListItem):
            if started[-1]:
                pieces.append("\n")
            stack.append(_ItemEnd(len(pieces)))
            text = _push_text(stack, pieces, entry.node)
            if text is not None and not isinstance(text, str) and not_str[-1] is None:
                not_str[-1] = text
        else:  # a codeBlock
            code = _adf_text_source(entry.get("content", []))
            if _adf_is_composite(code):
                stack.append(_Piece("\n```"))
                stack.append(code)
                pieces.append("```\n")
            else:
                pieces.append(f"```\n{_adf_leaf_text(code) or ''}\n```")
    return pieces


class _ListItem:
    """A list item on the ``_adf_text_pieces`` stack."""

    __slots__ = ("node",)

    def __init__(self, node: Any) -> None:
        self.node = node


def _push_text(stack: list[Any], pieces: list[str], node: Any) -> Any:
    """Write a leaf's text now and return it, or push a composite node."""
    node = _adf_text_source(node)
    if _adf_is_composite(node):
        stack.append(node)
        return None
    if text := _adf_leaf_text(node):
        pieces.append(text)
        return text
    return None


def _adf_leaf_text(node: Any) -> Any:
    """Text of a node that is not built from other nodes (see above)."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return None

    # Check if this is a text node
    if node.get("type") == "text":
        return node.get("text", "")

    # Check if this is a hardBreak node
    if node.get("type") == "hardBreak":
        return "\n"

    # Check if this is a mention node
    if node.get("type") == "mention":
        attrs = node.get("attrs", {})
        return attrs.get("text") or f"@{attrs.get('id', 'unknown')}"

    # Check if this is an emoji node
    if node.get("type") == "emoji":
        attrs = node.get("attrs", {})
        return attrs.get("text") or attrs.get("shortName", "")

    # Check if this is a date node
    if node.get("type") == "date":
        attrs = node.get("attrs", {})
        timestamp = attrs.get("timestamp")
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, OSError, TypeError, OverflowError):
                return str(timestamp)
        return ""

    # Check if this is a status node
    if node.get("type") == "status":
        attrs = node.get("attrs", {})
        return f"[{attrs.get('text', '')}]"

    # Check if this is an inlineCard node
    if node.get("type") == "inlineCard":
        attrs = node.get("attrs", {})
        url = attrs.get("url")
        if url:
            return url
        data = attrs.get("data", {})
        return data.get("url") or data.get("name", "")

    return None
