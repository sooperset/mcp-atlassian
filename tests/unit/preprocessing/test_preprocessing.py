import re

import pytest

from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor
from mcp_atlassian.preprocessing.jira import JiraPreprocessor
from tests.fixtures.confluence_mocks import MOCK_COMMENTS_RESPONSE, MOCK_PAGE_RESPONSE
from tests.fixtures.jira_mocks import MOCK_JIRA_ISSUE_RESPONSE
from tests.utils.mocks import MockConfluenceClient


@pytest.fixture
def preprocessor_with_jira():
    return JiraPreprocessor(base_url="https://example.atlassian.net")


@pytest.fixture
def preprocessor_with_jira_markup_translation_disabled():
    return JiraPreprocessor(
        base_url="https://example.atlassian.net", disable_translation=True
    )


@pytest.fixture
def preprocessor_with_confluence():
    return ConfluencePreprocessor(base_url="https://example.atlassian.net")


def test_init():
    """Test JiraPreprocessor initialization."""
    processor = JiraPreprocessor("https://example.atlassian.net/")
    assert processor.base_url == "https://example.atlassian.net"


def test_process_confluence_page_content(preprocessor_with_confluence):
    """Test processing Confluence page content using mock data."""
    html_content = MOCK_PAGE_RESPONSE["body"]["storage"]["value"]
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html_content, confluence_client=MockConfluenceClient()
        )
    )

    # Verify user mention is processed
    assert "@Test User user123" in processed_markdown

    # Verify basic HTML elements are converted
    assert "Date" in processed_markdown
    assert "Goals" in processed_markdown
    assert "Example goal" in processed_markdown


def test_process_confluence_comment_content(preprocessor_with_confluence):
    """Test processing Confluence comment content using mock data."""
    html_content = MOCK_COMMENTS_RESPONSE["results"][0]["body"]["view"]["value"]
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html_content, confluence_client=MockConfluenceClient()
        )
    )

    assert "Comment content here" in processed_markdown


def test_clean_jira_issue_content(preprocessor_with_jira):
    """Test cleaning Jira issue content using mock data."""
    description = MOCK_JIRA_ISSUE_RESPONSE["fields"]["description"]
    cleaned_text = preprocessor_with_jira.clean_jira_text(description)

    assert "test issue description" in cleaned_text.lower()

    # Test comment cleaning
    comment = MOCK_JIRA_ISSUE_RESPONSE["fields"]["comment"]["comments"][0]["body"]
    cleaned_comment = preprocessor_with_jira.clean_jira_text(comment)

    assert "test comment" in cleaned_comment.lower()


def test_process_html_content_basic(preprocessor_with_confluence):
    """Test basic HTML content processing."""
    html = "<p>Simple text</p>"
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html, confluence_client=MockConfluenceClient()
        )
    )

    assert processed_html == "<p>Simple text</p>"
    assert processed_markdown.strip() == "Simple text"


def test_process_html_content_with_user_mentions(preprocessor_with_confluence):
    """Test HTML content processing with user mentions."""
    html = """
    <ac:link>
        <ri:user ri:account-id="123456"/>
    </ac:link>
    <p>Some text</p>
    """
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html, confluence_client=MockConfluenceClient()
        )
    )

    assert "@Test User 123456" in processed_html
    assert "@Test User 123456" in processed_markdown


def test_clean_jira_text_empty(preprocessor_with_jira):
    """Test cleaning empty Jira text."""
    assert preprocessor_with_jira.clean_jira_text("") == ""
    assert preprocessor_with_jira.clean_jira_text(None) == ""


def test_clean_jira_text_user_mentions(preprocessor_with_jira):
    """Test cleaning Jira text with user mentions."""
    text = "Hello [~accountid:123456]!"
    cleaned = preprocessor_with_jira.clean_jira_text(text)
    assert cleaned == "Hello User:123456!"


def test_clean_jira_text_smart_links(preprocessor_with_jira):
    """Test cleaning Jira text with smart links."""
    base_url = "https://example.atlassian.net"

    # Test Jira issue link
    text = f"[Issue|{base_url}/browse/PROJ-123|smart-link]"
    cleaned = preprocessor_with_jira.clean_jira_text(text)
    assert cleaned == f"[PROJ-123]({base_url}/browse/PROJ-123)"

    # Test Confluence page link from mock data
    confluence_url = (
        f"{base_url}/wiki/spaces/PROJ/pages/987654321/Example+Meeting+Notes"
    )
    processed_url = f"{base_url}/wiki/spaces/PROJ/pages/987654321/ExampleMeetingNotes"
    text = f"[Meeting Notes|{confluence_url}|smart-link]"
    cleaned = preprocessor_with_jira.clean_jira_text(text)
    assert cleaned == f"[Example Meeting Notes]({processed_url})"


def test_clean_jira_text_html_content(preprocessor_with_jira):
    """Test cleaning Jira text with HTML content."""
    text = "<p>This is <b>bold</b> text</p>"
    cleaned = preprocessor_with_jira.clean_jira_text(text)
    assert cleaned.strip() == "This is **bold** text"


def test_clean_jira_text_combined(preprocessor_with_jira):
    """Test cleaning Jira text with multiple elements."""
    base_url = "https://example.atlassian.net"
    text = f"""
    <p>Hello [~accountid:123456]!</p>
    <p>Check out [PROJ-123|{base_url}/browse/PROJ-123|smart-link]</p>
    """
    cleaned = preprocessor_with_jira.clean_jira_text(text)
    assert "Hello User:123456!" in cleaned
    assert f"[PROJ-123]({base_url}/browse/PROJ-123)" in cleaned


def test_process_html_content_error_handling(preprocessor_with_confluence):
    """Test error handling in process_html_content."""
    with pytest.raises(Exception):
        preprocessor_with_confluence.process_html_content(
            None, confluence_client=MockConfluenceClient()
        )


def test_clean_jira_text_with_invalid_html(preprocessor_with_jira):
    """Test cleaning Jira text with invalid HTML."""
    text = "<p>Unclosed paragraph with <b>bold</b"
    cleaned = preprocessor_with_jira.clean_jira_text(text)
    assert "Unclosed paragraph with **bold**" in cleaned


def test_process_mentions_error_handling(preprocessor_with_jira):
    """Test error handling in _process_mentions."""
    text = "[~accountid:invalid]"
    processed = preprocessor_with_jira._process_mentions(text, r"\[~accountid:(.*?)\]")
    assert "User:invalid" in processed


def test_jira_to_markdown(preprocessor_with_jira):
    """Test conversion of Jira markup to Markdown."""
    # Test headers
    assert preprocessor_with_jira.jira_to_markdown("h1. Heading 1") == "# Heading 1"
    assert preprocessor_with_jira.jira_to_markdown("h2. Heading 2") == "## Heading 2"

    # Test text formatting
    assert preprocessor_with_jira.jira_to_markdown("*bold text*") == "**bold text**"
    assert preprocessor_with_jira.jira_to_markdown("_italic text_") == "*italic text*"

    # Test code blocks
    assert preprocessor_with_jira.jira_to_markdown("{{code}}") == "`code`"

    # For multiline code blocks, check content is preserved rather than exact format
    converted_code_block = preprocessor_with_jira.jira_to_markdown(
        "{code}\nmultiline code\n{code}"
    )
    assert "```" in converted_code_block
    assert "multiline code" in converted_code_block

    # Test lists
    assert preprocessor_with_jira.jira_to_markdown("* Item 1") == "- Item 1"
    assert preprocessor_with_jira.jira_to_markdown("# Item 1") == "1. Item 1"

    # Test complex Jira markup
    complex_jira = """
h1. Project Overview

h2. Introduction
This project aims to *improve* the user experience.

h3. Features
* Feature 1
* Feature 2

h3. Code Example
{code:python}
def hello():
    print("Hello World")
{code}

For more information, see [our website|https://example.com].
"""

    converted = preprocessor_with_jira.jira_to_markdown(complex_jira)
    assert "# Project Overview" in converted
    assert "## Introduction" in converted
    assert "**improve**" in converted
    assert "- Feature 1" in converted
    assert "```python" in converted
    assert "[our website](https://example.com)" in converted


def test_jira_to_markdown_citation(preprocessor_with_jira):
    """Test citation markup conversion and that unmatched ?? does not cause ReDoS."""
    # Matched citation
    assert "<cite>cited text</cite>" in preprocessor_with_jira.jira_to_markdown(
        "??cited text??"
    )

    # Citation with a single ? inside
    result = preprocessor_with_jira.jira_to_markdown("??is this cited? yes??")
    assert "<cite>" in result

    # Unmatched ?? followed by inline code must complete quickly (was ReDoS before fix)
    text = "* (??) Some weird formatting"
    result = preprocessor_with_jira.jira_to_markdown(text)
    assert "<cite>" not in result


def test_jira_to_markdown_citation_no_redos(preprocessor_with_jira):
    """Regression test: complex Jira wiki markup with unmatched ?? must not hang."""
    description = (
        "h2. Known limitations\n"
        "* (??) The {{retry-handler}} -> {{fallback}} path is *broken* "
        "if the upstream timeout during {{retry-handler}} has not "
        "elapsed yet. Each component would need to track pending "
        "requests and report a metric. _This means a request could "
        "be stuck in {{retry-handler}} indefinitely._\n"
        "* Each component must validate the configuration and *stop* "
        "after detecting an invalid setting.\n"
        "h2. Monitoring\n"
        "* Report the current status through a *metric*."
    )
    result = preprocessor_with_jira.jira_to_markdown(description)
    assert "Known limitations" in result
    assert "retry-handler" in result


def test_markdown_to_jira(preprocessor_with_jira):
    """Test conversion of Markdown to Jira markup."""
    # Test headers
    assert preprocessor_with_jira.markdown_to_jira("# Heading 1") == "h1. Heading 1"
    assert preprocessor_with_jira.markdown_to_jira("## Heading 2") == "h2. Heading 2"

    # Test text formatting
    assert preprocessor_with_jira.markdown_to_jira("**bold text**") == "*bold text*"
    assert preprocessor_with_jira.markdown_to_jira("*italic text*") == "_italic text_"

    # Test code blocks
    assert preprocessor_with_jira.markdown_to_jira("`code`") == "{{code}}"

    # For multiline code blocks, check content is preserved rather than exact format
    converted_code_block = preprocessor_with_jira.markdown_to_jira(
        "```\nmultiline code\n```"
    )
    assert "{code}" in converted_code_block
    assert "multiline code" in converted_code_block

    # Test lists
    list_conversion = preprocessor_with_jira.markdown_to_jira("- Item 1")
    assert "* Item 1" in list_conversion

    numbered_list = preprocessor_with_jira.markdown_to_jira("1. Item 1")
    assert "Item 1" in numbered_list
    assert "1" in numbered_list

    # Test complex Markdown
    complex_markdown = """
# Project Overview

## Introduction
This project aims to **improve** the user experience.

### Features
- Feature 1
- Feature 2

### Code Example
```python
def hello():
    print("Hello World")
```

For more information, see [our website](https://example.com).
"""

    converted = preprocessor_with_jira.markdown_to_jira(complex_markdown)
    assert "h1. Project Overview" in converted
    assert "h2. Introduction" in converted
    assert "*improve*" in converted
    assert "* Feature 1" in converted
    assert "{code:python}" in converted
    assert "[our website|https://example.com]" in converted


def test_markdown_nested_bullet_list_2space(preprocessor_with_jira):
    """Test that 2-space indented bullet lists convert correctly to Jira format."""
    markdown = "* Item A\n  * Sub-item A.1\n    * Sub-sub A.1.1\n* Item B"
    expected = "* Item A\n** Sub-item A.1\n*** Sub-sub A.1.1\n* Item B"
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert result == expected


def test_markdown_nested_numbered_list_2space(preprocessor_with_jira):
    """Test that 2-space indented numbered lists convert correctly to Jira format."""
    markdown = "1. Item A\n  1. Sub-item A.1\n    1. Sub-sub A.1.1\n2. Item B"
    expected = "# Item A\n## Sub-item A.1\n### Sub-sub A.1.1\n# Item B"
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert result == expected


def test_jira_markup_translation_disabled(
    preprocessor_with_jira_markup_translation_disabled,
):
    """Test that markup translation is disabled and original text is preserved."""
    mixed_markup = "h1. Jira Heading with **markdown bold** and {{jira code}} and *markdown italic*"

    # Both methods should return the original text unchanged
    assert (
        preprocessor_with_jira_markup_translation_disabled.markdown_to_jira(
            mixed_markup
        )
        == mixed_markup
    )
    assert (
        preprocessor_with_jira_markup_translation_disabled.jira_to_markdown(
            mixed_markup
        )
        == mixed_markup
    )

    # clean_jira_text should also preserve markup (only process mentions/links)
    result = preprocessor_with_jira_markup_translation_disabled.clean_jira_text(
        mixed_markup
    )
    assert "h1. Jira Heading" in result
    assert "**markdown bold**" in result
    assert "{{jira code}}" in result


def test_markdown_to_confluence_storage(preprocessor_with_confluence):
    """Test conversion of Markdown to Confluence storage format."""
    markdown = """# Heading 1

This is some **bold** and *italic* text.

- List item 1
- List item 2

[Link text](https://example.com)
"""

    # Convert markdown to storage format
    storage_format = preprocessor_with_confluence.markdown_to_confluence_storage(
        markdown
    )

    # Verify basic structure (we don't need to test the exact conversion, as that's handled by md2conf)
    assert "<h1>" in storage_format
    assert "Heading 1" in storage_format
    assert "<strong>" in storage_format or "<b>" in storage_format  # Bold
    assert "<em>" in storage_format or "<i>" in storage_format  # Italic
    assert "<a href=" in storage_format.lower()  # Link
    assert "example.com" in storage_format


def test_process_confluence_profile_macro(preprocessor_with_confluence):
    """Test processing Confluence User Profile Macro in page content."""
    html_content = MOCK_PAGE_RESPONSE["body"]["storage"]["value"]
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html_content, confluence_client=MockConfluenceClient()
        )
    )
    # Should replace macro with @Test User user123
    assert "@Test User user123" in processed_html
    assert "@Test User user123" in processed_markdown


def test_process_confluence_profile_macro_malformed(preprocessor_with_confluence):
    """Test processing malformed User Profile Macro (missing user param and ri:user)."""
    # Macro missing ac:parameter
    html_missing_param = '<ac:structured-macro ac:name="profile"></ac:structured-macro>'
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html_missing_param, confluence_client=MockConfluenceClient()
        )
    )
    assert "[User Profile Macro (Malformed)]" in processed_html
    assert "[User Profile Macro (Malformed)]" in processed_markdown

    # Macro with ac:parameter but missing ri:user
    html_missing_riuser = '<ac:structured-macro ac:name="profile"><ac:parameter ac:name="user"></ac:parameter></ac:structured-macro>'
    processed_html, processed_markdown = (
        preprocessor_with_confluence.process_html_content(
            html_missing_riuser, confluence_client=MockConfluenceClient()
        )
    )
    assert "[User Profile Macro (Malformed)]" in processed_html
    assert "[User Profile Macro (Malformed)]" in processed_markdown


def test_process_confluence_profile_macro_fallback():
    """Test fallback when confluence_client is None."""
    from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor

    html = (
        '<ac:structured-macro ac:name="profile">'
        '<ac:parameter ac:name="user">'
        '<ri:user ri:account-id="user999" />'
        "</ac:parameter>"
        "</ac:structured-macro>"
    )
    preprocessor = ConfluencePreprocessor(base_url="https://example.atlassian.net")
    processed_html, processed_markdown = preprocessor.process_html_content(
        html, confluence_client=None
    )
    assert "[User Profile: user999]" in processed_html
    assert "[User Profile: user999]" in processed_markdown


def test_process_user_profile_macro_multiple():
    """Test processing multiple User Profile Macros with account-id and userkey."""
    from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor

    html = (
        "<p>This page mentions a user via profile macro: "
        '<ac:structured-macro ac:name="profile" ac:schema-version="1">'
        '<ac:parameter ac:name="user">'
        '<ri:user ri:account-id="test-account-id-123" />'
        "</ac:parameter>"
        "</ac:structured-macro>. "
        "And another one: "
        '<ac:structured-macro ac:name="profile" ac:schema-version="1">'
        '<ac:parameter ac:name="user">'
        '<ri:user ri:userkey="test-userkey-456" />'
        "</ac:parameter>"
        "</ac:structured-macro>."
        "</p>"
    )

    class CustomMockConfluenceClient:
        def get_user_details_by_accountid(self, account_id):
            return (
                {"displayName": "Test User One"}
                if account_id == "test-account-id-123"
                else {}
            )

        def get_user_details_by_username(self, username):
            return (
                {"displayName": "Test User Two"}
                if username == "test-userkey-456"
                else {}
            )

    preprocessor = ConfluencePreprocessor(base_url="https://example.atlassian.net")
    processed_html, processed_markdown = preprocessor.process_html_content(
        html, confluence_client=CustomMockConfluenceClient()
    )
    assert "@Test User One" in processed_html
    assert "@Test User Two" in processed_html
    assert "@Test User One" in processed_markdown
    assert "@Test User Two" in processed_markdown


def test_markdown_to_confluence_no_automatic_anchors():
    """Test that heading_anchors=False prevents automatic anchor generation (regression for issue #488)."""
    from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor

    markdown_with_headings = """
# Main Title
Some content here.

## Subsection
More content.

### Deep Section
Final content.
"""

    preprocessor = ConfluencePreprocessor(base_url="https://example.atlassian.net")
    result = preprocessor.markdown_to_confluence_storage(markdown_with_headings)

    # Should not contain automatically generated anchor IDs
    assert 'id="main-title"' not in result.lower()
    assert 'id="subsection"' not in result.lower()
    assert 'id="deep-section"' not in result.lower()

    # Should still contain proper heading tags
    assert "<h1>Main Title</h1>" in result
    assert "<h2>Subsection</h2>" in result
    assert "<h3>Deep Section</h3>" in result


def test_markdown_to_confluence_style_preservation():
    """Test that styled content is preserved during conversion."""
    from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor

    markdown_with_styles = """
# Title with **bold** text

This paragraph has *italic* and **bold** text.

```python
def hello():
    return "world"
```

- Item with **bold**
- Item with *italic*

> Blockquote with **formatting**

[Link text](https://example.com) with description.
"""

    preprocessor = ConfluencePreprocessor(base_url="https://example.atlassian.net")
    result = preprocessor.markdown_to_confluence_storage(markdown_with_styles)

    # Check that formatting is preserved
    assert "<strong>bold</strong>" in result
    assert "<em>italic</em>" in result
    assert "<blockquote>" in result
    assert '<a href="https://example.com">Link text</a>' in result
    assert "ac:structured-macro" in result  # Code block macro
    assert 'ac:name="code"' in result
    assert "python" in result


def test_markdown_to_confluence_optional_anchor_generation():
    """Test that enable_heading_anchors parameter controls anchor generation."""
    from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor

    markdown_with_headings = """
# Main Title
Content here.

## Subsection
More content.
"""

    preprocessor = ConfluencePreprocessor(base_url="https://example.atlassian.net")

    # Test with anchors disabled (default)
    result_no_anchors = preprocessor.markdown_to_confluence_storage(
        markdown_with_headings
    )
    assert 'id="main-title"' not in result_no_anchors.lower()
    assert 'id="subsection"' not in result_no_anchors.lower()

    # Test with anchors enabled
    result_with_anchors = preprocessor.markdown_to_confluence_storage(
        markdown_with_headings, enable_heading_anchors=True
    )
    # When anchors are enabled, they should be present
    # Note: md2conf may use different anchor formats, so we check for presence of id attributes
    assert "<h1>" in result_with_anchors
    assert "<h2>" in result_with_anchors


# Issue #786 regression tests - Wiki Markup Corruption


def test_markdown_to_jira_header_requires_space(preprocessor_with_jira):
    """Test that # requires space to be converted to heading (issue #786)."""
    # With space - Markdown heading, should convert
    assert preprocessor_with_jira.markdown_to_jira("# Heading") == "h1. Heading"
    assert preprocessor_with_jira.markdown_to_jira("## Subheading") == "h2. Subheading"
    assert preprocessor_with_jira.markdown_to_jira("### Level 3") == "h3. Level 3"

    # Without space - could be Jira numbered list, should NOT convert
    assert preprocessor_with_jira.markdown_to_jira("#item") == "#item"
    assert preprocessor_with_jira.markdown_to_jira("##nested") == "##nested"
    assert preprocessor_with_jira.markdown_to_jira("###deep") == "###deep"


def test_markdown_to_jira_preserves_jira_list_syntax(preprocessor_with_jira):
    """Test that Jira list syntax (asterisks + space) is preserved (issue #786)."""
    # Jira nested bullets - should NOT be converted to bold
    jira_list = "* First level\n** Second level\n*** Third level"
    result = preprocessor_with_jira.markdown_to_jira(jira_list)
    assert "** Second level" in result  # Preserved, not converted
    assert "*** Third level" in result  # Preserved, not converted

    # Single Jira bullet should also be preserved
    assert preprocessor_with_jira.markdown_to_jira("* Item") == "* Item"


def test_markdown_to_jira_inline_bold_still_converts(preprocessor_with_jira):
    """Test that inline Markdown bold/italic still converts (issue #786)."""
    # Inline bold should still work
    assert (
        preprocessor_with_jira.markdown_to_jira("text **bold** text")
        == "text *bold* text"
    )
    assert (
        preprocessor_with_jira.markdown_to_jira("text *italic* text")
        == "text _italic_ text"
    )


def test_markdown_to_jira_bold_without_space_still_converts(preprocessor_with_jira):
    """Test that Markdown bold (no space after **) still converts (issue #786)."""
    # These should still be converted (existing behavior preserved)
    assert preprocessor_with_jira.markdown_to_jira("**bold text**") == "*bold text*"
    assert preprocessor_with_jira.markdown_to_jira("*italic text*") == "_italic text_"


def test_md2conf_elements_from_string_available():
    """Test that elements_from_string is importable with fallback (issue #817)."""
    from mcp_atlassian.preprocessing.confluence import elements_from_string

    assert callable(elements_from_string)


# Issue #893 regression tests - Code Block Content Corruption


def test_markdown_to_jira_code_block_preserves_hash(preprocessor_with_jira):
    """Test that # characters inside code blocks are preserved (issue #893)."""
    markdown = """Here's a script:

```
#!/bin/bash

# This is a comment
echo "hello"
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)

    # The shebang and comment should be preserved, not converted to headings
    assert "#!/bin/bash" in result
    assert "# This is a comment" in result
    assert "h1." not in result  # Should NOT have heading conversion


def test_markdown_to_jira_code_block_with_language_preserves_hash(
    preprocessor_with_jira,
):
    """Test that # in code blocks with language specifier is preserved (issue #893)."""
    markdown = """```python
# Python comment
def hello():
    print("world")
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)

    assert "# Python comment" in result
    assert "h1." not in result


def test_markdown_to_jira_code_block_multiple_hash_lines(preprocessor_with_jira):
    """Test multiple # lines in code block are all preserved (issue #893)."""
    markdown = """```bash
# First comment
# Second comment
# Third comment
echo "test"
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)

    assert "# First comment" in result
    assert "# Second comment" in result
    assert "# Third comment" in result
    assert result.count("h1.") == 0


def test_markdown_to_jira_inline_code_preserves_hash(preprocessor_with_jira):
    """Test that # in inline code is preserved (issue #893)."""
    markdown = "The shebang line is `#!/bin/bash` in shell scripts."
    result = preprocessor_with_jira.markdown_to_jira(markdown)

    assert "#!/bin/bash" in result
    assert "h1." not in result


def test_markdown_to_jira_mixed_code_and_headers(preprocessor_with_jira):
    """Test that headers outside code blocks still convert while code is preserved."""
    markdown = """# Real Heading

Here's some code:

```
# This is a comment, not a heading
```

## Another Heading"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)

    # Headers should convert
    assert "h1. Real Heading" in result
    assert "h2. Another Heading" in result

    # Code block content should be preserved
    assert "# This is a comment" in result


# Language mapping tests for code blocks (issue #669)


def test_normalize_code_language_valid_jira_languages(preprocessor_with_jira):
    """Test that valid JIRA languages pass through unchanged."""
    # Official JIRA-supported languages should be returned as-is (lowercase)
    # Source: https://jira.atlassian.com/browse/JRASERVER-21067
    assert preprocessor_with_jira._normalize_code_language("python") == "python"
    assert preprocessor_with_jira._normalize_code_language("java") == "java"
    assert preprocessor_with_jira._normalize_code_language("javascript") == "javascript"
    assert preprocessor_with_jira._normalize_code_language("bash") == "bash"
    assert preprocessor_with_jira._normalize_code_language("sql") == "sql"
    assert preprocessor_with_jira._normalize_code_language("xml") == "xml"
    assert preprocessor_with_jira._normalize_code_language("json") == "json"
    assert preprocessor_with_jira._normalize_code_language("go") == "go"
    assert preprocessor_with_jira._normalize_code_language("ruby") == "ruby"
    assert preprocessor_with_jira._normalize_code_language("none") == "none"


def test_normalize_code_language_case_insensitive(preprocessor_with_jira):
    """Test that language normalization is case-insensitive."""
    assert preprocessor_with_jira._normalize_code_language("Python") == "python"
    assert preprocessor_with_jira._normalize_code_language("JAVA") == "java"
    assert preprocessor_with_jira._normalize_code_language("JavaScript") == "javascript"
    assert preprocessor_with_jira._normalize_code_language("BASH") == "bash"


def test_normalize_code_language_mapped_languages(preprocessor_with_jira):
    """Test that unsupported languages map to their closest JIRA equivalent."""
    # Dockerfile → bash (similar syntax)
    assert preprocessor_with_jira._normalize_code_language("dockerfile") == "bash"
    assert preprocessor_with_jira._normalize_code_language("docker") == "bash"

    # TypeScript/JSX → javascript
    assert preprocessor_with_jira._normalize_code_language("typescript") == "javascript"
    assert preprocessor_with_jira._normalize_code_language("ts") == "javascript"
    assert preprocessor_with_jira._normalize_code_language("tsx") == "javascript"
    assert preprocessor_with_jira._normalize_code_language("jsx") == "javascript"

    # Kotlin → java (JVM-based)
    assert preprocessor_with_jira._normalize_code_language("kotlin") == "java"
    assert preprocessor_with_jira._normalize_code_language("kt") == "java"

    # Build files → bash
    assert preprocessor_with_jira._normalize_code_language("makefile") == "bash"
    assert preprocessor_with_jira._normalize_code_language("make") == "bash"


def test_normalize_code_language_unmapped_returns_none(preprocessor_with_jira):
    """Test that unmapped languages return None for plain {code} blocks."""
    # Languages with no good JIRA alternative should return None
    assert preprocessor_with_jira._normalize_code_language("rust") is None
    assert preprocessor_with_jira._normalize_code_language("toml") is None
    assert preprocessor_with_jira._normalize_code_language("markdown") is None
    assert preprocessor_with_jira._normalize_code_language("unknownlang") is None
    assert preprocessor_with_jira._normalize_code_language("zig") is None


def test_normalize_code_language_empty_input(preprocessor_with_jira):
    """Test that empty/None language returns None."""
    assert preprocessor_with_jira._normalize_code_language("") is None
    assert preprocessor_with_jira._normalize_code_language(None) is None


def test_markdown_to_jira_code_block_valid_language(preprocessor_with_jira):
    """Test code block conversion with valid JIRA language."""
    markdown = """```python
def hello():
    print("Hello World")
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert "{code:python}" in result
    assert "def hello():" in result
    assert "{code}" in result


def test_markdown_to_jira_code_block_dockerfile_maps_to_bash(preprocessor_with_jira):
    """Test that dockerfile code blocks map to bash (issue #669)."""
    markdown = """```dockerfile
FROM ubuntu:22.04
RUN apt-get update
CMD ["/bin/bash"]
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert "{code:bash}" in result
    assert "FROM ubuntu:22.04" in result
    assert "{code}" in result


def test_markdown_to_jira_code_block_typescript_maps_to_javascript(
    preprocessor_with_jira,
):
    """Test that typescript code blocks map to javascript."""
    markdown = """```typescript
interface User {
    name: string;
    age: number;
}
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert "{code:javascript}" in result
    assert "interface User" in result


def test_markdown_to_jira_code_block_jsx_maps_to_javascript(preprocessor_with_jira):
    """Test that jsx code blocks map to javascript (issue #669)."""
    markdown = """```jsx
const Component = () => {
  return <div>Hello</div>;
}
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert "{code:javascript}" in result
    assert "const Component" in result


def test_markdown_to_jira_code_block_unmapped_language_plain(preprocessor_with_jira):
    """Test that unmapped languages produce plain {code} blocks."""
    markdown = """```rust
fn main() {
    println!("Hello, world!");
}
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    # Should produce {code} without language specifier
    assert "{code}" in result
    assert "{code:rust}" not in result
    assert "fn main()" in result


def test_markdown_to_jira_code_block_no_language_plain(preprocessor_with_jira):
    """Test that code blocks without language produce plain {code}."""
    markdown = """```
plain text code
no syntax highlighting
```"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert "{code}" in result
    # Should not have any language specifier
    assert "{code:" not in result
    assert "plain text code" in result


def test_markdown_to_jira_multiple_code_blocks_mixed_languages(preprocessor_with_jira):
    """Test multiple code blocks with different language mappings."""
    markdown = """
Python code:
```python
print("hello")
```

Dockerfile:
```dockerfile
FROM alpine
```

Unknown language:
```unknownlang
some code
```
"""
    result = preprocessor_with_jira.markdown_to_jira(markdown)
    assert "{code:python}" in result
    assert "{code:bash}" in result  # dockerfile mapped to bash
    assert 'print("hello")' in result
    assert "FROM alpine" in result
    assert "some code" in result


# Confluence ac:image tag processing tests


class TestImageProcessing:
    """Tests for Confluence ac:image tag processing."""

    @pytest.fixture
    def preprocessor(self):
        return ConfluencePreprocessor(base_url="https://example.net")

    @pytest.mark.parametrize(
        "test_id, html, content_id, attachments, expected",
        [
            pytest.param(
                "ri-attachment-basic",
                '<ac:image><ri:attachment ri:filename="shot.png"/></ac:image>',
                "123",
                None,
                "![shot.png](https://example.net/download/attachments/123/shot.png)",
                id="ri-attachment-basic",
            ),
            pytest.param(
                "ri-url-basic",
                '<ac:image><ri:url ri:value="https://cdn/logo.png"/></ac:image>',
                "",
                None,
                "![logo.png](https://cdn/logo.png)",
                id="ri-url-basic",
            ),
            pytest.param(
                "width-attr",
                '<ac:image ac:width="600"><ri:attachment ri:filename="d.png"/></ac:image>',
                "123",
                None,
                "![d.png]",
                id="width-attr",
            ),
            pytest.param(
                "mixed-content",
                '<p>Text</p><ac:image><ri:attachment ri:filename="x.png"/></ac:image><p>More</p>',
                "123",
                None,
                "x.png",
                id="mixed-content",
            ),
            pytest.param(
                "no-content-id",
                '<ac:image><ri:attachment ri:filename="test.png"/></ac:image>',
                "",
                None,
                "![test.png](test.png)",
                id="no-content-id",
            ),
            pytest.param(
                "attachment-lookup",
                '<ac:image><ri:attachment ri:filename="doc.png"/></ac:image>',
                "123",
                [
                    {
                        "title": "doc.png",
                        "_links": {"download": "/download/attachments/123/doc.png"},
                    }
                ],
                "![doc.png](https://example.net/download/attachments/123/doc.png)",
                id="attachment-lookup",
            ),
            pytest.param(
                "filename-spaces",
                '<ac:image><ri:attachment ri:filename="Screen Shot 2024.png"/></ac:image>',
                "123",
                None,
                "Screen%20Shot%202024.png",
                id="filename-spaces",
            ),
            pytest.param(
                "unknown-inner",
                "<ac:image><ri:unknown/></ac:image>",
                "123",
                None,
                "[unsupported image]",
                id="unknown-inner",
            ),
            pytest.param(
                "no-image-tags",
                "<p>Normal content</p>",
                "123",
                None,
                "Normal content",
                id="no-image-tags",
            ),
        ],
    )
    def test_image_processing(
        self,
        preprocessor,
        test_id: str,
        html: str,
        content_id: str,
        attachments: list[dict] | None,
        expected: str,
    ):
        """Test ac:image tag processing with various inputs."""
        _, markdown = preprocessor.process_html_content(
            html,
            content_id=content_id,
            attachments=attachments,
        )
        assert expected in markdown

    def test_width_attr_in_img(self, preprocessor):
        """Verify width attribute is preserved in the img tag."""
        html = (
            '<ac:image ac:width="600"><ri:attachment ri:filename="d.png"/></ac:image>'
        )
        processed_html, _ = preprocessor.process_html_content(html, content_id="123")
        assert 'width="600"' in processed_html

    def test_mixed_content_has_all_parts(self, preprocessor):
        """Verify mixed content retains both text and image."""
        html = '<p>Text</p><ac:image><ri:attachment ri:filename="x.png"/></ac:image><p>More</p>'
        _, markdown = preprocessor.process_html_content(html, content_id="123")
        assert "Text" in markdown
        assert "x.png" in markdown
        assert "More" in markdown

    def test_attachment_lookup_uses_download_url(self, preprocessor):
        """Verify attachment lookup prefers _links.download over fallback."""
        attachments = [
            {
                "title": "doc.png",
                "_links": {"download": "/download/attachments/123/doc.png"},
            }
        ]
        html = '<ac:image><ri:attachment ri:filename="doc.png"/></ac:image>'
        _, markdown = preprocessor.process_html_content(
            html, content_id="123", attachments=attachments
        )
        # Should use the download link, not the fallback construction
        assert "/download/attachments/123/doc.png" in markdown

    def test_cross_page_attachment_uses_filename_fallback(self, preprocessor):
        """Cross-page ri:attachment should not use current page's content_id."""
        html = (
            "<ac:image>"
            '<ri:attachment ri:filename="img.png">'
            '<ri:page ri:content-title="Other Page" ri:space-key="X"/>'
            "</ri:attachment>"
            "</ac:image>"
        )
        _, markdown = preprocessor.process_html_content(html, content_id="999")
        # Should NOT contain /999/ (wrong page ID); should fall back to
        # filename-only reference since we can't resolve the other page
        assert "/999/" not in markdown
        assert "![img.png](img.png)" in markdown

    def test_backward_compatibility(self, preprocessor):
        """Ensure existing calls without new params still work."""
        html = "<p>Simple text</p>"
        processed_html, processed_markdown = preprocessor.process_html_content(html)
        assert "Simple text" in processed_markdown


# Issue #1052 - {panel} blocks drop links during wiki-to-markdown conversion


class TestPanelBlocks:
    """Tests for {panel} block conversion and bare link handling."""

    @pytest.fixture
    def preprocessor(self):
        return JiraPreprocessor(base_url="https://example.atlassian.net")

    @pytest.mark.parametrize(
        "test_id, input_text, expected_present, expected_absent",
        [
            pytest.param(
                "panel-bare-url",
                "{panel:title=Spec}[https://example.com]{panel}",
                ["**Spec**", "https://example.com"],
                ["{panel"],
                id="panel-bare-url",
            ),
            pytest.param(
                "panel-named-link",
                "{panel:title=Spec}[Link Text|https://example.com]{panel}",
                ["**Spec**", "[Link Text](https://example.com)"],
                ["{panel"],
                id="panel-named-link",
            ),
            pytest.param(
                "panel-no-title",
                "{panel}some content{panel}",
                ["some content"],
                ["{panel"],
                id="panel-no-title",
            ),
            pytest.param(
                "panel-extra-params",
                "{panel:borderColor=#ccc|title=Info}text{panel}",
                ["**Info**", "text"],
                ["{panel"],
                id="panel-extra-params",
            ),
            pytest.param(
                "panel-multiline",
                "{panel:title=Notes}line one\nline two{panel}",
                ["line one", "line two"],
                ["{panel"],
                id="panel-multiline",
            ),
            pytest.param(
                "multiple-panels",
                "{panel:title=A}content A{panel}\n{panel:title=B}content B{panel}",
                ["**A**", "content A", "**B**", "content B"],
                ["{panel"],
                id="multiple-panels",
            ),
        ],
    )
    def test_panel_conversion(
        self,
        preprocessor,
        test_id: str,
        input_text: str,
        expected_present: list[str],
        expected_absent: list[str],
    ):
        """Test {panel} block conversion to markdown."""
        result = preprocessor.jira_to_markdown(input_text)
        for expected in expected_present:
            assert expected in result, f"[{test_id}] Expected '{expected}' in: {result}"
        for absent in expected_absent:
            assert absent not in result, (
                f"[{test_id}] Unexpected '{absent}' in: {result}"
            )

    def test_panel_full_pipeline(self, preprocessor):
        """Test panel with URL link through the full clean_jira_text pipeline (the reported bug)."""
        input_text = "{panel:title=Spec}[https://example.com]{panel}"
        result = preprocessor.clean_jira_text(input_text)
        assert "https://example.com" in result, f"URL dropped in pipeline: {result}"

    def test_bare_link_without_panel(self, preprocessor):
        """Test bare [url] link is preserved outside panels too."""
        result = preprocessor.jira_to_markdown("[https://example.com] more text")
        assert "https://example.com" in result, f"URL dropped: {result}"


# Code block placeholder protection tests


class TestCodeBlockProtection:
    """Tests for code block content protection via placeholder extraction."""

    @pytest.fixture
    def preprocessor(self):
        return JiraPreprocessor(base_url="https://example.atlassian.net")

    @pytest.mark.parametrize(
        "test_id, input_text, expected_in_fence, description",
        [
            pytest.param(
                "quote-in-code",
                "{code}{quote}quoted{quote}{code}",
                "{quote}quoted{quote}",
                "Quote not converted inside code",
                id="quote-in-code",
            ),
            pytest.param(
                "color-in-code",
                "{code}{color:red}text{color}{code}",
                "{color:red}text{color}",
                "Color not converted inside code",
                id="color-in-code",
            ),
            pytest.param(
                "panel-in-code",
                "{code}{panel:title=X}content{panel}{code}",
                "{panel:title=X}content{panel}",
                "Panel not converted inside code",
                id="panel-in-code",
            ),
            pytest.param(
                "noformat-with-quote",
                "{noformat}{quote}q{quote}{noformat}",
                "{quote}q{quote}",
                "Quote not converted inside noformat",
                id="noformat-with-quote",
            ),
            pytest.param(
                "code-with-lang",
                "{code:python}{quote}q{quote}{code}",
                "{quote}q{quote}",
                "Language preserved, content literal",
                id="code-with-lang",
            ),
            pytest.param(
                "mixed-outside-inside",
                "{quote}real quote{quote}\n{code}{quote}not a quote{quote}{code}",
                "{quote}not a quote{quote}",
                "Outside converted, inside preserved",
                id="mixed-outside-inside",
            ),
        ],
    )
    def test_jira_to_markdown_code_block_preserves_content(
        self,
        preprocessor,
        test_id: str,
        input_text: str,
        expected_in_fence: str,
        description: str,
    ):
        """Test that markup inside {code}/{noformat} is not converted."""
        result = preprocessor.jira_to_markdown(input_text)
        assert "```" in result, f"[{test_id}] No code fence in: {result}"
        fence_pattern = r"```(?:\w*)\n([\s\S]*?)\n```"
        fence_match = re.search(fence_pattern, result)
        assert fence_match, (
            f"[{test_id}] Could not extract fence content from: {result}"
        )
        fence_content = fence_match.group(1)
        assert expected_in_fence in fence_content, (
            f"[{test_id}] Expected '{expected_in_fence}' "
            f"inside fence, got: '{fence_content}'"
        )

    def test_inline_code_inside_code_block_preserved(self, preprocessor):
        """Test that {{inline}} inside {code} blocks is preserved."""
        input_text = "{code}use {{var}} here{code}"
        result = preprocessor.jira_to_markdown(input_text)
        assert "```" in result
        # The {{var}} should appear as literal text, not
        # converted to backtick inline code
        fence_match = re.search(r"```\n([\s\S]*?)\n```", result)
        assert fence_match
        assert "{{var}}" in fence_match.group(1)

    def test_round_trip_preserves_code_block(self, preprocessor):
        """Test jira->md->jira round-trip preserves code content."""
        jira_input = "{code:python}# comment\nprint('hi'){code}"
        md = preprocessor.jira_to_markdown(jira_input)
        assert "```python" in md
        assert "# comment" in md
        jira_output = preprocessor.markdown_to_jira(md)
        assert "{code:python}" in jira_output
        assert "# comment" in jira_output
        assert "print('hi')" in jira_output
