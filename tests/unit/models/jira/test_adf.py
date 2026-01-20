"""Tests for Atlassian Document Format (ADF) utilities."""

import pytest

from mcp_atlassian.models.jira.adf import (
    adf_to_text,
    markdown_to_adf,
)


class TestMarkdownToAdf:
    """Tests for markdown_to_adf function."""

    def test_empty_string(self):
        """Test converting empty string."""
        result = markdown_to_adf("")
        assert result["version"] == 1
        assert result["type"] == "doc"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "paragraph"

    def test_simple_paragraph(self):
        """Test converting simple paragraph."""
        result = markdown_to_adf("Hello world")
        assert result["type"] == "doc"
        assert result["content"][0]["type"] == "paragraph"
        assert result["content"][0]["content"][0]["text"] == "Hello world"

    def test_heading_levels(self):
        """Test converting headings at different levels."""
        for level in range(1, 7):
            md = "#" * level + " Heading"
            result = markdown_to_adf(md)
            heading = result["content"][0]
            assert heading["type"] == "heading"
            assert heading["attrs"]["level"] == level
            assert heading["content"][0]["text"] == "Heading"

    def test_bold_formatting(self):
        """Test converting bold text."""
        result = markdown_to_adf("This is **bold** text")
        content = result["content"][0]["content"]
        assert content[0]["text"] == "This is "
        assert content[1]["text"] == "bold"
        assert content[1]["marks"] == [{"type": "strong"}]
        assert content[2]["text"] == " text"

    def test_italic_formatting(self):
        """Test converting italic text."""
        result = markdown_to_adf("This is *italic* text")
        content = result["content"][0]["content"]
        assert content[1]["text"] == "italic"
        assert content[1]["marks"] == [{"type": "em"}]

    def test_inline_code(self):
        """Test converting inline code."""
        result = markdown_to_adf("Use `code` here")
        content = result["content"][0]["content"]
        assert content[1]["text"] == "code"
        assert content[1]["marks"] == [{"type": "code"}]

    def test_link(self):
        """Test converting links."""
        result = markdown_to_adf("Click [here](https://example.com)")
        content = result["content"][0]["content"]
        link_node = content[1]
        assert link_node["text"] == "here"
        assert link_node["marks"] == [{"type": "link", "attrs": {"href": "https://example.com"}}]

    def test_bullet_list(self):
        """Test converting bullet list."""
        result = markdown_to_adf("- Item 1\n- Item 2\n- Item 3")
        bullet_list = result["content"][0]
        assert bullet_list["type"] == "bulletList"
        assert len(bullet_list["content"]) == 3
        assert bullet_list["content"][0]["type"] == "listItem"

    def test_ordered_list(self):
        """Test converting ordered list."""
        result = markdown_to_adf("1. First\n2. Second\n3. Third")
        ordered_list = result["content"][0]
        assert ordered_list["type"] == "orderedList"
        assert len(ordered_list["content"]) == 3

    def test_code_block(self):
        """Test converting code block."""
        result = markdown_to_adf("```python\nprint('hello')\n```")
        code_block = result["content"][0]
        assert code_block["type"] == "codeBlock"
        assert code_block["attrs"]["language"] == "python"
        assert code_block["content"][0]["text"] == "print('hello')"

    def test_code_block_no_language(self):
        """Test converting code block without language."""
        result = markdown_to_adf("```\nsome code\n```")
        code_block = result["content"][0]
        assert code_block["type"] == "codeBlock"
        assert "attrs" not in code_block or "language" not in code_block.get("attrs", {})

    def test_blockquote(self):
        """Test converting blockquote."""
        result = markdown_to_adf("> This is a quote")
        blockquote = result["content"][0]
        assert blockquote["type"] == "blockquote"

    def test_horizontal_rule(self):
        """Test converting horizontal rule."""
        result = markdown_to_adf("---")
        rule = result["content"][0]
        assert rule["type"] == "rule"

    def test_complex_document(self):
        """Test converting a complex markdown document."""
        md = """# Main Title

This is a paragraph with **bold** and *italic* text.

## Section 1

- Item 1
- Item 2

```python
def hello():
    print("world")
```

> A blockquote

[Link](https://example.com)
"""
        result = markdown_to_adf(md)
        assert result["version"] == 1
        assert result["type"] == "doc"

        # Check we have multiple content types
        content_types = [c["type"] for c in result["content"]]
        assert "heading" in content_types
        assert "paragraph" in content_types
        assert "bulletList" in content_types
        assert "codeBlock" in content_types
        assert "blockquote" in content_types


class TestAdfToText:
    """Tests for adf_to_text function."""

    def test_none_input(self):
        """Test handling None input."""
        assert adf_to_text(None) is None

    def test_string_input(self):
        """Test handling string input (passthrough)."""
        assert adf_to_text("plain text") == "plain text"

    def test_text_node(self):
        """Test extracting text from text node."""
        adf = {"type": "text", "text": "Hello"}
        assert adf_to_text(adf) == "Hello"

    def test_paragraph_with_text(self):
        """Test extracting text from paragraph."""
        adf = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "World"}
            ]
        }
        assert adf_to_text(adf) == "Hello \nWorld"

    def test_code_block(self):
        """Test extracting text from code block."""
        adf = {
            "type": "codeBlock",
            "content": [
                {"type": "text", "text": "print('hello')"}
            ]
        }
        result = adf_to_text(adf)
        assert "print('hello')" in result

    def test_document(self):
        """Test extracting text from full document."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello"}]
                }
            ]
        }
        assert adf_to_text(adf) == "Hello"


class TestRoundtrip:
    """Tests for markdown -> ADF -> text roundtrip."""

    def test_simple_roundtrip(self):
        """Test that simple text survives roundtrip."""
        original = "Hello World"
        adf = markdown_to_adf(original)
        text = adf_to_text(adf)
        assert original in text

    def test_heading_roundtrip(self):
        """Test that heading content survives roundtrip."""
        original = "# My Title"
        adf = markdown_to_adf(original)
        text = adf_to_text(adf)
        assert "My Title" in text
