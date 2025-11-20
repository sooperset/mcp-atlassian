"""
Minimal ADF (Atlassian Document Format) parser.

Extracts plain text from ADF JSON structures.
"""

from typing import Any


def parse_adf_to_text(content: Any) -> str:
    """
    Extract plain text from ADF format.

    Args:
        content: ADF content (dict, str, or other)

    Returns:
        Plain text string
    """
    if isinstance(content, str):
        return content

    if not isinstance(content, dict):
        return str(content) if content else ""

    # Handle ADF document structure
    if content.get("type") == "doc":
        return _extract_text_from_nodes(content.get("content", []))

    # Handle direct content array
    if "content" in content:
        return _extract_text_from_nodes(content["content"])

    return str(content)


def _extract_text_from_nodes(nodes: list[dict[str, Any]]) -> str:
    """
    Recursively extract text from ADF nodes.

    Args:
        nodes: List of ADF content nodes

    Returns:
        Extracted text with basic formatting
    """
    if not isinstance(nodes, list):
        return ""

    text_parts = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type")

        if node_type == "text":
            # Direct text node
            text_parts.append(node.get("text", ""))

        elif node_type in ("paragraph", "heading", "listItem", "blockquote"):
            # Block elements with nested content
            nested_text = _extract_text_from_nodes(node.get("content", []))
            if nested_text:
                text_parts.append(nested_text)

        elif node_type in ("bulletList", "orderedList"):
            # Lists
            nested_text = _extract_text_from_nodes(node.get("content", []))
            if nested_text:
                text_parts.append(nested_text)

        elif node_type == "codeBlock":
            # Code blocks
            code_text = _extract_text_from_nodes(node.get("content", []))
            if code_text:
                text_parts.append(f"```\n{code_text}\n```")

        elif node_type == "hardBreak":
            # Line breaks
            text_parts.append("\n")

        elif "content" in node:
            # Any other node with nested content
            nested_text = _extract_text_from_nodes(node["content"])
            if nested_text:
                text_parts.append(nested_text)

    return "\n".join(text_parts) if text_parts else ""
