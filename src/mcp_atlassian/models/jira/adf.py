"""
Atlassian Document Format (ADF) utilities.

This module provides utilities for parsing ADF content from Jira Cloud.
"""


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

        # Recursively process content
        content = adf_content.get("content")
        if content:
            return adf_to_text(content)

        return None

    return None
