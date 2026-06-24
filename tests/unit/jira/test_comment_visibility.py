"""Regression tests for comment visibility levels (upstream #725).

Verifies that add_comment correctly passes visibility restrictions to
the Jira API and rejects invalid combinations (visibility + public).
"""

from unittest.mock import Mock

import pytest

from mcp_atlassian.jira.comments import CommentsMixin


class TestCommentVisibility:
    """Visibility level regression tests for upstream #725."""

    @pytest.fixture
    def comments_mixin(self, jira_client):
        """Create a CommentsMixin instance with mocked dependencies."""
        mixin = CommentsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Set up a mock preprocessor with markdown_to_jira method
        mixin.preprocessor = Mock()
        mixin.preprocessor.markdown_to_jira = Mock(
            return_value="*This* is _Jira_ formatted"
        )

        # Mock the clean_text method
        mixin._clean_text = Mock(side_effect=lambda x: x)

        return mixin

    def test_add_comment_visibility_group_jira_developers(self, comments_mixin):
        """add_comment accepts group visibility restricting to jira-developers.

        Regression for https://github.com/sooperset/mcp-atlassian/issues/725
        """
        mock_response = {
            "id": "10001",
            "body": "Restricted comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        result = comments_mixin.add_comment(
            "TEST-123",
            "Restricted comment",
            visibility={"type": "group", "value": "jira-developers"},
        )

        call_args = comments_mixin._post_api3.call_args
        payload = call_args[0][1]
        assert payload["visibility"] == {"type": "group", "value": "jira-developers"}
        assert result["id"] == "10001"

    def test_add_comment_visibility_role_administrators(self, comments_mixin):
        """add_comment accepts role visibility restricting to Administrators.

        Regression for https://github.com/sooperset/mcp-atlassian/issues/725
        """
        mock_response = {
            "id": "10002",
            "body": "Admin-only comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "Jane Smith"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        result = comments_mixin.add_comment(
            "TEST-456",
            "Admin-only comment",
            visibility={"type": "role", "value": "Administrators"},
        )

        call_args = comments_mixin._post_api3.call_args
        payload = call_args[0][1]
        assert payload["visibility"] == {"type": "role", "value": "Administrators"}
        assert result["id"] == "10002"

    def test_add_comment_visibility_and_public_raises_value_error(self, comments_mixin):
        """Combining visibility with public=True raises ValueError.

        The ServiceDesk API (used when public is set) does not support Jira
        visibility restrictions — mixing both is rejected before any API call.

        Regression for https://github.com/sooperset/mcp-atlassian/issues/725
        """
        with pytest.raises(ValueError, match="Cannot use both"):
            comments_mixin.add_comment(
                "TEST-123",
                "Conflicting comment",
                visibility={"type": "group", "value": "jira-developers"},
                public=True,
            )
