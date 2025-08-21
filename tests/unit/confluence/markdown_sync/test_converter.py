"""Tests for the markdown converter module."""

import os
import tempfile

import pytest

from mcp_atlassian.confluence.markdown_sync.converter import (
    FrontmatterParser,
    MarkdownConverter,
    MarkdownSyncError,
    ParsedMarkdownFile,
)


class TestFrontmatterParser:
    """Test the FrontmatterParser class."""

    def test_parse_with_frontmatter(self):
        """Test parsing content with valid frontmatter."""
        parser = FrontmatterParser()
        content = """---
title: Test Page
space_key: TEST
tags: [documentation, test]
---

# Test Content

This is a test page.
"""
        frontmatter, remaining = parser.parse(content)

        assert frontmatter["title"] == "Test Page"
        assert frontmatter["space_key"] == "TEST"
        assert frontmatter["tags"] == ["documentation", "test"]
        assert remaining.strip().startswith("# Test Content")

    def test_parse_without_frontmatter(self):
        """Test parsing content without frontmatter."""
        parser = FrontmatterParser()
        content = """# Test Content

This is a test page without frontmatter.
"""
        frontmatter, remaining = parser.parse(content)

        assert frontmatter == {}
        assert remaining == content

    def test_parse_invalid_yaml(self):
        """Test parsing content with invalid YAML frontmatter."""
        parser = FrontmatterParser()
        content = """---
title: Test Page
invalid: [unclosed list
---

# Test Content
"""
        frontmatter, remaining = parser.parse(content)

        # Should return empty frontmatter and original content on YAML error
        assert frontmatter == {}
        assert remaining == content


class TestMarkdownConverter:
    """Test the MarkdownConverter class."""

    def test_parse_markdown_file(self):
        """Test parsing a markdown file."""
        converter = MarkdownConverter()

        # Create a temporary markdown file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("""---
title: Test Document
space_key: TEST
---

# Test Document

This is a test document with **bold** text and `code`.

## Section 2

- Item 1
- Item 2
""")
            temp_path = f.name

        try:
            parsed = converter.parse_markdown_file(temp_path)

            assert isinstance(parsed, ParsedMarkdownFile)
            assert parsed.title == "Test Document"
            assert parsed.frontmatter["space_key"] == "TEST"
            assert "# Test Document" in parsed.markdown_content
            assert "<h1>Test Document</h1>" in parsed.confluence_content
            assert parsed.content_hash is not None

        finally:
            os.unlink(temp_path)

    def test_parse_nonexistent_file(self):
        """Test parsing a file that doesn't exist."""
        converter = MarkdownConverter()

        with pytest.raises(MarkdownSyncError) as exc_info:
            converter.parse_markdown_file("/nonexistent/file.md")

        assert "FILE_NOT_FOUND" in str(exc_info.value.code)

    def test_extract_title_from_frontmatter(self):
        """Test title extraction from frontmatter."""
        converter = MarkdownConverter()
        frontmatter = {"title": "Frontmatter Title"}
        content = "# Content Title"

        title = converter._extract_title(frontmatter, content, "test.md")
        assert title == "Frontmatter Title"

    def test_extract_title_from_h1(self):
        """Test title extraction from H1 heading."""
        converter = MarkdownConverter()
        frontmatter = {}
        content = "# Content Title\n\nSome content"

        title = converter._extract_title(frontmatter, content, "test.md")
        assert title == "Content Title"

    def test_extract_title_from_filename(self):
        """Test title extraction from filename as fallback."""
        converter = MarkdownConverter()
        frontmatter = {}
        content = "Some content without heading"

        title = converter._extract_title(frontmatter, content, "/path/to/test-file.md")
        assert title == "test-file"

    def test_markdown_to_confluence_storage(self):
        """Test markdown to Confluence storage format conversion."""
        converter = MarkdownConverter()
        markdown = """# Heading 1

## Heading 2

This is **bold** and *italic* text.

`inline code`

```python
def hello():
    print("Hello, world!")
```

[Link text](https://example.com)

- List item 1
- List item 2
"""

        storage = converter._markdown_to_confluence_storage(markdown)

        assert "<h1>Heading 1</h1>" in storage
        assert "<h2>Heading 2</h2>" in storage
        assert "<strong>bold</strong>" in storage
        assert "<em>italic</em>" in storage
        assert "<code>inline code</code>" in storage
        assert "ac:structured-macro" in storage  # Code block macro
        assert '<a href="https://example.com">Link text</a>' in storage
        assert "<li>List item 1</li>" in storage

    def test_confluence_storage_to_markdown(self):
        """Test Confluence storage to markdown conversion."""
        converter = MarkdownConverter()
        storage = """<h1>Heading 1</h1>

<h2>Heading 2</h2>

<p>This is <strong>bold</strong> and <em>italic</em> text.</p>

<p><code>inline code</code></p>

<p><a href="https://example.com">Link text</a></p>

<ul><li>List item 1</li><li>List item 2</li></ul>"""

        markdown = converter.confluence_storage_to_markdown(storage)

        assert "# Heading 1" in markdown
        assert "## Heading 2" in markdown
        assert "**bold**" in markdown
        assert "*italic*" in markdown
        assert "`inline code`" in markdown
        assert "[Link text](https://example.com)" in markdown
        assert "- List item 1" in markdown

    def test_create_frontmatter(self):
        """Test creating frontmatter from page data."""
        converter = MarkdownConverter()
        page_data = {
            "id": "123456",
            "title": "Test Page",
            "space": {"key": "TEST"},
            "version": {
                "number": 5,
                "when": "2023-12-01T10:00:00.000Z",
                "by": {"displayName": "Test User"},
            },
        }

        frontmatter = converter.create_frontmatter(page_data)

        assert "confluence_page_id: '123456'" in frontmatter
        assert "confluence_space_key: TEST" in frontmatter
        assert "confluence_title: Test Page" in frontmatter
        assert "confluence_version: 5" in frontmatter
        assert "last_modified: '2023-12-01T10:00:00.000Z'" in frontmatter
        assert "last_modified_by: Test User" in frontmatter


if __name__ == "__main__":
    pytest.main([__file__])
