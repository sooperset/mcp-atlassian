"""
Atlassian Document Format (ADF) utilities.

This module provides utilities for converting between ADF and other formats.
Supports both ADF → plain text (for reading) and Markdown → ADF (for writing).
"""

import re
from datetime import datetime, timezone
from typing import Any


def _parse_inline_formatting(text: str) -> list[dict[str, Any]]:
    """Parse inline Markdown formatting into ADF inline nodes.

    Handles: bold (**), italic (*), inline code (`), links ([text](url)),
    and strikethrough (~~).

    Args:
        text: Raw text potentially containing inline Markdown formatting.

    Returns:
        List of ADF inline nodes (text nodes with optional marks).
    """
    if not text:
        return []

    nodes: list[dict[str, Any]] = []
    # Pattern order matters: bold before italic, code before others
    inline_re = re.compile(
        r"`(?P<code_inner>[^`]+)`"
        r"|\*\*(?P<bold_inner>.+?)\*\*"
        r"|~~(?P<strike_inner>.+?)~~"
        r"|\[(?P<link_text>[^\]]+)\]\((?P<link_href>[^)]+)\)"
        r"|(?<!\*)\*(?!\*)(?P<italic_inner>.+?)(?<!\*)\*(?!\*)"
    )

    pos = 0
    for m in inline_re.finditer(text):
        # Add any plain text before this match
        if m.start() > pos:
            plain = text[pos : m.start()]
            if plain:
                nodes.append({"type": "text", "text": plain})

        if m.group("code_inner") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("code_inner"),
                    "marks": [{"type": "code"}],
                }
            )
        elif m.group("bold_inner") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("bold_inner"),
                    "marks": [{"type": "strong"}],
                }
            )
        elif m.group("strike_inner") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("strike_inner"),
                    "marks": [{"type": "strike"}],
                }
            )
        elif m.group("link_text") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("link_text"),
                    "marks": [
                        {
                            "type": "link",
                            "attrs": {"href": m.group("link_href")},
                        }
                    ],
                }
            )
        elif m.group("italic_inner") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("italic_inner"),
                    "marks": [{"type": "em"}],
                }
            )

        pos = m.end()

    # Remaining plain text after last match
    if pos < len(text):
        remaining = text[pos:]
        if remaining:
            nodes.append({"type": "text", "text": remaining})

    # If no patterns matched, return the whole thing as plain text
    if not nodes and text:
        nodes.append({"type": "text", "text": text})

    return nodes


def _make_paragraph(text: str) -> dict[str, Any]:
    """Create an ADF paragraph node from text with inline formatting."""
    content = _parse_inline_formatting(text)
    if not content:
        content = [{"type": "text", "text": ""}]
    return {"type": "paragraph", "content": content}


def _make_list_item(text: str) -> dict[str, Any]:
    """Create an ADF listItem node wrapping a paragraph."""
    return {"type": "listItem", "content": [_make_paragraph(text)]}


def markdown_to_adf(markdown_text: str) -> dict[str, Any]:
    """Convert Markdown text to ADF (Atlassian Document Format) document.

    Implements a line-by-line parser that handles common Markdown constructs.
    No external dependencies required.

    Args:
        markdown_text: Markdown-formatted text to convert.

    Returns:
        ADF document dict with version, type, and content keys.
    """
    doc: dict[str, Any] = {"version": 1, "type": "doc", "content": []}

    if not markdown_text:
        doc["content"].append({"type": "paragraph", "content": []})
        return doc

    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # --- Fenced code block ---
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            # Skip closing ```
            if i < len(lines):
                i += 1
            cb: dict[str, Any] = {
                "type": "codeBlock",
                "attrs": {"language": lang} if lang else {},
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            }
            doc["content"].append(cb)
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
                doc["content"].append({"type": "rule"})
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
                "content": _parse_inline_formatting(text),
            }
            doc["content"].append(heading_node)
            i += 1
            continue

        # --- Blockquote ---
        if line.startswith("> "):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            bq_content = [_make_paragraph(ln) for ln in quote_lines]
            doc["content"].append({"type": "blockquote", "content": bq_content})
            continue

        # --- Unordered list ---
        if re.match(r"^[-*]\s+", line):
            items: list[dict[str, Any]] = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                item_text = re.sub(r"^[-*]\s+", "", lines[i])
                items.append(_make_list_item(item_text))
                i += 1
            doc["content"].append({"type": "bulletList", "content": items})
            continue

        # --- Ordered list ---
        if re.match(r"^\d+\.\s+", line):
            items_ol: list[dict[str, Any]] = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                items_ol.append(_make_list_item(item_text))
                i += 1
            doc["content"].append({"type": "orderedList", "content": items_ol})
            continue

        # --- Empty line (skip) ---
        if not stripped:
            i += 1
            continue

        # --- Paragraph (default) ---
        doc["content"].append(_make_paragraph(line))
        i += 1

    # Ensure at least one content node
    if not doc["content"]:
        doc["content"].append({"type": "paragraph", "content": []})

    return doc


def adf_to_text(adf_content: dict | list | str | None) -> str | None:
    """
    Convert Atlassian Document Format (ADF) content to plain text.

    ADF is Jira Cloud's rich text format returned for fields like description.
    This function recursively extracts text content from the ADF structure.

    Args:
        adf_content: ADF document (dict), content list, string, or None

    Returns:
        Plain text string or None if no content
    """
    if adf_content is None:
        return None

    if isinstance(adf_content, str):
        return adf_content

    if isinstance(adf_content, list):
        texts = []
        for item in adf_content:
            text = adf_to_text(item)
            if text:
                texts.append(text)
        return "\n".join(texts) if texts else None

    if isinstance(adf_content, dict):
        # Check if this is a text node
        if adf_content.get("type") == "text":
            return adf_content.get("text", "")

        # Check if this is a hardBreak node
        if adf_content.get("type") == "hardBreak":
            return "\n"

        # Check if this is a mention node
        if adf_content.get("type") == "mention":
            attrs = adf_content.get("attrs", {})
            return attrs.get("text") or f"@{attrs.get('id', 'unknown')}"

        # Check if this is an emoji node
        if adf_content.get("type") == "emoji":
            attrs = adf_content.get("attrs", {})
            return attrs.get("text") or attrs.get("shortName", "")

        # Check if this is a date node
        if adf_content.get("type") == "date":
            attrs = adf_content.get("attrs", {})
            timestamp = attrs.get("timestamp")
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
                    return dt.strftime("%Y-%m-%d")
                except (ValueError, OSError, TypeError, OverflowError):
                    return str(timestamp)
            return ""

        # Check if this is a status node
        if adf_content.get("type") == "status":
            attrs = adf_content.get("attrs", {})
            return f"[{attrs.get('text', '')}]"

        # Check if this is an inlineCard node
        if adf_content.get("type") == "inlineCard":
            attrs = adf_content.get("attrs", {})
            url = attrs.get("url")
            if url:
                return url
            data = attrs.get("data", {})
            return data.get("url") or data.get("name", "")

        # Check if this is a codeBlock node
        if adf_content.get("type") == "codeBlock":
            content = adf_content.get("content", [])
            code_text = adf_to_text(content) or ""
            return f"```\n{code_text}\n```"

        # Recursively process content
        content = adf_content.get("content")
        if content:
            return adf_to_text(content)

        return None

    return None
