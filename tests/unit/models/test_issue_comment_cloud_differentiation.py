"""Tests for cloud/non-cloud differentiation in issue and comment models."""

import pytest

from mcp_atlassian.models.jira import JiraComment, JiraIssue


class TestCloudNonCloudDifferentiation:
    """Test cloud vs non-cloud behavior in models."""

    def test_jira_issue_description_cloud_adf_parsing(self):
        """Test that Cloud issues parse ADF descriptions to text."""
        # Cloud ADF description
        adf_description = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "This is a test description"}],
                }
            ],
        }

        api_response = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": adf_description,
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
                "reporter": {"displayName": "Jane Doe"},
                "created": "2023-01-01T00:00:00.000Z",
                "updated": "2023-01-01T00:00:00.000Z",
            },
        }

        # Test Cloud parsing (is_cloud=True)
        issue_cloud = JiraIssue.from_api_response(api_response, is_cloud=True)
        assert issue_cloud.description == "This is a test description"
        assert isinstance(issue_cloud.description, str)

        # Test Server/DC parsing (is_cloud=False) - should convert dict to string
        issue_server = JiraIssue.from_api_response(api_response, is_cloud=False)
        assert isinstance(issue_server.description, str)
        # Server/DC should get string representation of the dict
        assert "type" in issue_server.description and "doc" in issue_server.description

    def test_jira_issue_description_server_plain_text(self):
        """Test that Server/DC issues handle plain text descriptions."""
        api_response = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": "This is a plain text description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
                "reporter": {"displayName": "Jane Doe"},
                "created": "2023-01-01T00:00:00.000Z",
                "updated": "2023-01-01T00:00:00.000Z",
            },
        }

        # Both Cloud and Server/DC should handle plain text the same way
        issue_cloud = JiraIssue.from_api_response(api_response, is_cloud=True)
        issue_server = JiraIssue.from_api_response(api_response, is_cloud=False)

        assert issue_cloud.description == "This is a plain text description"
        assert issue_server.description == "This is a plain text description"
        assert isinstance(issue_cloud.description, str)
        assert isinstance(issue_server.description, str)

    def test_jira_issue_description_none_handling(self):
        """Test handling of None descriptions in both Cloud and Server/DC."""
        api_response = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": None,
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
                "reporter": {"displayName": "Jane Doe"},
                "created": "2023-01-01T00:00:00.000Z",
                "updated": "2023-01-01T00:00:00.000Z",
            },
        }

        # Both should handle None the same way
        issue_cloud = JiraIssue.from_api_response(api_response, is_cloud=True)
        issue_server = JiraIssue.from_api_response(api_response, is_cloud=False)

        assert issue_cloud.description is None
        assert issue_server.description is None

    def test_jira_comment_cloud_adf_parsing(self):
        """Test that Cloud comments parse ADF body to text."""
        # Cloud ADF comment body
        adf_body = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "This is a test comment"}],
                }
            ],
        }

        api_response = {
            "id": "10001",
            "body": adf_body,
            "author": {"displayName": "John Doe"},
            "created": "2023-01-01T00:00:00.000Z",
            "updated": "2023-01-01T00:00:00.000Z",
        }

        # Test Cloud parsing (is_cloud=True)
        comment_cloud = JiraComment.from_api_response(api_response, is_cloud=True)
        assert comment_cloud.body == "This is a test comment"
        assert isinstance(comment_cloud.body, str)

        # Test Server/DC parsing (is_cloud=False) - should convert dict to string
        comment_server = JiraComment.from_api_response(api_response, is_cloud=False)
        assert isinstance(comment_server.body, str)
        # Server/DC should get string representation of the dict
        assert "type" in comment_server.body and "doc" in comment_server.body

    def test_jira_comment_server_plain_text(self):
        """Test that Server/DC comments handle plain text bodies."""
        api_response = {
            "id": "10001",
            "body": "This is a plain text comment",
            "author": {"displayName": "John Doe"},
            "created": "2023-01-01T00:00:00.000Z",
            "updated": "2023-01-01T00:00:00.000Z",
        }

        # Both Cloud and Server/DC should handle plain text the same way
        comment_cloud = JiraComment.from_api_response(api_response, is_cloud=True)
        comment_server = JiraComment.from_api_response(api_response, is_cloud=False)

        assert comment_cloud.body == "This is a plain text comment"
        assert comment_server.body == "This is a plain text comment"
        assert isinstance(comment_cloud.body, str)
        assert isinstance(comment_server.body, str)

    def test_jira_comment_empty_body_handling(self):
        """Test handling of empty/None comment bodies."""
        api_response = {
            "id": "10001",
            "body": "",
            "author": {"displayName": "John Doe"},
            "created": "2023-01-01T00:00:00.000Z",
            "updated": "2023-01-01T00:00:00.000Z",
        }

        # Both should handle empty body the same way
        comment_cloud = JiraComment.from_api_response(api_response, is_cloud=True)
        comment_server = JiraComment.from_api_response(api_response, is_cloud=False)

        assert comment_cloud.body == ""
        assert comment_server.body == ""

    def test_complex_adf_parsing_cloud_vs_server(self):
        """Test complex ADF structures are handled differently in Cloud vs Server/DC."""
        complex_adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "This is "},
                        {
                            "type": "text",
                            "text": "bold text",
                            "marks": [{"type": "strong"}],
                        },
                        {"type": "text", "text": " and normal text."},
                    ],
                },
                {
                    "type": "codeBlock",
                    "content": [{"type": "text", "text": "print('hello world')"}],
                },
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
                },
            ],
        }

        # Test with issue description
        api_response = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": complex_adf,
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
                "reporter": {"displayName": "Jane Doe"},
                "created": "2023-01-01T00:00:00.000Z",
                "updated": "2023-01-01T00:00:00.000Z",
            },
        }

        # Cloud should parse ADF to readable text
        issue_cloud = JiraIssue.from_api_response(api_response, is_cloud=True)
        cloud_desc = issue_cloud.description

        # Should contain the parsed text elements
        assert "This is" in cloud_desc
        assert "bold text" in cloud_desc
        assert "and normal text" in cloud_desc
        assert "print('hello world')" in cloud_desc
        assert "Item 1" in cloud_desc
        assert "Item 2" in cloud_desc
        assert "```" in cloud_desc  # Code block formatting

        # Server/DC should get string representation
        issue_server = JiraIssue.from_api_response(api_response, is_cloud=False)
        server_desc = issue_server.description

        # Should contain JSON-like structure
        assert "type" in server_desc
        assert "doc" in server_desc
        assert isinstance(server_desc, str)

        # The two should be different
        assert cloud_desc != server_desc

    @pytest.mark.parametrize("is_cloud", [True, False])
    def test_issue_model_consistency_across_environments(self, is_cloud):
        """Test that issue models are consistent regardless of environment."""
        api_response = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": "Plain text description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
                "reporter": {"displayName": "Jane Doe"},
                "created": "2023-01-01T00:00:00.000Z",
                "updated": "2023-01-01T00:00:00.000Z",
                "labels": ["bug", "urgent"],
            },
        }

        issue = JiraIssue.from_api_response(api_response, is_cloud=is_cloud)

        # Core fields should be consistent
        assert issue.id == "10001"
        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.status.name == "Open"
        assert issue.issue_type.name == "Bug"
        assert issue.priority.name == "High"
        assert issue.assignee.display_name == "John Doe"
        assert issue.reporter.display_name == "Jane Doe"
        assert issue.labels == ["bug", "urgent"]

        # Description should be string in both cases for plain text
        assert issue.description == "Plain text description"
        assert isinstance(issue.description, str)

    @pytest.mark.parametrize("is_cloud", [True, False])
    def test_comment_model_consistency_across_environments(self, is_cloud):
        """Test that comment models are consistent regardless of environment."""
        api_response = {
            "id": "10001",
            "body": "This is a plain text comment",
            "author": {"displayName": "John Doe", "emailAddress": "john@example.com"},
            "created": "2023-01-01T00:00:00.000Z",
            "updated": "2023-01-01T00:00:00.000Z",
        }

        comment = JiraComment.from_api_response(api_response, is_cloud=is_cloud)

        # Core fields should be consistent
        assert comment.id == "10001"
        assert comment.body == "This is a plain text comment"
        assert comment.author.display_name == "John Doe"
        assert isinstance(comment.body, str)
