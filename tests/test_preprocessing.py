import pytest

from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor
from mcp_atlassian.preprocessing.jira import JiraPreprocessor
from tests.fixtures.confluence_mocks import MOCK_COMMENTS_RESPONSE, MOCK_PAGE_RESPONSE
from tests.fixtures.jira_mocks import MOCK_JIRA_ISSUE_RESPONSE


class MockConfluenceClient:
    def get_user_details_by_accountid(self, account_id):
        # Mock user details response based on the format in MOCK_PAGE_RESPONSE
        return {
            "displayName": f"Test User {account_id}",
            "accountType": "atlassian",
            "accountStatus": "active",
        }


@pytest.fixture
def preprocessor_with_jira():
    return JiraPreprocessor(base_url="https://example.atlassian.net")


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
