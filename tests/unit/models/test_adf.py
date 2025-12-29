"""
Tests for the ADF (Atlassian Document Format) parser.

These tests validate the adf_to_text function which converts Jira Cloud's
rich text format (ADF) to plain text for display and processing.
"""

import pytest

from src.mcp_atlassian.models.jira.adf import adf_to_text


class TestAdfToText:
    """Tests for the adf_to_text function."""

    # =========================================================================
    # Basic Input Handling
    # =========================================================================

    def test_none_input(self):
        """Test that None input returns None."""
        assert adf_to_text(None) is None

    def test_string_input(self):
        """Test that string input is returned as-is."""
        assert adf_to_text("plain text") == "plain text"

    def test_string_input_empty(self):
        """Test that empty string input returns empty string."""
        assert adf_to_text("") == ""

    def test_empty_dict(self):
        """Test that empty dict returns None."""
        assert adf_to_text({}) is None

    def test_empty_list(self):
        """Test that empty list returns None."""
        assert adf_to_text([]) is None

    # =========================================================================
    # Text Nodes
    # =========================================================================

    def test_simple_text_node(self):
        """Test simple text node extraction."""
        node = {"type": "text", "text": "Hello World"}
        assert adf_to_text(node) == "Hello World"

    def test_text_node_empty_text(self):
        """Test text node with empty string."""
        node = {"type": "text", "text": ""}
        assert adf_to_text(node) == ""

    def test_text_node_missing_text(self):
        """Test text node without text field returns empty string."""
        node = {"type": "text"}
        assert adf_to_text(node) == ""

    def test_text_node_with_marks(self):
        """Test text node with formatting marks (marks are ignored, text extracted)."""
        node = {
            "type": "text",
            "text": "Bold text",
            "marks": [{"type": "strong"}],
        }
        assert adf_to_text(node) == "Bold text"

    # =========================================================================
    # HardBreak Nodes
    # =========================================================================

    def test_hardbreak_node(self):
        """Test hardBreak node returns newline."""
        node = {"type": "hardBreak"}
        assert adf_to_text(node) == "\n"

    # =========================================================================
    # Content Processing
    # =========================================================================

    def test_paragraph_with_text(self):
        """Test paragraph containing a text node."""
        paragraph = {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Hello"}],
        }
        assert adf_to_text(paragraph) == "Hello"

    def test_paragraph_with_multiple_text_nodes(self):
        """Test paragraph with multiple text nodes joined."""
        paragraph = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "World"},
            ],
        }
        assert adf_to_text(paragraph) == "Hello \nWorld"

    def test_paragraph_with_hardbreak(self):
        """Test paragraph with text and hardBreak."""
        paragraph = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Line 1"},
                {"type": "hardBreak"},
                {"type": "text", "text": "Line 2"},
            ],
        }
        result = adf_to_text(paragraph)
        assert "Line 1" in result
        assert "Line 2" in result
        assert "\n" in result

    def test_nested_content(self):
        """Test deeply nested content structures."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Nested text"}],
                }
            ],
        }
        assert adf_to_text(doc) == "Nested text"

    def test_multiple_paragraphs(self):
        """Test document with multiple paragraphs."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "First paragraph"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Second paragraph"}],
                },
            ],
        }
        result = adf_to_text(doc)
        assert "First paragraph" in result
        assert "Second paragraph" in result

    # =========================================================================
    # Full ADF Documents
    # =========================================================================

    def test_full_adf_document(self):
        """Test complete ADF document with type: doc."""
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "This is a test description."}
                    ],
                }
            ],
        }
        assert adf_to_text(adf) == "This is a test description."

    def test_complex_adf_document(self):
        """Test complex ADF with multiple blocks and formatting."""
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Introduction paragraph."}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Second "},
                        {
                            "type": "text",
                            "text": "paragraph",
                            "marks": [{"type": "strong"}],
                        },
                        {"type": "text", "text": " here."},
                    ],
                },
            ],
        }
        result = adf_to_text(adf)
        assert "Introduction paragraph." in result
        assert "Second" in result
        assert "paragraph" in result
        assert "here." in result

    def test_adf_with_bullet_list(self):
        """Test ADF with bullet list structure."""
        adf = {
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
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 2"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "Item 1" in result
        assert "Item 2" in result

    def test_adf_with_heading(self):
        """Test ADF with heading structure."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Main Heading"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Body text."}],
                },
            ],
        }
        result = adf_to_text(adf)
        assert "Main Heading" in result
        assert "Body text." in result

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_unknown_node_type(self):
        """Test that unknown node type without content returns None."""
        node = {"type": "unknownType"}
        assert adf_to_text(node) is None

    def test_unknown_node_type_with_content(self):
        """Test that unknown node type with content still extracts content."""
        node = {
            "type": "unknownType",
            "content": [{"type": "text", "text": "Extracted"}],
        }
        assert adf_to_text(node) == "Extracted"

    def test_node_without_content(self):
        """Test dict without content field returns None."""
        node = {"type": "paragraph"}
        assert adf_to_text(node) is None

    def test_list_with_mixed_content(self):
        """Test list containing None, strings, and dicts."""
        content = [
            None,
            {"type": "text", "text": "Valid"},
            None,
        ]
        # None items should be filtered out
        result = adf_to_text(content)
        assert result == "Valid"

    def test_list_with_all_none(self):
        """Test list containing only None values returns None."""
        content = [None, None]
        assert adf_to_text(content) is None

    def test_content_with_empty_paragraph(self):
        """Test paragraph with empty content list."""
        paragraph = {"type": "paragraph", "content": []}
        assert adf_to_text(paragraph) is None

    def test_deeply_nested_structure(self):
        """Test very deeply nested content structure."""
        deep = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Deeply nested quote",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        assert adf_to_text(deep) == "Deeply nested quote"

    # =========================================================================
    # XFail Tests for Future Node Types
    # =========================================================================

    @pytest.mark.xfail(reason="mention node type not yet implemented")
    def test_mention_node(self):
        """Test @mention nodes should extract user info."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {
                            "type": "mention",
                            "attrs": {
                                "id": "user123",
                                "text": "@john.doe",
                                "accessLevel": "",
                            },
                        },
                        {"type": "text", "text": "!"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should contain mention text like "@john.doe"
        assert "@john.doe" in result or "john.doe" in result

    @pytest.mark.xfail(reason="emoji node type not yet implemented")
    def test_emoji_node(self):
        """Test emoji nodes should extract emoji representation."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Great job "},
                        {
                            "type": "emoji",
                            "attrs": {
                                "shortName": ":thumbsup:",
                                "id": "1f44d",
                                "text": "\ud83d\udc4d",
                            },
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should contain emoji text or shortName
        assert ":thumbsup:" in result or "\ud83d\udc4d" in result

    @pytest.mark.xfail(reason="date node type not yet implemented")
    def test_date_node(self):
        """Test date nodes should extract date value."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Due: "},
                        {
                            "type": "date",
                            "attrs": {"timestamp": "1704067200000"},
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should contain some date representation
        assert "2024" in result or "1704067200000" in result

    @pytest.mark.xfail(reason="status node type not yet implemented")
    def test_status_node(self):
        """Test status nodes should extract status text."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Status: "},
                        {
                            "type": "status",
                            "attrs": {
                                "text": "IN PROGRESS",
                                "color": "blue",
                            },
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should contain status text
        assert "IN PROGRESS" in result

    @pytest.mark.xfail(reason="inlineCard node type not yet implemented")
    def test_inline_card_node(self):
        """Test inlineCard (smart link) nodes should extract URL or title."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "See: "},
                        {
                            "type": "inlineCard",
                            "attrs": {
                                "url": "https://example.atlassian.net/browse/PROJ-123"
                            },
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should contain URL or something meaningful
        assert "PROJ-123" in result or "example.atlassian.net" in result
