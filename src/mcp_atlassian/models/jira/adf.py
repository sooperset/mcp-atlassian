"""
Atlassian Document Format (ADF) utilities.

This module provides utilities for parsing and generating ADF content for Jira Cloud.
"""

import re
from datetime import datetime, timezone
from typing import Any


def markdown_to_adf(markdown_text: str) -> dict[str, Any]:
    """
    Convert Markdown text to Atlassian Document Format (ADF).

    This function converts common Markdown elements to their ADF equivalents.
    Supported elements:
    - Paragraphs
    - Headers (h1-h6)
    - Bold (**text** or __text__)
    - Italic (*text* or _text_)
    - Code blocks (```)
    - Inline code (`code`)
    - Links ([text](url))
    - Bullet lists (- or *)
    - Numbered lists (1. 2. etc.)
    - Blockquotes (>)
    - Horizontal rules (---)

    Args:
        markdown_text: Text in Markdown format

    Returns:
        ADF document as a dictionary
    """
    if not markdown_text:
        return _create_adf_doc([_create_paragraph([])])

    lines = markdown_text.split("\n")
    content: list[dict[str, Any]] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block (fenced)
        if line.startswith("```"):
            language = line[3:].strip() or None
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code_content = "\n".join(code_lines)
            content.append(_create_code_block(code_content, language))
            i += 1
            continue

        # Header
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2)
            content.append(_create_heading(header_text, level))
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^(-{3,}|_{3,}|\*{3,})$", line.strip()):
            content.append(_create_rule())
            i += 1
            continue

        # Blockquote
        if line.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_lines.append(lines[i][1:].strip())
                i += 1
            quote_text = "\n".join(quote_lines)
            content.append(_create_blockquote(quote_text))
            continue

        # Bullet list
        if re.match(r"^[\-\*]\s+", line):
            list_items = []
            while i < len(lines) and re.match(r"^[\-\*]\s+", lines[i]):
                item_text = re.sub(r"^[\-\*]\s+", "", lines[i])
                list_items.append(item_text)
                i += 1
            content.append(_create_bullet_list(list_items))
            continue

        # Numbered list
        if re.match(r"^\d+\.\s+", line):
            list_items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                list_items.append(item_text)
                i += 1
            content.append(_create_ordered_list(list_items))
            continue

        # Empty line - skip
        if not line.strip():
            i += 1
            continue

        # Default: paragraph with inline formatting
        paragraph_content = _parse_inline_formatting(line)
        content.append(_create_paragraph(paragraph_content))
        i += 1

    if not content:
        content = [_create_paragraph([])]

    return _create_adf_doc(content)


def _create_adf_doc(content: list[dict[str, Any]]) -> dict[str, Any]:
    """Create an ADF document wrapper."""
    return {"version": 1, "type": "doc", "content": content}


def _create_paragraph(content: list[dict[str, Any]]) -> dict[str, Any]:
    """Create an ADF paragraph node."""
    return {"type": "paragraph", "content": content}


def _create_heading(text: str, level: int) -> dict[str, Any]:
    """Create an ADF heading node."""
    return {
        "type": "heading",
        "attrs": {"level": min(max(level, 1), 6)},
        "content": _parse_inline_formatting(text),
    }


def _create_text(text: str, marks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Create an ADF text node."""
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _create_code_block(code: str, language: str | None = None) -> dict[str, Any]:
    """Create an ADF code block node."""
    node: dict[str, Any] = {
        "type": "codeBlock",
        "content": [{"type": "text", "text": code}],
    }
    if language:
        node["attrs"] = {"language": language}
    return node


def _create_rule() -> dict[str, Any]:
    """Create an ADF horizontal rule node."""
    return {"type": "rule"}


def _create_blockquote(text: str) -> dict[str, Any]:
    """Create an ADF blockquote node."""
    return {
        "type": "blockquote",
        "content": [_create_paragraph(_parse_inline_formatting(text))],
    }


def _create_bullet_list(items: list[str]) -> dict[str, Any]:
    """Create an ADF bullet list node."""
    list_items = []
    for item in items:
        list_items.append({
            "type": "listItem",
            "content": [_create_paragraph(_parse_inline_formatting(item))],
        })
    return {"type": "bulletList", "content": list_items}


def _create_ordered_list(items: list[str]) -> dict[str, Any]:
    """Create an ADF ordered list node."""
    list_items = []
    for item in items:
        list_items.append({
            "type": "listItem",
            "content": [_create_paragraph(_parse_inline_formatting(item))],
        })
    return {"type": "orderedList", "content": list_items}


def _create_link(text: str, url: str) -> dict[str, Any]:
    """Create an ADF text node with link mark."""
    return {
        "type": "text",
        "text": text,
        "marks": [{"type": "link", "attrs": {"href": url}}],
    }


def _parse_inline_formatting(text: str) -> list[dict[str, Any]]:
    """
    Parse inline Markdown formatting and convert to ADF content nodes.

    Handles: bold, italic, inline code, links
    """
    if not text:
        return []

    result: list[dict[str, Any]] = []
    pos = 0

    # Regex patterns for inline elements
    patterns = [
        # Links: [text](url)
        (r"\[([^\]]+)\]\(([^)]+)\)", "link"),
        # Bold: **text** or __text__
        (r"\*\*([^*]+)\*\*|__([^_]+)__", "bold"),
        # Italic: *text* or _text_ (but not inside words for underscore)
        (r"(?<!\w)\*([^*]+)\*(?!\w)|(?<!\w)_([^_]+)_(?!\w)", "italic"),
        # Inline code: `code`
        (r"`([^`]+)`", "code"),
    ]

    while pos < len(text):
        earliest_match = None
        earliest_pos = len(text)
        match_type = None

        # Find the earliest match among all patterns
        for pattern, ptype in patterns:
            match = re.search(pattern, text[pos:])
            if match and pos + match.start() < earliest_pos:
                earliest_match = match
                earliest_pos = pos + match.start()
                match_type = ptype

        if earliest_match is None:
            # No more matches, add remaining text
            if pos < len(text):
                result.append(_create_text(text[pos:]))
            break

        # Add text before the match
        if earliest_pos > pos:
            result.append(_create_text(text[pos:earliest_pos]))

        # Process the match
        if match_type == "link":
            link_text = earliest_match.group(1)
            link_url = earliest_match.group(2)
            result.append(_create_link(link_text, link_url))
        elif match_type == "bold":
            bold_text = earliest_match.group(1) or earliest_match.group(2)
            result.append(_create_text(bold_text, [{"type": "strong"}]))
        elif match_type == "italic":
            italic_text = earliest_match.group(1) or earliest_match.group(2)
            result.append(_create_text(italic_text, [{"type": "em"}]))
        elif match_type == "code":
            code_text = earliest_match.group(1)
            result.append(_create_text(code_text, [{"type": "code"}]))

        pos = earliest_pos + earliest_match.end() - earliest_match.start()

    return result if result else [_create_text(text)] if text else []


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
                except (ValueError, OSError, TypeError):
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
