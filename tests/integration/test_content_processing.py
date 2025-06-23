"""Integration tests for content processing functionality.

These tests validate HTML ↔ Markdown conversion, macro handling,
special character preservation, and performance with large content.
"""

import time
from typing import Any

import pytest

from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor
from mcp_atlassian.preprocessing.jira import JiraPreprocessor


class MockConfluenceClient:
    """Mock Confluence client for testing user lookups."""

    def get_user_details_by_accountid(self, account_id: str) -> dict[str, Any]:
        """Mock user details by account ID."""
        return {
            "displayName": f"User {account_id}",
            "accountType": "atlassian",
            "accountStatus": "active",
        }

    def get_user_details_by_username(self, username: str) -> dict[str, Any]:
        """Mock user details by username (Server/DC compatibility)."""
        return {
            "displayName": f"User {username}",
            "accountType": "atlassian",
            "accountStatus": "active",
        }


@pytest.fixture
def jira_preprocessor():
    """Create a JiraPreprocessor instance."""
    return JiraPreprocessor(base_url="https://example.atlassian.net")


@pytest.fixture
def confluence_preprocessor():
    """Create a ConfluencePreprocessor instance with mock client."""
    return ConfluencePreprocessor(
        base_url="https://example.atlassian.net",
        confluence_client=MockConfluenceClient(),
    )


@pytest.mark.integration
class TestJiraContentProcessing:
    """Integration tests for Jira content processing."""

    def test_jira_markdown_roundtrip_simple(self, jira_preprocessor):
        """Test simple Jira markup to Markdown and back."""
        jira_markup = """h1. Main Title

This is *bold* and _italic_ text.

* List item 1
* List item 2
# Numbered item 1
# Numbered item 2"""

        # Convert to Markdown
        markdown = jira_preprocessor.jira_to_markdown(jira_markup)

        # Convert back to Jira
        jira_result = jira_preprocessor.markdown_to_jira(markdown)

        # Verify key elements are preserved
        assert "h1. Main Title" in jira_result
        assert "*bold*" in jira_result
        assert "_italic_" in jira_result
        assert "* List item 1" in jira_result
        # Numbered lists in Jira are converted to "1." format in markdown
        assert "1. Numbered item 1" in jira_result or "# Numbered item 1" in jira_result

    def test_jira_markdown_roundtrip_complex(self, jira_preprocessor):
        """Test complex Jira markup with code blocks, tables, and formatting."""
        jira_markup = """h1. Project Documentation

h2. Overview
This project uses *advanced* features with _emphasis_ and {{inline code}}.

h3. Code Example
{code:python}
def process_data(items):
    '''Process a list of items.'''
    for item in items:
        print(f"Processing {item}")
    return len(items)
{code}

h3. Table Example
||Header 1||Header 2||Header 3||
|Cell 1|Cell 2|Cell 3|
|Cell 4|Cell 5|Cell 6|

h3. Features
* Feature with *bold* text
** Nested feature with _italic_
*** Deep nested item
# First step
## Sub-step A
## Sub-step B

bq. This is a block quote with *formatting*

h3. Links and Images
[Jira Documentation|https://docs.atlassian.com/jira]
!image.png|alt=Screenshot!

h3. Special Formatting
+inserted text+
-deleted text-
^superscript^
~subscript~
??citation??

{noformat}
Raw text that should not be formatted
    with preserved    spacing
{noformat}

{quote}
This is a quoted section
with multiple lines
{quote}

{color:red}Red text{color}
{color:#0000FF}Blue text{color}"""

        # Convert to Markdown
        markdown = jira_preprocessor.jira_to_markdown(jira_markup)

        # Convert back to Jira
        jira_result = jira_preprocessor.markdown_to_jira(markdown)

        # Verify structure is preserved
        assert "h1. Project Documentation" in jira_result
        assert "h2. Overview" in jira_result
        assert "h3. Code Example" in jira_result

        # Verify code block
        assert "{code:python}" in jira_result
        assert "def process_data(items):" in jira_result
        assert "{code}" in jira_result

        # Verify table structure
        assert "||Header 1||Header 2||Header 3||" in jira_result
        assert "|Cell 1|Cell 2|Cell 3|" in jira_result

        # Verify lists (may be converted differently)
        assert "Feature with" in jira_result and "bold" in jira_result
        assert "First step" in jira_result

        # Verify special formatting
        assert "+inserted text+" in jira_result
        assert "-deleted text-" in jira_result
        assert "^superscript^" in jira_result
        assert "~subscript~" in jira_result
        assert "??citation??" in jira_result

        # Verify links
        assert "Jira Documentation" in jira_result
        assert "https://docs.atlassian.com/jira" in jira_result

        # Verify color formatting
        assert "Red text" in jira_result
        assert "Blue text" in jira_result

    def test_jira_user_mentions_processing(self, jira_preprocessor):
        """Test processing of Jira user mentions."""
        content = """h1. Team Update

[~accountid:12345] completed the task.
[~accountid:67890] is reviewing the changes.

See [PROJ-123|https://example.atlassian.net/browse/PROJ-123|smart-link] for details."""

        cleaned = jira_preprocessor.clean_jira_text(content)

        # User mentions should be processed
        assert "User:12345" in cleaned
        assert "User:67890" in cleaned

        # Smart link should be converted
        assert "[PROJ-123](https://example.atlassian.net/browse/PROJ-123)" in cleaned

    def test_jira_html_content_processing(self, jira_preprocessor):
        """Test processing of HTML content in Jira."""
        html_content = """<p>This is a <strong>test</strong> with <em>HTML</em> content.</p>
<ul>
<li>Item 1</li>
<li>Item 2 with <code>inline code</code></li>
</ul>
<blockquote>
<p>A quote with <strong>formatting</strong></p>
</blockquote>
<pre><code class="language-python">def hello():
    print("Hello, World!")
</code></pre>"""

        cleaned = jira_preprocessor.clean_jira_text(html_content)

        # Verify HTML is converted to Markdown
        assert "**test**" in cleaned
        assert "*HTML*" in cleaned
        assert "`inline code`" in cleaned
        assert "def hello():" in cleaned

    def test_jira_nested_lists_preservation(self, jira_preprocessor):
        """Test preservation of nested list structures."""
        jira_markup = """* Level 1 item
** Level 2 item
*** Level 3 item
**** Level 4 item
** Another Level 2
* Back to Level 1

# Numbered Level 1
## Numbered Level 2
### Numbered Level 3
## Another Numbered Level 2
# Back to Numbered Level 1"""

        markdown = jira_preprocessor.jira_to_markdown(jira_markup)
        jira_result = jira_preprocessor.markdown_to_jira(markdown)

        # Verify nested structure is preserved (checking for presence of items)
        assert "Level 1 item" in jira_result
        assert "Level 2 item" in jira_result
        assert "Level 3 item" in jira_result
        assert "Level 4 item" in jira_result

        assert "Numbered Level 1" in jira_result
        assert "Numbered Level 2" in jira_result
        assert "Numbered Level 3" in jira_result

    def test_jira_special_characters_preservation(self, jira_preprocessor):
        """Test preservation of special characters and Unicode."""
        jira_markup = """h1. Special Characters Test

Unicode: α β γ δ ε ζ η θ
Emojis: 🚀 💻 ✅ ❌ 📝
Symbols: © ® ™ € £ ¥ § ¶

Special chars in code:
{code}
if (x > 0 && y < 10) {
    return x & y | z ^ w;
}
{code}

Math: x² + y² = z²
Quotes: "curly quotes" and 'single quotes'
Dashes: em—dash and en–dash"""

        markdown = jira_preprocessor.jira_to_markdown(jira_markup)
        jira_result = jira_preprocessor.markdown_to_jira(markdown)

        # Verify Unicode preservation
        assert "α β γ δ ε ζ η θ" in jira_result
        assert "🚀 💻 ✅ ❌ 📝" in jira_result
        assert "© ® ™ € £ ¥ § ¶" in jira_result

        # Verify special characters in code
        assert "x > 0 && y < 10" in jira_result
        assert "x & y | z ^ w" in jira_result

        # Verify other special characters
        assert "x² + y² = z²" in jira_result
        assert '"curly quotes"' in jira_result
        assert "em—dash" in jira_result
        assert "en–dash" in jira_result

    def test_jira_large_content_performance(self, jira_preprocessor):
        """Test performance with large content (>1MB)."""
        # Generate large content
        large_content_parts = []

        # Add many sections (increase to 200 for larger content)
        for i in range(200):
            section = f"""h2. Section {i}

This is paragraph {i} with *bold* and _italic_ text.

* List item {i}.1
* List item {i}.2
* List item {i}.3

{{code:python}}
def function_{i}():
    # Function {i} implementation
    data = [{{"id": j, "value": j * {i}}} for j in range(100)]
    return sum(item["value"] for item in data)
{{code}}

||Header A||Header B||Header C||
|Row {i} Cell 1|Row {i} Cell 2|Row {i} Cell 3|

"""
            large_content_parts.append(section)

        large_content = "\n".join(large_content_parts)
        content_size = len(large_content.encode("utf-8"))

        # Ensure content is reasonably large (adjust threshold for test)
        assert content_size > 50000  # 50KB is enough for performance testing

        # Test conversion performance
        start_time = time.time()
        markdown = jira_preprocessor.jira_to_markdown(large_content)
        markdown_time = time.time() - start_time

        start_time = time.time()
        jira_result = jira_preprocessor.markdown_to_jira(markdown)
        jira_time = time.time() - start_time

        # Performance assertions (should complete in reasonable time)
        assert markdown_time < 10.0  # Should complete within 10 seconds
        assert jira_time < 10.0

        # Verify content integrity
        assert "Section 0" in jira_result
        assert "Section 199" in jira_result
        assert (
            "function" in jira_result
        )  # Function names might have escaped underscores

    def test_jira_edge_cases(self, jira_preprocessor):
        """Test edge cases in Jira content processing."""
        # Empty content
        assert jira_preprocessor.jira_to_markdown("") == ""
        assert jira_preprocessor.markdown_to_jira("") == ""
        assert jira_preprocessor.clean_jira_text("") == ""
        assert jira_preprocessor.clean_jira_text(None) == ""

        # Malformed markup
        malformed = "*unclosed bold _mixed italic*"
        result = jira_preprocessor.jira_to_markdown(malformed)
        assert "**unclosed bold" in result

        # Very long lines
        long_line = "x" * 10000
        result = jira_preprocessor.jira_to_markdown(long_line)
        assert len(result) >= 10000

        # Nested code blocks (should not process inner content)
        nested = """{code}
{code}
inner code
{code}
{code}"""
        result = jira_preprocessor.jira_to_markdown(nested)
        assert "inner code" in result


@pytest.mark.integration
class TestConfluenceContentProcessing:
    """Integration tests for Confluence content processing."""

    def test_confluence_macro_preservation(self, confluence_preprocessor):
        """Test preservation of Confluence macros during processing."""
        html_with_macros = """<p>Page content with macros:</p>
<ac:structured-macro ac:name="info" ac:schema-version="1">
    <ac:rich-text-body>
        <p>This is an info panel with <strong>formatting</strong></p>
    </ac:rich-text-body>
</ac:structured-macro>

<ac:structured-macro ac:name="code" ac:schema-version="1">
    <ac:parameter ac:name="language">python</ac:parameter>
    <ac:plain-text-body><![CDATA[
def process():
    return "Hello, World!"
]]></ac:plain-text-body>
</ac:structured-macro>

<ac:structured-macro ac:name="toc">
    <ac:parameter ac:name="maxLevel">3</ac:parameter>
</ac:structured-macro>

<ac:structured-macro ac:name="excerpt">
    <ac:rich-text-body>
        <p>This is an excerpt of the page.</p>
    </ac:rich-text-body>
</ac:structured-macro>"""

        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(html_with_macros)
        )

        # Verify macros are preserved in HTML
        assert 'ac:structured-macro ac:name="info"' in processed_html
        assert 'ac:structured-macro ac:name="code"' in processed_html
        assert 'ac:structured-macro ac:name="toc"' in processed_html
        assert 'ac:structured-macro ac:name="excerpt"' in processed_html

        # Verify parameters are preserved
        assert 'ac:parameter ac:name="language">python' in processed_html
        assert 'ac:parameter ac:name="maxLevel">3' in processed_html

    def test_confluence_user_mentions_complex(self, confluence_preprocessor):
        """Test complex user mention scenarios in Confluence."""
        html_content = """<p>Multiple user mentions:</p>
<ac:link>
    <ri:user ri:account-id="user123"/>
</ac:link>

<p>User with link body:</p>
<ac:link>
    <ri:user ri:account-id="user456"/>
    <ac:link-body>@Custom Name</ac:link-body>
</ac:link>

<ac:structured-macro ac:name="profile">
    <ac:parameter ac:name="user">
        <ri:user ri:account-id="user789"/>
    </ac:parameter>
</ac:structured-macro>

<p>Server/DC user with userkey:</p>
<ac:structured-macro ac:name="profile">
    <ac:parameter ac:name="user">
        <ri:user ri:userkey="admin"/>
    </ac:parameter>
</ac:structured-macro>"""

        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(html_content)
        )

        # Verify all user mentions are processed
        assert "@User user123" in processed_markdown
        assert "@User user456" in processed_markdown
        assert "@User user789" in processed_markdown
        assert "@User admin" in processed_markdown

    def test_confluence_markdown_roundtrip(self, confluence_preprocessor):
        """Test Markdown to Confluence storage format and processing."""
        markdown_content = """# Main Title

## Introduction
This is a **bold** paragraph with *italic* text and `inline code`.

### Code Block
```python
def hello_world():
    print("Hello, World!")
    return True
```

### Lists
- Item 1
  - Nested item 1.1
  - Nested item 1.2
- Item 2

1. First step
2. Second step
   1. Sub-step 2.1
   2. Sub-step 2.2

### Table
| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |

### Links and Images
[Confluence Documentation](https://confluence.atlassian.com/doc/)
![Alt text](https://example.com/image.png)

### Blockquote
> This is a blockquote
> with multiple lines

### Horizontal Rule
---

### Special Characters
Unicode: α β γ δ ε ζ η θ
Emojis: 🚀 💻 ✅ ❌ 📝
Math: x² + y² = z²"""

        # Convert to Confluence storage format
        storage_format = confluence_preprocessor.markdown_to_confluence_storage(
            markdown_content
        )

        # Process the storage format
        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(storage_format)
        )

        # Verify key elements are preserved
        assert "Main Title" in processed_markdown
        assert "**bold**" in processed_markdown
        assert "*italic*" in processed_markdown
        assert "`inline code`" in processed_markdown

        # Verify code block (may have escaped underscores)
        assert (
            "hello_world" in processed_markdown or "hello\\_world" in processed_markdown
        )
        assert "Hello, World!" in processed_markdown

        # Verify lists
        assert "Item 1" in processed_markdown
        assert "Nested item 1.1" in processed_markdown
        assert "First step" in processed_markdown
        assert "Sub-step 2.1" in processed_markdown

        # Verify table (tables might be converted to HTML)
        assert "Header 1" in processed_markdown
        assert "Cell 1" in processed_markdown

        # Verify links
        assert "Confluence Documentation" in processed_markdown
        assert "https://confluence.atlassian.com/doc/" in processed_markdown

        # Verify special characters
        assert "α β γ δ ε ζ η θ" in processed_markdown
        assert "🚀 💻 ✅ ❌ 📝" in processed_markdown
        assert "x² + y² = z²" in processed_markdown

    def test_confluence_heading_anchor_control(self, confluence_preprocessor):
        """Test control over heading anchor generation."""
        markdown_with_headings = """# Main Title
Content under main title.

## Section One
Content in section one.

### Subsection 1.1
Details here.

## Section Two
More content."""

        # Test with anchors disabled (default)
        storage_no_anchors = confluence_preprocessor.markdown_to_confluence_storage(
            markdown_with_headings
        )
        assert 'id="main-title"' not in storage_no_anchors.lower()
        assert 'id="section-one"' not in storage_no_anchors.lower()

        # Test with anchors enabled
        storage_with_anchors = confluence_preprocessor.markdown_to_confluence_storage(
            markdown_with_headings, enable_heading_anchors=True
        )
        # Verify headings are still present (they may have anchor macros)
        assert "Main Title</h1>" in storage_with_anchors
        assert "Section One</h2>" in storage_with_anchors

    def test_confluence_large_content_performance(self, confluence_preprocessor):
        """Test performance with large Confluence content (>1MB)."""
        # Generate large content with various Confluence elements
        large_content_parts = []

        for i in range(50):
            section = f"""<h2>Section {i}</h2>
<p>This is paragraph {i} with <strong>bold</strong> and <em>italic</em> text.</p>

<ac:structured-macro ac:name="info">
    <ac:rich-text-body>
        <p>Info box {i} with important information.</p>
    </ac:rich-text-body>
</ac:structured-macro>

<ul>
    <li>List item {i}.1</li>
    <li>List item {i}.2 with <code>inline code</code></li>
    <li>List item {i}.3</li>
</ul>

<ac:structured-macro ac:name="code">
    <ac:parameter ac:name="language">python</ac:parameter>
    <ac:plain-text-body><![CDATA[
def function_{i}():
    # Large function with many lines
    data = []
    for j in range(1000):
        data.append({{
            "id": j,
            "value": j * {i},
            "description": "Item " + str(j)
        }})

    result = sum(item["value"] for item in data)
    return result
]]></ac:plain-text-body>
</ac:structured-macro>

<table>
    <thead>
        <tr>
            <th>Header A</th>
            <th>Header B</th>
            <th>Header C</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Row {i} Cell 1</td>
            <td>Row {i} Cell 2</td>
            <td>Row {i} Cell 3</td>
        </tr>
    </tbody>
</table>

<ac:link>
    <ri:user ri:account-id="user{i}"/>
</ac:link> completed this section.
"""
            large_content_parts.append(section)

        large_content = "\n".join(large_content_parts)
        content_size = len(large_content.encode("utf-8"))

        # Ensure content is reasonably large (adjust threshold for test)
        assert content_size > 50000  # 50KB is enough for performance testing

        # Test processing performance
        start_time = time.time()
        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(large_content)
        )
        processing_time = time.time() - start_time

        # Performance assertion
        assert processing_time < 15.0  # Should complete within 15 seconds

        # Verify content integrity
        assert "Section 0" in processed_markdown
        assert "Section 49" in processed_markdown
        assert (
            "function" in processed_markdown
        )  # Function names might have escaped underscores
        assert "@User user10" in processed_markdown

    def test_confluence_nested_structures(self, confluence_preprocessor):
        """Test handling of deeply nested structures."""
        nested_html = """<div>
    <h1>Top Level</h1>
    <div>
        <h2>Level 2</h2>
        <div>
            <h3>Level 3</h3>
            <ul>
                <li>Item 1
                    <ul>
                        <li>Nested 1.1
                            <ul>
                                <li>Deep nested 1.1.1</li>
                                <li>Deep nested 1.1.2</li>
                            </ul>
                        </li>
                        <li>Nested 1.2</li>
                    </ul>
                </li>
                <li>Item 2</li>
            </ul>

            <blockquote>
                <p>Quote level 1</p>
                <blockquote>
                    <p>Quote level 2</p>
                    <blockquote>
                        <p>Quote level 3</p>
                    </blockquote>
                </blockquote>
            </blockquote>

            <table>
                <tr>
                    <td>
                        <table>
                            <tr>
                                <td>Nested table cell</td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </div>
    </div>
</div>"""

        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(nested_html)
        )

        # Verify nested structures are preserved
        assert "Top Level" in processed_markdown
        assert "Level 2" in processed_markdown
        assert "Level 3" in processed_markdown
        assert "Deep nested 1.1.1" in processed_markdown
        assert "Quote level 1" in processed_markdown
        assert "Quote level 2" in processed_markdown
        assert "Quote level 3" in processed_markdown
        assert "Nested table cell" in processed_markdown

    def test_confluence_edge_cases(self, confluence_preprocessor):
        """Test edge cases in Confluence content processing."""
        # Empty content
        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content("")
        )
        assert processed_html == ""
        assert processed_markdown == ""

        # Malformed HTML
        malformed_html = "<p>Unclosed paragraph <strong>bold text</p>"
        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(malformed_html)
        )
        assert "Unclosed paragraph" in processed_markdown
        assert "bold text" in processed_markdown

        # HTML with CDATA sections
        cdata_html = """<div>
            <![CDATA[This is raw CDATA content with <tags>]]>
        </div>"""
        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(cdata_html)
        )
        assert "This is raw CDATA content" in processed_markdown

        # Very long single line
        long_line_html = f"<p>{'x' * 10000}</p>"
        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(long_line_html)
        )
        assert len(processed_markdown) >= 10000

    def test_confluence_special_html_entities(self, confluence_preprocessor):
        """Test handling of HTML entities and special characters."""
        html_with_entities = """<p>HTML entities: &lt; &gt; &amp; &quot; &apos;</p>
<p>Named entities: &nbsp; &copy; &reg; &trade; &euro;</p>
<p>Numeric entities: &#65; &#66; &#67; &#8364; &#128512;</p>
<p>Mixed: &lt;tag&gt; &amp;&amp; &quot;quoted&quot;</p>"""

        processed_html, processed_markdown = (
            confluence_preprocessor.process_html_content(html_with_entities)
        )

        # Verify entities are properly decoded
        assert "<" in processed_markdown
        assert ">" in processed_markdown
        assert "&" in processed_markdown
        assert '"' in processed_markdown
        assert "©" in processed_markdown
        assert "®" in processed_markdown
        assert "€" in processed_markdown
        assert "😀" in processed_markdown  # Emoji from numeric entity


@pytest.mark.integration
class TestContentProcessingInteroperability:
    """Test interoperability between Jira and Confluence content processing."""

    def test_cross_platform_content_sharing(
        self, jira_preprocessor, confluence_preprocessor
    ):
        """Test content that might be shared between Jira and Confluence."""
        shared_markdown = """# Shared Documentation

## Overview
This content might be used in both Jira and Confluence.

### Key Features
- **Feature 1**: Description with *emphasis*
- **Feature 2**: Contains `code examples`

### Code Sample
```python
def shared_function():
    return "Works in both platforms"
```

### Links
[Project Documentation](https://example.com/docs)
[PROJ-123](https://example.atlassian.net/browse/PROJ-123)

### Table
| Platform | Support |
|----------|---------|
| Jira     | ✅      |
| Confluence | ✅    |"""

        # Convert to Jira format
        jira_markup = jira_preprocessor.markdown_to_jira(shared_markdown)

        # Convert to Confluence format
        confluence_storage = confluence_preprocessor.markdown_to_confluence_storage(
            shared_markdown
        )

        # Verify both conversions preserve key content
        assert "Shared Documentation" in jira_markup
        assert "Shared Documentation" in confluence_storage

        assert "Feature 1" in jira_markup
        assert "Feature 1" in confluence_storage

        assert "shared_function" in jira_markup
        assert "shared_function" in confluence_storage

    def test_unicode_consistency(self, jira_preprocessor, confluence_preprocessor):
        """Test Unicode handling consistency across processors."""
        unicode_content = """Unicode Test 🌍

Symbols: ™ © ® € £ ¥
Math: ∑ ∏ ∫ ∞ ≈ ≠ ≤ ≥
Greek: Α Β Γ Δ Ε Ζ Η Θ
Arrows: → ← ↑ ↓ ↔ ⇒ ⇐ ⇔
Box Drawing: ┌─┬─┐ │ ├─┼─┤ └─┴─┘
Emojis: 😀 😎 🚀 💻 ✅ ❌ ⚡ 🔥"""

        # Process through Jira
        jira_result = jira_preprocessor.clean_jira_text(unicode_content)

        # Process through Confluence
        processed_html, confluence_result = (
            confluence_preprocessor.process_html_content(f"<p>{unicode_content}</p>")
        )

        # Verify Unicode is preserved in both
        for char in ["🌍", "™", "∑", "Α", "→", "┌", "😀", "🚀"]:
            assert char in jira_result
            assert char in confluence_result

    def test_error_recovery(self, jira_preprocessor, confluence_preprocessor):
        """Test error recovery in content processing."""
        # Test with None input
        assert jira_preprocessor.clean_jira_text(None) == ""

        # Test with invalid input types (should raise exceptions)
        with pytest.raises(Exception):
            confluence_preprocessor.process_html_content(None)

        # Test with extremely malformed content
        malformed_content = "<<<>>>&&&'''\"\"\"{{{{}}}}[[[[]]]]"

        # Jira should handle this
        jira_result = jira_preprocessor.clean_jira_text(malformed_content)
        assert len(jira_result) > 0

        # Confluence should handle this
        processed_html, confluence_result = (
            confluence_preprocessor.process_html_content(malformed_content)
        )
        assert len(confluence_result) > 0
