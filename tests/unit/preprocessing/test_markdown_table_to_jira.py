"""Regression tests for Issue #1343 — Markdown pipe table conversion."""

import pytest

from mcp_atlassian.preprocessing.jira import JiraPreprocessor


@pytest.fixture
def preprocessor():
    return JiraPreprocessor()


def test_markdown_table_with_spaces(preprocessor):
    """Markdown tables with padded cells must be stripped when converted to Jira."""
    markdown = """| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |"""

    jira = preprocessor.markdown_to_jira(markdown)

    lines = jira.strip().split("\n")
    assert lines[0] == "||Header 1||Header 2||Header 3||"
    assert lines[1] == "|Cell 1|Cell 2|Cell 3|"
    assert lines[2] == "|Cell 4|Cell 5|Cell 6|"


def test_markdown_table_no_spaces(preprocessor):
    """Markdown tables without padding should still convert correctly."""
    markdown = """|H1|H2|
|--|--|
|A|B|
|C|D|"""

    jira = preprocessor.markdown_to_jira(markdown)

    lines = jira.strip().split("\n")
    assert lines[0] == "||H1||H2||"
    assert lines[1] == "|A|B|"
    assert lines[2] == "|C|D|"


def test_markdown_table_with_alignment(preprocessor):
    """Markdown tables with alignment separators ( :---: ) should work."""
    markdown = """| Left | Center | Right |
|:-----|:------:|------:|
| L    |   C    |     R |"""

    jira = preprocessor.markdown_to_jira(markdown)

    lines = jira.strip().split("\n")
    assert lines[0] == "||Left||Center||Right||"
    assert lines[1] == "|L|C|R|"


def test_markdown_table_single_column(preprocessor):
    """Single-column markdown tables should convert correctly."""
    markdown = """| Name |
|------|
| Alice |
| Bob   |"""

    jira = preprocessor.markdown_to_jira(markdown)

    lines = jira.strip().split("\n")
    assert lines[0] == "||Name||"
    assert lines[1] == "|Alice|"
    assert lines[2] == "|Bob|"


def test_non_table_pipes_unchanged(preprocessor):
    """Lines that look like tables but lack a separator should be left alone."""
    markdown = "This | is | not | a | table"

    jira = preprocessor.markdown_to_jira(markdown)

    assert jira.strip() == "This | is | not | a | table"


def test_table_with_inline_formatting(preprocessor):
    """Inline markdown formatting inside table cells should be preserved."""
    markdown = """| Name | Status |
|------|--------|
| **Bold** | _italic_ |"""

    jira = preprocessor.markdown_to_jira(markdown)

    lines = jira.strip().split("\n")
    assert lines[0] == "||Name||Status||"
    assert "*Bold*" in lines[1]
    assert "_italic_" in lines[1]
