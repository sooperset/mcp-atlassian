"""Integration tests for Jira wiki markup <-> Markdown format conversion.

These tests verify that the format conversion pipeline works end-to-end:
- Reading from Jira: Wiki markup → Markdown
- Writing to Jira: Markdown → Wiki markup

This ensures that the conversion functions are actually called in the read/write flow,
which was broken in PR #72 (March 2025) and went undetected for 11 months.
"""

import pytest


class TestFormatConversionIntegration:
    """Integration tests for format conversion in get_issue/create_issue flow."""

    @pytest.fixture
    def jira_fetcher_with_real_preprocessor(self, jira_fetcher):
        """Use JiraFetcher with real preprocessor to test actual conversion."""
        # JiraFetcher already has a real preprocessor, so we just return it
        return jira_fetcher

    def test_get_issue_converts_wiki_markup_description_to_markdown(self, jira_fetcher_with_real_preprocessor):
        """Test that reading an issue converts Jira wiki markup description to Markdown.

        This test would have caught the regression bug in PR #72 where _clean_text()
        was not being called on descriptions.
        """
        # Mock API response with Jira wiki markup in description
        jira_fetcher_with_real_preprocessor.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "h2. Summary\n\nThis is *bold* text.\n\n|| Header 1 || Header 2 ||\n| Cell 1 | Cell 2 |",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "created": "2023-01-01T12:00:00.000+0000",
                "updated": "2023-01-01T12:00:00.000+0000",
            },
        }

        # Call get_issue
        result = jira_fetcher_with_real_preprocessor.get_issue("TEST-123")

        # Verify description was converted to Markdown
        assert result.description is not None
        assert "## Summary" in result.description  # h2. → ##
        assert "**bold**" in result.description  # *bold* → **bold**
        assert "| Header 1 | Header 2 |" in result.description  # || → |

        # Should NOT contain Jira wiki markup
        assert "h2." not in result.description
        assert "||" not in result.description

    def test_get_issue_converts_wiki_markup_comments_to_markdown(self, jira_fetcher_with_real_preprocessor):
        """Test that reading issue comments converts Jira wiki markup to Markdown.

        This test would have caught the regression bug where comment bodies
        were not being cleaned.
        """
        # Mock API response with Jira wiki markup in comments
        jira_fetcher_with_real_preprocessor.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "Test description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "created": "2023-01-01T12:00:00.000+0000",
                "updated": "2023-01-01T12:00:00.000+0000",
                "comment": {
                    "comments": [
                        {
                            "id": "10001",
                            "body": "h1. Important Update\n\n# First item\n# Second item\n\n*Status:* Done",
                            "created": "2023-01-01T10:00:00.000+0000",
                            "updated": "2023-01-01T10:00:00.000+0000",
                            "author": {"displayName": "Test User"},
                        }
                    ]
                },
            },
        }

        # Need to mock issue_get_comments as well
        jira_fetcher_with_real_preprocessor.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": "h1. Important Update\n\n# First item\n# Second item\n\n*Status:* Done",
                    "created": "2023-01-01T10:00:00.000+0000",
                    "updated": "2023-01-01T10:00:00.000+0000",
                    "author": {"displayName": "Test User"},
                }
            ]
        }

        # Call get_issue with comments
        result = jira_fetcher_with_real_preprocessor.get_issue("TEST-123", comment_limit=10)

        # Verify comment body was converted to Markdown
        assert len(result.comments) == 1
        comment_body = result.comments[0].body

        assert "# Important Update" in comment_body  # h1. → #
        assert "1. First item" in comment_body  # # → 1.
        assert "**Status:** Done" in comment_body  # *Status:* → **Status:**

        # Should NOT contain Jira wiki markup
        assert "h1." not in comment_body

    def test_get_issue_handles_adf_format(self, jira_fetcher_with_real_preprocessor):
        """Test that ADF (Atlassian Document Format) is converted to plain text.

        ADF is used by Jira Cloud with the new editor.
        """
        # Mock API response with ADF format (dict instead of string)
        jira_fetcher_with_real_preprocessor.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "This is ADF content"}],
                        }
                    ],
                },
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "created": "2023-01-01T12:00:00.000+0000",
                "updated": "2023-01-01T12:00:00.000+0000",
            },
        }

        # Call get_issue
        result = jira_fetcher_with_real_preprocessor.get_issue("TEST-123")

        # Verify ADF was converted to plain text
        assert result.description == "This is ADF content"

    def test_create_issue_converts_markdown_description_to_jira(self, jira_fetcher_with_real_preprocessor):
        """Test that creating an issue converts Markdown description to Jira wiki markup.

        This verifies the write path: Markdown → Jira wiki markup.
        """
        # Mock API response
        jira_fetcher_with_real_preprocessor.jira.create_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "self": "https://test.atlassian.net/rest/api/3/issue/TEST-123",
        }

        # Create issue with Markdown description
        markdown_description = """## Summary

This is **bold** and *italic* text.

1. First item
2. Second item

| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
"""

        result = jira_fetcher_with_real_preprocessor.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Task",
            description=markdown_description,
        )

        # Verify create_issue was called with Jira wiki markup
        call_args = jira_fetcher_with_real_preprocessor.jira.create_issue.call_args
        sent_fields = call_args[1]["fields"]
        sent_description = sent_fields["description"]

        # Should be converted to Jira wiki markup
        assert "h2. Summary" in sent_description  # ## → h2.
        assert "*bold*" in sent_description  # **bold** → *bold*
        assert "_italic_" in sent_description  # *italic* → _italic_
        assert "# First item" in sent_description  # 1. → #
        assert "# Second item" in sent_description  # 2. → #
        assert "||" in sent_description  # | Header | → || Header ||

        # Should NOT contain Markdown
        assert "**bold**" not in sent_description
        assert "1. First" not in sent_description

    def test_numbered_list_not_converted_to_heading(self, jira_fetcher_with_real_preprocessor):
        """Test that Jira numbered lists (# Item) don't get converted to headings (h1.).

        This is the specific bug reported in TODO-BULLETLIST.md:
        When markdown `1. Item` is converted to Jira `# Item`, and then re-processed,
        it should NOT be converted to `h1. Item`.

        With our fix, this should not happen because:
        1. Reading from Jira: `# Item` → `1. Item` (Markdown)
        2. Writing to Jira: `1. Item` → `# Item` (Jira)

        The conversion is idempotent and format-aware.
        """
        # Mock API response with Jira numbered list
        jira_fetcher_with_real_preprocessor.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "h3. Next Steps\n\n# Wait for mirrors to stabilize\n# Apply patch if needed\n# Retry build",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "created": "2023-01-01T12:00:00.000+0000",
                "updated": "2023-01-01T12:00:00.000+0000",
            },
        }

        # Call get_issue
        result = jira_fetcher_with_real_preprocessor.get_issue("TEST-123")

        # Verify numbered list was converted correctly
        assert result.description is not None
        assert "### Next Steps" in result.description  # h3. → ###
        assert "1. Wait for mirrors" in result.description  # # → 1.
        assert "1. Apply patch" in result.description  # # → 1. (Markdown uses 1. for all items)
        assert "1. Retry build" in result.description  # # → 1. (auto-numbered by renderer)

        # Should NOT contain headings for list items or Jira h1. markup
        assert "h1." not in result.description

    def test_mixed_jira_and_markdown_handled_correctly(self, jira_fetcher_with_real_preprocessor):
        """Test that mixed Jira/Markdown content is handled gracefully.

        When reading from Jira, we should get clean Markdown.
        """
        # Mock API response with various Jira wiki markup elements
        jira_fetcher_with_real_preprocessor.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "h2. Overview\n\n*Bold* and _underline_ text.\n\n{code:python}\nprint('hello')\n{code}\n\n* Bullet 1\n** Nested bullet\n\n# Numbered 1\n# Numbered 2",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "created": "2023-01-01T12:00:00.000+0000",
                "updated": "2023-01-01T12:00:00.000+0000",
            },
        }

        # Call get_issue
        result = jira_fetcher_with_real_preprocessor.get_issue("TEST-123")

        # Verify conversion to Markdown
        assert result.description is not None
        assert "## Overview" in result.description
        assert "**Bold**" in result.description
        assert "```python" in result.description or "```" in result.description
        assert "- Bullet 1" in result.description  # Jira * → Markdown -
        assert "1. Numbered 1" in result.description
        # Markdown often uses 1. for all numbered items (auto-numbered by renderer)
