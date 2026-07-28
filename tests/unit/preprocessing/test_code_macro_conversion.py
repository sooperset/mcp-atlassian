"""Tests for Confluence code-macro to fenced-Markdown conversion."""

from bs4 import BeautifulSoup

from mcp_atlassian.preprocessing.base import BasePreprocessor

# Mirrors the storage format Confluence Server returns for a code macro,
# including the CDATA body with box-drawing characters and indentation.
CODE_MACRO = (
    "<p>Before</p>"
    '<ac:structured-macro ac:name="code" ac:schema-version="1" ac:macro-id="x">'
    '<ac:parameter ac:name="language">text</ac:parameter>'
    '<ac:parameter ac:name="linenumbers">true</ac:parameter>'
    "<ac:plain-text-body><![CDATA[root (1m 11s)\n"
    "  ├── child A (167ms)\n"
    "  │     └── grandchild (22ms)\n"
    "  └── child B (501ms)]]></ac:plain-text-body>"
    "</ac:structured-macro>"
    "<p>After</p>"
)


def test_code_macro_becomes_fenced_block():
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    html, markdown = preprocessor.process_html_content(CODE_MACRO)

    # The HTML output keeps the original storage-format macro (raw mode
    # consumers rely on it); only the markdown path converts it
    assert 'ac:name="code"' in html
    assert "ac:plain-text-body" in html

    # Parameter values must not leak into the output as literal text
    assert "texttrue" not in markdown
    # The body arrives fenced, with the language tag carried over
    assert "```text" in markdown
    # Indentation inside the body survives
    assert "  │     └── grandchild (22ms)" in markdown
    # Surrounding prose is intact
    assert "Before" in markdown
    assert "After" in markdown


def test_code_macro_uses_longer_fence_for_embedded_backticks():
    code_body = "first line\n```\nlast line"
    macro = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">text</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code_body}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(macro)

    expected_block = f"````text\n{code_body}\n````"
    assert markdown == expected_block
    assert markdown.count("````text") == 1


def test_code_macro_preserves_boundary_newlines():
    code_body = "\n\nfirst line\nlast line\n\n"
    macro = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">text</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code_body}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(macro)

    expected_block = f"```text\n{code_body}```"
    assert markdown == expected_block


def test_code_macro_nested_in_list_keeps_list_structure():
    code_body = "first line\n  indented line\nlast line"
    macro = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code_body}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(f"<ul><li>{macro}</li></ul>")

    # Every line after the marker is indented to the list item's content
    # column, so the whole fence stays inside the item
    assert markdown == (
        "* ```python\n  first line\n    indented line\n  last line\n  ```"
    )


def test_code_macro_nested_in_blockquote_keeps_quote_prefix():
    code_body = "first line\n```\nlast line"
    macro = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">text</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code_body}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(f"<blockquote>{macro}</blockquote>")

    # The quote marker repeats on every line (a bare line would end the
    # blockquote), and the embedded backticks still lengthen the fence
    assert markdown == ("> ````text\n> first line\n> ```\n> last line\n> ````")


def test_code_macro_without_language_still_fenced():
    macro = (
        '<ac:structured-macro ac:name="noformat">'
        "<ac:plain-text-body><![CDATA[plain  spaced   body]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(macro)

    assert "```" in markdown
    assert "plain  spaced   body" in markdown


def test_code_macro_without_body_is_left_untouched():
    soup = BeautifulSoup(
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">text</ac:parameter>'
        '<ac:parameter ac:name="linenumbers">true</ac:parameter>'
        "</ac:structured-macro>",
        "html.parser",
    )

    BasePreprocessor._process_code_macros_in_soup(soup)

    assert soup.find("ac:structured-macro") is not None
    assert soup.find("pre") is None


def test_empty_body_code_macro_does_not_leak_parameters():
    macro = (
        "<p>Before</p>"
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        '<ac:parameter ac:name="linenumbers">true</ac:parameter>'
        "<ac:plain-text-body><![CDATA[]]></ac:plain-text-body>"
        "</ac:structured-macro>"
        "<p>After</p>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(macro)

    # The macro converts to an empty fenced block; the parameter values must
    # not appear as literal text outside the fence tag
    assert "```python" in markdown
    assert "true" not in markdown
    assert "pythontrue" not in markdown
    assert "Before" in markdown
    assert "After" in markdown


def test_whitespace_only_body_converts_without_parameter_leak():
    macro = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        '<ac:parameter ac:name="linenumbers">true</ac:parameter>'
        "<ac:plain-text-body><![CDATA[   ]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(macro)

    assert "```python" in markdown
    assert "true" not in markdown


def test_non_code_macros_unaffected():
    html = "<p>No macros here, just <code>inline</code>.</p>"
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(html)

    assert "inline" in markdown
    assert "```" not in markdown


def test_multiple_code_macros_in_one_page():
    page = CODE_MACRO + CODE_MACRO
    preprocessor = BasePreprocessor(base_url="https://confluence.example.com")
    _, markdown = preprocessor.process_html_content(page)

    assert markdown.count("```text") == 2
    assert "texttrue" not in markdown
