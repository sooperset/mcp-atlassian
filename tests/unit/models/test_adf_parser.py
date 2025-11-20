"""Tests for ADF parser."""

from mcp_atlassian.models.jira.adf_parser import parse_adf_to_text


class TestADFParser:
    """Test ADF parsing functionality."""

    def test_parse_plain_text(self):
        """Test parsing plain text (non-ADF)."""
        result = parse_adf_to_text("Simple text")
        assert result == "Simple text"

    def test_parse_none(self):
        """Test parsing None value."""
        result = parse_adf_to_text(None)
        assert result == ""

    def test_parse_simple_adf_paragraph(self):
        """Test parsing simple ADF paragraph."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }
        result = parse_adf_to_text(adf)
        assert result == "Hello world"

    def test_parse_multiple_paragraphs(self):
        """Test parsing multiple paragraphs."""
        adf = {
            "type": "doc",
            "version": 1,
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
        result = parse_adf_to_text(adf)
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_parse_heading(self):
        """Test parsing heading."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Title"}],
                }
            ],
        }
        result = parse_adf_to_text(adf)
        assert result == "Title"

    def test_parse_code_block(self):
        """Test parsing code block."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "codeBlock",
                    "content": [{"type": "text", "text": "print('hello')"}],
                }
            ],
        }
        result = parse_adf_to_text(adf)
        assert "print('hello')" in result
        assert "```" in result

    def test_parse_bullet_list(self):
        """Test parsing bullet list."""
        adf = {
            "type": "doc",
            "version": 1,
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
        result = parse_adf_to_text(adf)
        assert "Item 1" in result
        assert "Item 2" in result

    def test_parse_mixed_content(self):
        """Test parsing mixed content types."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Normal text "},
                        {
                            "type": "text",
                            "text": "bold text",
                            "marks": [{"type": "strong"}],
                        },
                    ],
                },
                {"type": "hardBreak"},
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "After break"}],
                },
            ],
        }
        result = parse_adf_to_text(adf)
        assert "Normal text" in result
        assert "bold text" in result
        assert "After break" in result

    def test_parse_empty_adf(self):
        """Test parsing empty ADF document."""
        adf = {"type": "doc", "version": 1, "content": []}
        result = parse_adf_to_text(adf)
        assert result == ""

    def test_parse_nested_content(self):
        """Test parsing deeply nested content."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Quoted text"}],
                        }
                    ],
                }
            ],
        }
        result = parse_adf_to_text(adf)
        assert "Quoted text" in result

    def test_parse_malformed_adf(self):
        """Test parsing malformed ADF gracefully."""
        malformed_adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    # Missing content array
                }
            ],
        }
        result = parse_adf_to_text(malformed_adf)
        # Should not crash, return empty or minimal content
        assert isinstance(result, str)

    def test_parse_unknown_node_types(self):
        """Test parsing ADF with unknown node types."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "unknownNodeType",
                    "content": [{"type": "text", "text": "Unknown content"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Known content"}],
                },
            ],
        }
        result = parse_adf_to_text(adf)
        # Should extract text from unknown nodes and continue
        assert "Unknown content" in result
        assert "Known content" in result

    def test_parse_ordered_list(self):
        """Test parsing ordered list."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "First item"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Second item"}
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = parse_adf_to_text(adf)
        assert "First item" in result
        assert "Second item" in result

    def test_parse_complex_real_world_adf(self):
        """Test parsing complex real-world ADF structure."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Bug Description"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "The login functionality is "},
                        {
                            "type": "text",
                            "text": "broken",
                            "marks": [{"type": "strong"}],
                        },
                        {"type": "text", "text": " in the production environment."},
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Users cannot log in"}
                                    ],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Error 500 is returned",
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "codeBlock",
                    "attrs": {"language": "javascript"},
                    "content": [
                        {"type": "text", "text": "console.error('Login failed');"}
                    ],
                },
            ],
        }
        result = parse_adf_to_text(adf)

        # Should contain all text content
        assert "Bug Description" in result
        assert "broken" in result
        assert "production environment" in result
        assert "Users cannot log in" in result
        assert "Error 500 is returned" in result
        assert "console.error('Login failed');" in result

    def test_parse_non_dict_input(self):
        """Test parsing non-dictionary input."""
        result = parse_adf_to_text(123)
        assert result == "123"

        result = parse_adf_to_text([])
        assert result == ""  # Empty list returns empty string

    def test_parse_empty_content_arrays(self):
        """Test parsing ADF with empty content arrays."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Non-empty paragraph"}],
                },
            ],
        }
        result = parse_adf_to_text(adf)
        assert "Non-empty paragraph" in result
