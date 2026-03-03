"""
Tests for the ADF (Atlassian Document Format) parser.

These tests validate the conversion of ADF content to plain text,
including handling of various inline and block node types,
and the reverse conversion from Markdown to ADF.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.mcp_atlassian.models.jira.adf import adf_to_text, markdown_to_adf


class TestAdfToText:
    """Tests for the adf_to_text function."""

    # Basic input handling

    def test_none_input(self):
        """Test that None input returns None."""
        assert adf_to_text(None) is None

    def test_string_input(self):
        """Test that string input is returned as-is."""
        assert adf_to_text("plain text") == "plain text"

    def test_empty_dict(self):
        """Test that empty dict returns None."""
        assert adf_to_text({}) is None

    def test_empty_list(self):
        """Test that empty list returns None."""
        assert adf_to_text([]) is None

    # Text node tests

    def test_text_node(self):
        """Test basic text node extraction."""
        node = {"type": "text", "text": "Hello, World!"}
        assert adf_to_text(node) == "Hello, World!"

    def test_text_node_empty(self):
        """Test text node with empty text."""
        node = {"type": "text", "text": ""}
        assert adf_to_text(node) == ""

    def test_text_node_missing_text(self):
        """Test text node without text field."""
        node = {"type": "text"}
        assert adf_to_text(node) == ""

    # hardBreak node tests

    def test_hard_break_node(self):
        """Test hardBreak node returns newline."""
        node = {"type": "hardBreak"}
        assert adf_to_text(node) == "\n"

    # Mention node tests

    def test_mention_with_text(self):
        """Test mention node with text attribute."""
        node = {
            "type": "mention",
            "attrs": {"id": "user123", "text": "@John Doe", "userType": "DEFAULT"},
        }
        assert adf_to_text(node) == "@John Doe"

    def test_mention_without_text(self):
        """Test mention node falls back to id."""
        node = {"type": "mention", "attrs": {"id": "user123"}}
        assert adf_to_text(node) == "@user123"

    def test_mention_without_attrs(self):
        """Test mention node with missing attrs."""
        node = {"type": "mention"}
        assert adf_to_text(node) == "@unknown"

    # Emoji node tests

    def test_emoji_with_text(self):
        """Test emoji node with unicode text."""
        node = {
            "type": "emoji",
            "attrs": {"shortName": ":smile:", "text": "😄"},
        }
        assert adf_to_text(node) == "😄"

    def test_emoji_without_text(self):
        """Test emoji node falls back to shortName."""
        node = {"type": "emoji", "attrs": {"shortName": ":custom_emoji:"}}
        assert adf_to_text(node) == ":custom_emoji:"

    def test_emoji_without_attrs(self):
        """Test emoji node with missing attrs."""
        node = {"type": "emoji"}
        assert adf_to_text(node) == ""

    # Date node tests

    def test_date_node(self):
        """Test date node formats timestamp correctly."""
        # 1582152559000 = 2020-02-19 21:49:19 UTC
        node = {"type": "date", "attrs": {"timestamp": "1582152559000"}}
        assert adf_to_text(node) == "2020-02-19"

    def test_date_node_integer_timestamp(self):
        """Test date node with integer timestamp."""
        node = {"type": "date", "attrs": {"timestamp": 1582152559000}}
        assert adf_to_text(node) == "2020-02-19"

    def test_date_node_invalid_timestamp(self):
        """Test date node with invalid timestamp returns raw value."""
        node = {"type": "date", "attrs": {"timestamp": "not-a-number"}}
        assert adf_to_text(node) == "not-a-number"

    def test_date_node_missing_timestamp(self):
        """Test date node without timestamp."""
        node = {"type": "date", "attrs": {}}
        assert adf_to_text(node) == ""

    def test_date_node_without_attrs(self):
        """Test date node with missing attrs."""
        node = {"type": "date"}
        assert adf_to_text(node) == ""

    def test_date_node_overflow_timestamp(self):
        """Regression test for #1033: overflow timestamps must not crash.

        On Windows, datetime.fromtimestamp raises OverflowError for sentinel
        timestamps (year 9999). adf_to_text should fall back to the raw string.
        """
        node = {"type": "date", "attrs": {"timestamp": "253402300799000"}}
        mock_dt = MagicMock()
        mock_dt.fromtimestamp.side_effect = OverflowError(
            "timestamp too large to convert to C _PyTime_t"
        )
        with patch("src.mcp_atlassian.models.jira.adf.datetime", mock_dt):
            result = adf_to_text(node)
            assert result == "253402300799000"

    # Status node tests

    def test_status_node(self):
        """Test status node wraps text in brackets."""
        node = {
            "type": "status",
            "attrs": {"text": "In Progress", "color": "yellow"},
        }
        assert adf_to_text(node) == "[In Progress]"

    def test_status_node_empty_text(self):
        """Test status node with empty text."""
        node = {"type": "status", "attrs": {"text": "", "color": "neutral"}}
        assert adf_to_text(node) == "[]"

    def test_status_node_without_attrs(self):
        """Test status node with missing attrs."""
        node = {"type": "status"}
        assert adf_to_text(node) == "[]"

    # inlineCard node tests

    def test_inline_card_with_url(self):
        """Test inlineCard node extracts URL."""
        node = {"type": "inlineCard", "attrs": {"url": "https://example.com"}}
        assert adf_to_text(node) == "https://example.com"

    def test_inline_card_with_data_url(self):
        """Test inlineCard node extracts URL from data."""
        node = {
            "type": "inlineCard",
            "attrs": {"data": {"url": "https://jira.example.com/issue/PROJ-123"}},
        }
        assert adf_to_text(node) == "https://jira.example.com/issue/PROJ-123"

    def test_inline_card_with_data_name(self):
        """Test inlineCard node falls back to name from data."""
        node = {
            "type": "inlineCard",
            "attrs": {"data": {"name": "PROJ-123: Fix bug"}},
        }
        assert adf_to_text(node) == "PROJ-123: Fix bug"

    def test_inline_card_empty(self):
        """Test inlineCard node with no data."""
        node = {"type": "inlineCard", "attrs": {}}
        assert adf_to_text(node) == ""

    def test_inline_card_without_attrs(self):
        """Test inlineCard node with missing attrs."""
        node = {"type": "inlineCard"}
        assert adf_to_text(node) == ""

    # codeBlock node tests

    def test_code_block(self):
        """Test codeBlock node wraps content in backticks."""
        node = {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [{"type": "text", "text": "print('hello')"}],
        }
        assert adf_to_text(node) == "```\nprint('hello')\n```"

    def test_code_block_multiline(self):
        """Test codeBlock node with multiline content."""
        node = {
            "type": "codeBlock",
            "content": [{"type": "text", "text": "line1\nline2\nline3"}],
        }
        assert adf_to_text(node) == "```\nline1\nline2\nline3\n```"

    def test_code_block_empty(self):
        """Test codeBlock node with no content."""
        node = {"type": "codeBlock", "content": []}
        assert adf_to_text(node) == "```\n\n```"

    def test_code_block_without_content(self):
        """Test codeBlock node without content field."""
        node = {"type": "codeBlock"}
        assert adf_to_text(node) == "```\n\n```"

    # Nested content tests

    def test_paragraph_with_text(self):
        """Test paragraph node with nested text."""
        node = {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Hello, World!"}],
        }
        assert adf_to_text(node) == "Hello, World!"

    def test_document_with_paragraphs(self):
        """Test full document structure."""
        doc = {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
            ],
        }
        assert adf_to_text(doc) == "First\nSecond"

    def test_paragraph_with_mixed_content(self):
        """Test paragraph with text, mention, and emoji."""
        node = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "mention", "attrs": {"id": "123", "text": "@John"}},
                {"type": "text", "text": " "},
                {"type": "emoji", "attrs": {"shortName": ":wave:", "text": "👋"}},
            ],
        }
        assert adf_to_text(node) == "Hello \n@John\n \n👋"

    def test_list_of_text_nodes(self):
        """Test list of text nodes joins with newlines."""
        nodes = [
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"},
        ]
        assert adf_to_text(nodes) == "Line 1\nLine 2"

    # Edge cases

    def test_unknown_node_type(self):
        """Test unknown node type without content returns None."""
        node = {"type": "unknownNode"}
        assert adf_to_text(node) is None

    def test_unknown_node_with_content(self):
        """Test unknown node type with content processes recursively."""
        node = {
            "type": "unknownNode",
            "content": [{"type": "text", "text": "nested text"}],
        }
        assert adf_to_text(node) == "nested text"

    def test_deeply_nested_content(self):
        """Test deeply nested ADF structure."""
        node = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 1"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        assert adf_to_text(node) == "Item 1"


class TestMarkdownToAdf:
    """Tests for the markdown_to_adf function."""

    def _assert_valid_adf(self, result: dict) -> None:
        """Helper: assert the result is a valid ADF document."""
        assert result["version"] == 1
        assert result["type"] == "doc"
        assert isinstance(result["content"], list)

    # -- Structure -----------------------------------------------------------

    def test_structure(self):
        """Any input always produces version:1, type:doc, content:[...]."""
        result = markdown_to_adf("anything")
        self._assert_valid_adf(result)

    # -- Empty / whitespace -------------------------------------------------

    def test_empty_string(self):
        """Empty string produces a minimal ADF doc with an empty paragraph."""
        result = markdown_to_adf("")
        self._assert_valid_adf(result)
        assert len(result["content"]) >= 1
        assert result["content"][0]["type"] == "paragraph"

    # -- Paragraphs ---------------------------------------------------------

    def test_simple_paragraph(self):
        """Plain text becomes a paragraph with a text node."""
        result = markdown_to_adf("Hello world")
        self._assert_valid_adf(result)
        para = result["content"][0]
        assert para["type"] == "paragraph"
        texts = [n["text"] for n in para["content"] if n["type"] == "text"]
        assert "Hello world" in " ".join(texts)

    # -- Headings -----------------------------------------------------------

    @pytest.mark.parametrize(
        "md, level",
        [
            ("# H1", 1),
            ("## H2", 2),
            ("### H3", 3),
            ("#### H4", 4),
            ("##### H5", 5),
            ("###### H6", 6),
        ],
        ids=[f"heading_h{i}" for i in range(1, 7)],
    )
    def test_headings(self, md: str, level: int):
        """Headings produce heading nodes with the correct level attr."""
        result = markdown_to_adf(md)
        heading = result["content"][0]
        assert heading["type"] == "heading"
        assert heading["attrs"]["level"] == level

    # -- Inline formatting --------------------------------------------------

    def test_bold(self):
        """**bold** text gets a strong mark."""
        result = markdown_to_adf("**bold**")
        para = result["content"][0]
        bold_nodes = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "strong" for m in n.get("marks", []))
        ]
        assert len(bold_nodes) >= 1
        assert bold_nodes[0]["text"] == "bold"

    def test_italic(self):
        """*italic* text gets an em mark."""
        result = markdown_to_adf("*italic*")
        para = result["content"][0]
        italic_nodes = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "em" for m in n.get("marks", []))
        ]
        assert len(italic_nodes) >= 1
        assert italic_nodes[0]["text"] == "italic"

    def test_inline_code(self):
        """`code` text gets a code mark."""
        result = markdown_to_adf("`code`")
        para = result["content"][0]
        code_nodes = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "code" for m in n.get("marks", []))
        ]
        assert len(code_nodes) >= 1
        assert code_nodes[0]["text"] == "code"

    def test_strikethrough(self):
        """~~strike~~ text gets a strike mark."""
        result = markdown_to_adf("~~strike~~")
        para = result["content"][0]
        strike_nodes = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "strike" for m in n.get("marks", []))
        ]
        assert len(strike_nodes) >= 1
        assert strike_nodes[0]["text"] == "strike"

    # -- Links --------------------------------------------------------------

    def test_link(self):
        """[text](url) produces a text node with a link mark."""
        result = markdown_to_adf("[click here](https://example.com)")
        para = result["content"][0]
        link_nodes = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "link" for m in n.get("marks", []))
        ]
        assert len(link_nodes) >= 1
        assert link_nodes[0]["text"] == "click here"
        link_mark = next(m for m in link_nodes[0]["marks"] if m["type"] == "link")
        assert link_mark["attrs"]["href"] == "https://example.com"

    # -- Code blocks --------------------------------------------------------

    def test_code_block_with_lang(self):
        """Fenced code block with language attr."""
        md = "```python\nprint('hi')\n```"
        result = markdown_to_adf(md)
        cb = next(n for n in result["content"] if n["type"] == "codeBlock")
        assert cb["attrs"]["language"] == "python"
        code_text = cb["content"][0]["text"]
        assert "print('hi')" in code_text

    def test_code_block_no_lang(self):
        """Fenced code block without language."""
        md = "```\nsome code\n```"
        result = markdown_to_adf(md)
        cb = next(n for n in result["content"] if n["type"] == "codeBlock")
        # language should be absent or empty
        lang = cb.get("attrs", {}).get("language", "")
        assert lang == "" or lang is None or "language" not in cb.get("attrs", {})

    # -- Lists --------------------------------------------------------------

    def test_bullet_list(self):
        """- items produce a bulletList with listItem > paragraph > text."""
        md = "- alpha\n- beta"
        result = markdown_to_adf(md)
        bl = next(n for n in result["content"] if n["type"] == "bulletList")
        items = bl["content"]
        assert len(items) == 2
        for item in items:
            assert item["type"] == "listItem"
            # listItem must contain paragraph (not bare text)
            assert item["content"][0]["type"] == "paragraph"

    def test_ordered_list(self):
        """1. items produce an orderedList with listItem > paragraph > text."""
        md = "1. first\n2. second"
        result = markdown_to_adf(md)
        ol = next(n for n in result["content"] if n["type"] == "orderedList")
        items = ol["content"]
        assert len(items) == 2
        for item in items:
            assert item["type"] == "listItem"
            assert item["content"][0]["type"] == "paragraph"

    # -- Blockquote ---------------------------------------------------------

    def test_blockquote(self):
        """> text produces a blockquote wrapping a paragraph."""
        result = markdown_to_adf("> quoted text")
        bq = next(n for n in result["content"] if n["type"] == "blockquote")
        assert bq["content"][0]["type"] == "paragraph"

    # -- Horizontal rule ----------------------------------------------------

    @pytest.mark.parametrize(
        "md", ["---", "***", "___"], ids=["dashes", "stars", "underscores"]
    )
    def test_horizontal_rule(self, md: str):
        """Horizontal rule markers produce a rule node."""
        result = markdown_to_adf(md)
        rule_nodes = [n for n in result["content"] if n["type"] == "rule"]
        assert len(rule_nodes) >= 1

    # -- Mixed formatting ---------------------------------------------------

    def test_mixed_formatting(self):
        """Bold and italic in the same line get correct marks per segment."""
        result = markdown_to_adf("**bold** and *italic*")
        para = result["content"][0]
        assert para["type"] == "paragraph"
        # Find bold
        bold = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "strong" for m in n.get("marks", []))
        ]
        # Find italic
        italic = [
            n
            for n in para["content"]
            if n["type"] == "text"
            and any(m["type"] == "em" for m in n.get("marks", []))
        ]
        assert len(bold) >= 1
        assert len(italic) >= 1
        assert bold[0]["text"] == "bold"
        assert italic[0]["text"] == "italic"

    # -- Tables -------------------------------------------------------------

    def test_table_basic(self):
        """Pipe-delimited table produces table > tableRow > tableHeader/tableCell."""
        md = "| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |"
        result = markdown_to_adf(md)
        table = next(n for n in result["content"] if n["type"] == "table")
        rows = table["content"]
        assert len(rows) == 3  # header + 2 data rows

        # First row is header
        header_row = rows[0]
        assert header_row["type"] == "tableRow"
        assert all(c["type"] == "tableHeader" for c in header_row["content"])
        header_texts = [
            c["content"][0]["content"][0]["text"] for c in header_row["content"]
        ]
        assert header_texts == ["Name", "Age"]

        # Remaining rows are data cells
        for data_row in rows[1:]:
            assert data_row["type"] == "tableRow"
            assert all(c["type"] == "tableCell" for c in data_row["content"])

        # Verify data values
        data_texts = [c["content"][0]["content"][0]["text"] for c in rows[1]["content"]]
        assert data_texts == ["Alice", "30"]

    def test_table_with_inline_formatting(self):
        """Table cells preserve inline formatting (bold, code)."""
        md = "| Feature | Status |\n|---|---|\n| **Auth** | `done` |"
        result = markdown_to_adf(md)
        table = next(n for n in result["content"] if n["type"] == "table")
        data_row = table["content"][1]  # skip header

        # First cell should have bold
        first_cell_content = data_row["content"][0]["content"][0]["content"]
        bold_nodes = [
            n
            for n in first_cell_content
            if any(m["type"] == "strong" for m in n.get("marks", []))
        ]
        assert len(bold_nodes) == 1
        assert bold_nodes[0]["text"] == "Auth"

        # Second cell should have code
        second_cell_content = data_row["content"][1]["content"][0]["content"]
        code_nodes = [
            n
            for n in second_cell_content
            if any(m["type"] == "code" for m in n.get("marks", []))
        ]
        assert len(code_nodes) == 1
        assert code_nodes[0]["text"] == "done"

    def test_table_attrs(self):
        """Table node has required ADF attrs (isNumberColumnEnabled, layout)."""
        md = "| A |\n|---|\n| B |"
        result = markdown_to_adf(md)
        table = next(n for n in result["content"] if n["type"] == "table")
        assert table["attrs"]["isNumberColumnEnabled"] is False
        assert table["attrs"]["layout"] == "default"

    def test_table_alignment_separator(self):
        """Alignment separators (:---|:---:|---:) are skipped correctly."""
        md = "| Left | Center | Right |\n|:---|:---:|---:|\n| a | b | c |"
        result = markdown_to_adf(md)
        table = next(n for n in result["content"] if n["type"] == "table")
        # Should have 2 rows: header + 1 data (separator skipped)
        assert len(table["content"]) == 2

    # -- Roundtrip ----------------------------------------------------------

    def test_roundtrip(self):
        """markdown_to_adf → adf_to_text preserves the original words."""
        original = "Hello world with **bold** and *italic* text"
        adf = markdown_to_adf(original)
        text_back = adf_to_text(adf) or ""
        for word in ["Hello", "world", "bold", "italic", "text"]:
            assert word in text_back


class TestMarkdownToJiraDispatch:
    """Tests for _markdown_to_jira Cloud/Server dispatch."""

    @pytest.fixture
    def cloud_client(self):
        """Create a mock JiraClient configured for Cloud."""
        with patch("atlassian.Jira"):
            from mcp_atlassian.jira.client import JiraClient

            client = MagicMock(spec=JiraClient)
            client.config = MagicMock()
            client.config.is_cloud = True
            client.preprocessor = MagicMock()
            # Bind the real method to the mock
            client._markdown_to_jira = JiraClient._markdown_to_jira.__get__(
                client, JiraClient
            )
            return client

    @pytest.fixture
    def server_client(self):
        """Create a mock JiraClient configured for Server/DC."""
        with patch("atlassian.Jira"):
            from mcp_atlassian.jira.client import JiraClient

            client = MagicMock(spec=JiraClient)
            client.config = MagicMock()
            client.config.is_cloud = False
            client.preprocessor = MagicMock()
            client.preprocessor.markdown_to_jira.return_value = "wiki markup"
            client._markdown_to_jira = JiraClient._markdown_to_jira.__get__(
                client, JiraClient
            )
            return client

    def test_server_returns_string(self, server_client):
        """Server/DC path returns a string (wiki markup)."""
        result = server_client._markdown_to_jira("# Hello")
        assert isinstance(result, str)

    def test_cloud_returns_adf_dict(self, cloud_client):
        """Cloud path returns an ADF dict with version/type/content."""
        result = cloud_client._markdown_to_jira("# Hello")
        assert isinstance(result, dict)
        assert result["version"] == 1
        assert result["type"] == "doc"
        assert isinstance(result["content"], list)

    def test_cloud_empty(self, cloud_client):
        """Cloud path with empty string returns an ADF dict."""
        result = cloud_client._markdown_to_jira("")
        assert isinstance(result, dict)
        assert result["version"] == 1
        assert result["type"] == "doc"

    def test_server_empty(self, server_client):
        """Server/DC path with empty string returns empty string."""
        result = server_client._markdown_to_jira("")
        assert result == ""
