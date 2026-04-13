"""
Reproduction test for issue #1208: Support for ADF mention nodes in markdown_to_adf.

This test demonstrates that the current markdown_to_adf implementation does NOT
support mention syntax, which prevents users from properly mentioning/tagging
users in Jira Cloud comments.

Expected behavior:
  Input: @[John Doe](accountid:712020:abc-123)
  Output: ADF mention node with proper structure

Actual behavior:
  Input is treated as plain text, no mention node is generated
"""

import pytest

from src.mcp_atlassian.models.jira.adf import adf_to_text, markdown_to_adf


class TestMentionNodesReproduction:
    """Reproduction tests demonstrating the missing mention node support."""

    def test_mention_syntax_basic(self):
        """FIXED (#1208): Mention syntax now produces proper ADF mention nodes.

        After fix, @[Name](accountid:xxx) is correctly parsed as a mention node,
        not as a link. This enables user notifications in Jira Cloud.
        """
        # Given a comment with mention syntax (Markdown-like)
        markdown = "@[John Doe](accountid:712020:abc-123-def-456)"

        # When we convert to ADF
        result = markdown_to_adf(markdown)

        # Then we get a paragraph with a mention node
        para = result["content"][0]
        assert para["type"] == "paragraph"
        assert len(para["content"]) == 1

        # The mention node has the correct structure
        mention = para["content"][0]
        assert mention["type"] == "mention"
        assert mention["attrs"]["id"] == "712020:abc-123-def-456"
        assert mention["attrs"]["text"] == "@John Doe"

    def test_mention_syntax_expected_behavior(self):
        """EXPECTED: Mention syntax should produce a proper ADF mention node.

        This test is currently skipped because the feature doesn't exist yet.
        Once implemented, this test should pass.
        """
        # Given a comment with mention syntax
        markdown = "@[John Doe](accountid:712020:abc-123-def-456)"

        # When we convert to ADF
        result = markdown_to_adf(markdown)

        # Then we should get a paragraph with a mention node
        para = result["content"][0]
        assert para["type"] == "paragraph"

        # Find the mention node
        mention_nodes = [
            node for node in para["content"] if node.get("type") == "mention"
        ]
        assert len(mention_nodes) == 1

        # The mention node should have the correct structure
        mention = mention_nodes[0]
        assert mention["type"] == "mention"
        assert mention["attrs"]["id"] == "712020:abc-123-def-456"
        assert mention["attrs"]["text"] == "@John Doe"

    def test_multiple_mentions_in_text(self):
        """EXPECTED: Multiple mentions should all be converted properly."""
        markdown = (
            "Hey @[John](accountid:712020:aaa) "
            "and @[Jane](accountid:712020:bbb), please review."
        )

        result = markdown_to_adf(markdown)
        para = result["content"][0]

        # Should have 2 mention nodes plus surrounding text nodes
        mention_nodes = [
            node for node in para["content"] if node.get("type") == "mention"
        ]
        assert len(mention_nodes) == 2
        assert mention_nodes[0]["attrs"]["id"] == "712020:aaa"
        assert mention_nodes[1]["attrs"]["id"] == "712020:bbb"

    def test_mention_with_markdown_formatting(self):
        """EXPECTED: Mentions should work alongside other inline formatting."""
        markdown = "**Important**: @[Admin](accountid:712020:xyz) please check this"

        result = markdown_to_adf(markdown)
        para = result["content"][0]

        # Should have both bold text and a mention
        bold_nodes = [
            n
            for n in para["content"]
            if n.get("type") == "text"
            and any(m["type"] == "strong" for m in n.get("marks", []))
        ]
        mention_nodes = [n for n in para["content"] if n.get("type") == "mention"]

        assert len(bold_nodes) >= 1
        assert len(mention_nodes) == 1

    def test_mention_roundtrip(self):
        """EXPECTED: Mention should survive markdown → ADF → text roundtrip."""
        markdown = "Hello @[User](accountid:712020:abc) thanks"

        # markdown → ADF
        adf = markdown_to_adf(markdown)

        # ADF → text
        text_back = adf_to_text(adf) or ""

        # The mention should appear (adf_to_text already supports reading mentions)
        # Note: adf_to_text extracts the display text from mention nodes
        assert "@User" in text_back or "User" in text_back

    def test_adf_to_text_already_handles_mentions(self):
        """CONTEXT: The adf_to_text function ALREADY supports reading mentions.

        This proves that the ADF mention structure is well-understood on the
        read side. We just need to add write support (markdown → ADF).
        """
        # Given a proper ADF document with a mention node
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {
                            "type": "mention",
                            "attrs": {
                                "id": "712020:abc-123-def-456",
                                "text": "@John Doe",
                            },
                        },
                        {"type": "text", "text": " thanks!"},
                    ],
                }
            ],
        }

        # When we convert to text
        result = adf_to_text(adf)

        # Then the mention is extracted correctly
        assert result is not None
        assert "@John Doe" in result or "John Doe" in result


class TestAlternativeSyntaxOptions:
    """Tests exploring different mention syntax options."""

    @pytest.mark.skip(reason="Alternative syntax - not yet decided")
    def test_jira_wiki_markup_style(self):
        """Alternative: Support Jira's [~accountid:xxx] wiki markup style."""
        markdown = "Hey [~accountid:712020:abc-123] please review"

        result = markdown_to_adf(markdown)
        para = result["content"][0]

        mention_nodes = [
            node for node in para["content"] if node.get("type") == "mention"
        ]
        assert len(mention_nodes) == 1
        assert mention_nodes[0]["attrs"]["id"] == "712020:abc-123"
        # Note: with this syntax, we wouldn't have display text
        # Would need to use just the account ID as text

    @pytest.mark.skip(reason="Alternative syntax - not yet decided")
    def test_support_both_syntaxes(self):
        """Alternative: Support both Markdown-like AND Jira wiki markup."""
        markdown = "@[John](accountid:712020:aaa) and [~accountid:712020:bbb]"

        result = markdown_to_adf(markdown)
        para = result["content"][0]

        mention_nodes = [
            node for node in para["content"] if node.get("type") == "mention"
        ]
        # Both syntaxes should produce mention nodes
        assert len(mention_nodes) == 2
