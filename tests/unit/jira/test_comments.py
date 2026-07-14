"""Tests for the Jira Comments mixin."""

from unittest.mock import Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira.comments import CommentsMixin


class TestCommentsMixin:
    """Tests for the CommentsMixin class."""

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

    def test_get_issue_comments_basic(self, comments_mixin):
        """Test get_issue_comments with basic data."""
        # Setup mock response
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": "This is a comment",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T11:00:00.000+0000",
                    "author": {"displayName": "John Doe"},
                }
            ]
        }

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        comments_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["body"] == "This is a comment"
        assert result[0]["created"] == "2024-01-01 10:00:00+00:00"  # Parsed date
        assert result[0]["author"] == "John Doe"

    def test_get_issue_comments_with_limit(self, comments_mixin):
        """Test get_issue_comments with limit parameter."""
        # Setup mock response with multiple comments
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": "First comment",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "author": {"displayName": "John Doe"},
                },
                {
                    "id": "10002",
                    "body": "Second comment",
                    "created": "2024-01-02T10:00:00.000+0000",
                    "author": {"displayName": "Jane Smith"},
                },
                {
                    "id": "10003",
                    "body": "Third comment",
                    "created": "2024-01-03T10:00:00.000+0000",
                    "author": {"displayName": "Bob Johnson"},
                },
            ]
        }

        # Call the method with limit=2
        result = comments_mixin.get_issue_comments("TEST-123", limit=2)

        # Verify
        comments_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
        assert len(result) == 2  # Only 2 comments should be returned
        assert result[0]["id"] == "10001"
        assert result[1]["id"] == "10002"
        # Third comment shouldn't be included due to limit

    def test_get_issue_comments_with_missing_fields(self, comments_mixin):
        """Test get_issue_comments with missing fields in the response."""
        # Setup mock response with missing fields
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    # Missing body field
                    "created": "2024-01-01T10:00:00.000+0000",
                    # Missing author field
                },
                {
                    # Missing id field
                    "body": "Second comment",
                    # Missing created field
                    "author": {},  # Empty author object
                },
                {
                    "id": "10003",
                    "body": "Third comment",
                    "created": "2024-01-03T10:00:00.000+0000",
                    "author": {"name": "user123"},  # Using name instead of displayName
                },
            ]
        }

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        assert len(result) == 3
        assert result[0]["id"] == "10001"
        assert result[0]["body"] == ""  # Should default to empty string
        assert result[0]["author"] == "Unknown"  # Should default to Unknown

        assert (
            "id" not in result[1] or not result[1]["id"]
        )  # Should be missing or empty
        assert result[1]["author"] == "Unknown"  # Should default to Unknown

        assert (
            result[2]["author"] == "Unknown"
        )  # Should use Unknown when only name is available

    def test_get_issue_comments_with_empty_response(self, comments_mixin):
        """Test get_issue_comments with an empty response."""
        # Setup mock response with no comments
        comments_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call the method
        result = comments_mixin.get_issue_comments("TEST-123")

        # Verify
        assert len(result) == 0  # Should return an empty list

    def test_get_issue_comments_with_error(self, comments_mixin):
        """Test get_issue_comments with an error response."""
        # Setup mock to raise exception
        comments_mixin.jira.issue_get_comments.side_effect = Exception("API Error")

        # Verify it raises the wrapped exception
        with pytest.raises(Exception, match="Error getting comments"):
            comments_mixin.get_issue_comments("TEST-123")

    def test_get_issue_comments_adf_body(self, comments_mixin):
        """Regression test for #1488: Jira Cloud (REST API v3) returns
        comment bodies as ADF dicts; get_issue_comments previously raised
        TypeError from re.sub() in _process_mentions because the dict was
        passed straight to _clean_text. adf_to_text() must be applied
        first, matching the pattern in add_comment / edit_comment."""
        comments_mixin.jira.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Hello from ADF",
                                    }
                                ],
                            }
                        ],
                    },
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T11:00:00.000+0000",
                    "author": {"displayName": "John Doe"},
                },
                {
                    "id": "10002",
                    # Plain string body must still work unchanged
                    "body": "This is a plain text comment",
                    "created": "2024-01-02T10:00:00.000+0000",
                    "updated": "2024-01-02T11:00:00.000+0000",
                    "author": {"displayName": "Jane Smith"},
                },
            ]
        }

        result = comments_mixin.get_issue_comments("TEST-123")

        assert len(result) == 2
        # ADF body converted to plain text and forwarded to _clean_text.
        # The fixture's mock _clean_text is the identity function, so the
        # plain-text extraction result is what comes back.
        assert "Hello from ADF" in result[0]["body"]
        assert "doc" not in result[0]["body"]
        # Plain string body passes through adf_to_text unchanged.
        assert result[1]["body"] == "This is a plain text comment"

    def test_add_comment_basic(self, comments_mixin):
        """Test add_comment with basic data (Cloud → ADF via v3 API)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "This is a comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        # Call the method
        result = comments_mixin.add_comment("TEST-123", "Test comment")

        # On Cloud, ADF goes through _post_api3 (not issue_add_comment)
        comments_mixin._post_api3.assert_called_once()
        call_args = comments_mixin._post_api3.call_args
        assert call_args[0][0] == "issue/TEST-123/comment"
        adf_body = call_args[0][1]["body"]
        assert isinstance(adf_body, dict)
        assert adf_body["version"] == 1
        assert adf_body["type"] == "doc"
        # preprocessor.markdown_to_jira should NOT be called on Cloud
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["id"] == "10001"
        assert result["body"] == "This is a comment"
        assert result["created"] == "2024-01-01 10:00:00+00:00"
        assert result["author"] == "John Doe"

    def test_add_comment_with_markdown_conversion(self, comments_mixin):
        """Test add_comment with markdown conversion (Cloud → ADF via v3)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "Heading and content",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        markdown_comment = "# Heading 1\n\nThis is **bold** text."

        # Call the method
        result = comments_mixin.add_comment("TEST-123", markdown_comment)

        # On Cloud, should produce ADF via v3 API, not call preprocessor
        call_args = comments_mixin._post_api3.call_args
        adf_body = call_args[0][1]["body"]
        assert isinstance(adf_body, dict)
        assert adf_body["version"] == 1
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["body"] == "Heading and content"

    def test_add_comment_with_accountid_mention_uses_adf_node(
        self, comments_mixin: CommentsMixin
    ) -> None:
        """Test [~accountid:...] comments become ADF mention nodes on Cloud."""
        mock_response = {
            "id": "10001",
            "body": "Mention comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        account_id = "712020:1cfc6d16-950f-4096-8e57-f2c6c60d8ffa"
        comments_mixin.add_comment("TEST-123", f"Hello [~accountid:{account_id}]")

        call_args = comments_mixin._post_api3.call_args
        adf_body = call_args[0][1]["body"]
        assert adf_body["content"][0]["content"] == [
            {"type": "text", "text": "Hello "},
            {"type": "mention", "attrs": {"id": account_id}},
        ]
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()

    def test_add_comment_with_empty_comment(self, comments_mixin):
        """Test add_comment with an empty comment (Cloud → minimal ADF)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        # Call the method with empty comment
        result = comments_mixin.add_comment("TEST-123", "")

        # On Cloud, empty string produces a minimal ADF dict via v3 API
        call_args = comments_mixin._post_api3.call_args
        adf_body = call_args[0][1]["body"]
        assert isinstance(adf_body, dict)
        assert adf_body["version"] == 1
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["body"] == ""

    def test_add_comment_with_restricted_visibility(self, comments_mixin):
        """Test add_comment with visibility set (Cloud → ADF via v3)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "This is a comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        # Call the method
        result = comments_mixin.add_comment(
            "TEST-123", "Test comment", {"type": "group", "value": "restricted"}
        )

        # Verify ADF via v3 API with visibility
        call_args = comments_mixin._post_api3.call_args
        assert call_args[0][0] == "issue/TEST-123/comment"
        payload = call_args[0][1]
        assert isinstance(payload["body"], dict)
        assert payload["body"]["version"] == 1
        assert payload["visibility"] == {"type": "group", "value": "restricted"}
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["id"] == "10001"
        assert result["body"] == "This is a comment"
        assert result["created"] == "2024-01-01 10:00:00+00:00"
        assert result["author"] == "John Doe"

    def test_add_comment_with_role_visibility(self, comments_mixin):
        """Test add_comment with role visibility set (Cloud → ADF via v3)."""
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
        assert call_args[0][0] == "issue/TEST-456/comment"
        payload = call_args[0][1]
        assert isinstance(payload["body"], dict)
        assert payload["body"]["version"] == 1
        assert payload["visibility"] == {"type": "role", "value": "Administrators"}
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["id"] == "10002"
        assert result["body"] == "Admin-only comment"
        assert result["created"] == "2024-01-01 10:00:00+00:00"
        assert result["author"] == "Jane Smith"

    def test_add_comment_with_error(self, comments_mixin):
        """Test add_comment with an error response."""
        # Setup mock to raise exception (Cloud uses _post_api3)
        comments_mixin._post_api3 = Mock(side_effect=Exception("API Error"))

        # Verify it raises the wrapped exception
        with pytest.raises(Exception, match="Error adding comment"):
            comments_mixin.add_comment("TEST-123", "Test comment")

    def test_edit_comment_basic(self, comments_mixin):
        """Test edit_comment with basic data (Cloud → ADF via v3)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "This is an updated comment",
            "updated": "2024-01-01T12:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._put_api3 = Mock(return_value=mock_response)

        # Call the method
        result = comments_mixin.edit_comment("TEST-123", "10001", "Updated comment")

        # On Cloud, ADF goes through _put_api3
        comments_mixin._put_api3.assert_called_once()
        call_args = comments_mixin._put_api3.call_args
        assert call_args[0][0] == "issue/TEST-123/comment/10001"
        adf_body = call_args[0][1]["body"]
        assert isinstance(adf_body, dict)
        assert adf_body["version"] == 1
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["id"] == "10001"
        assert result["body"] == "This is an updated comment"
        assert result["updated"] == "2024-01-01 12:00:00+00:00"
        assert result["author"] == "John Doe"

    def test_edit_comment_with_markdown_conversion(self, comments_mixin):
        """Test edit_comment with markdown conversion (Cloud → ADF via v3)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "Updated content",
            "updated": "2024-01-01T12:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._put_api3 = Mock(return_value=mock_response)

        markdown_comment = "# Updated Heading\n\nThis is **updated** text."

        # Call the method
        result = comments_mixin.edit_comment("TEST-123", "10001", markdown_comment)

        # On Cloud, should produce ADF via v3 API
        call_args = comments_mixin._put_api3.call_args
        adf_body = call_args[0][1]["body"]
        assert isinstance(adf_body, dict)
        assert adf_body["version"] == 1
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["body"] == "Updated content"

    def test_edit_comment_with_empty_comment(self, comments_mixin):
        """Test edit_comment with an empty comment (Cloud → minimal ADF)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "",
            "updated": "2024-01-01T12:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._put_api3 = Mock(return_value=mock_response)

        # Call the method with empty comment
        result = comments_mixin.edit_comment("TEST-123", "10001", "")

        # On Cloud, empty string produces a minimal ADF dict via v3 API
        call_args = comments_mixin._put_api3.call_args
        adf_body = call_args[0][1]["body"]
        assert isinstance(adf_body, dict)
        assert adf_body["version"] == 1
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["body"] == ""

    def test_edit_comment_with_restricted_visibility(self, comments_mixin):
        """Test edit_comment with visibility set (Cloud → ADF via v3)."""
        # Setup mock response for v3 API path
        mock_response = {
            "id": "10001",
            "body": "This is an updated comment",
            "updated": "2024-01-01T12:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._put_api3 = Mock(return_value=mock_response)

        # Call the method
        result = comments_mixin.edit_comment(
            "TEST-123",
            "10001",
            "Updated comment",
            {"type": "group", "value": "restricted"},
        )

        # Verify ADF via v3 API with visibility
        call_args = comments_mixin._put_api3.call_args
        assert call_args[0][0] == "issue/TEST-123/comment/10001"
        payload = call_args[0][1]
        assert isinstance(payload["body"], dict)
        assert payload["body"]["version"] == 1
        assert payload["visibility"] == {"type": "group", "value": "restricted"}
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()
        assert result["id"] == "10001"
        assert result["body"] == "This is an updated comment"
        assert result["updated"] == "2024-01-01 12:00:00+00:00"
        assert result["author"] == "John Doe"

    def test_edit_comment_with_error(self, comments_mixin):
        """Test edit_comment with an error response."""
        # Setup mock to raise exception (Cloud uses _put_api3)
        comments_mixin._put_api3 = Mock(side_effect=Exception("API Error"))

        # Verify it raises the wrapped exception
        with pytest.raises(Exception, match="Error editing comment"):
            comments_mixin.edit_comment("TEST-123", "10001", "Updated comment")

    def test_markdown_to_jira_cloud(self, comments_mixin):
        """Test _markdown_to_jira returns ADF dict on Cloud."""
        result = comments_mixin._markdown_to_jira("Markdown text")
        # Cloud config → ADF dict
        assert isinstance(result, dict)
        assert result["version"] == 1
        assert result["type"] == "doc"
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()

    def test_markdown_to_jira_cloud_links_issue_keys(self, comments_mixin):
        """Cloud ADF links bare Jira issue keys to the configured Jira site."""
        result = comments_mixin._markdown_to_jira("Blocked by PROJ-123.")
        assert isinstance(result, dict)
        para = result["content"][0]
        link_node = next(n for n in para["content"] if n.get("text") == "PROJ-123")
        link_mark = next(m for m in link_node["marks"] if m["type"] == "link")
        assert (
            link_mark["attrs"]["href"] == "https://test.atlassian.net/browse/PROJ-123"
        )

    def test_markdown_to_jira_cloud_empty(self, comments_mixin):
        """Test _markdown_to_jira with empty text on Cloud returns ADF."""
        result = comments_mixin._markdown_to_jira("")
        assert isinstance(result, dict)
        assert result["version"] == 1
        comments_mixin.preprocessor.markdown_to_jira.assert_not_called()

    # --- Server/DC path tests ---

    @pytest.fixture
    def server_comments_mixin(self, jira_config_factory):
        """Create a CommentsMixin configured for Server/DC."""
        config = jira_config_factory(url="https://jira.example.com")
        mixin = CommentsMixin(config=config)
        mixin.jira = Mock()
        mixin.preprocessor = Mock()
        mixin.preprocessor.markdown_to_jira = Mock(return_value="h1. Hello")
        mixin._clean_text = Mock(side_effect=lambda x: x)
        return mixin

    def test_markdown_to_jira_server_returns_string(self, server_comments_mixin):
        """Server/DC path returns wiki markup string."""
        result = server_comments_mixin._markdown_to_jira("# Hello")
        assert isinstance(result, str)
        assert result == "h1. Hello"
        server_comments_mixin.preprocessor.markdown_to_jira.assert_called_once()

    def test_add_comment_server_sends_string(self, server_comments_mixin):
        """Server/DC add_comment sends wiki markup string to API."""
        server_comments_mixin.jira.issue_add_comment.return_value = {
            "id": "10001",
            "body": "h1. Hello",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "Test User"},
        }
        result = server_comments_mixin.add_comment("TEST-123", "# Hello")
        call_args = server_comments_mixin.jira.issue_add_comment.call_args
        comment_arg = call_args[0][1]
        assert isinstance(comment_arg, str)
        assert result["body"] == "h1. Hello"

    def test_edit_comment_server_sends_string(self, server_comments_mixin):
        """Server/DC edit_comment sends wiki markup string to API."""
        server_comments_mixin.jira.issue_edit_comment.return_value = {
            "id": "10001",
            "body": "h1. Updated",
            "updated": "2024-01-01T11:00:00.000+0000",
            "author": {"displayName": "Test User"},
        }
        server_comments_mixin.preprocessor.markdown_to_jira.return_value = "h1. Updated"
        result = server_comments_mixin.edit_comment("TEST-123", "10001", "# Updated")
        call_args = server_comments_mixin.jira.issue_edit_comment.call_args
        comment_arg = call_args[0][2]
        assert isinstance(comment_arg, str)
        assert result["body"] == "h1. Updated"

    # --- ServiceDesk API (internal/public comments) tests ---

    SERVICEDESK_COMMENT_RESPONSE = {
        "id": 10001,
        "body": "Test comment",
        "public": True,
        "created": {
            "iso8601": "2024-01-01T10:00:00.000+0000",
            "jira": "2024-01-01T10:00:00.000+0000",
            "friendly": "Today 10:00 AM",
            "epochMillis": 1704099600000,
        },
        "author": {
            "accountId": "test-id",
            "displayName": "Test User",
        },
    }

    def test_add_comment_servicedesk_public(self, comments_mixin):
        """public=True routes through ServiceDesk API."""
        response = {**self.SERVICEDESK_COMMENT_RESPONSE, "public": True}
        comments_mixin.jira.post.return_value = response

        result = comments_mixin.add_comment("TEST-123", "Test comment", public=True)

        comments_mixin.jira.post.assert_called_once()
        call_args = comments_mixin.jira.post.call_args
        assert "rest/servicedeskapi/request/TEST-123/comment" in str(call_args)
        assert call_args[1]["data"] == {
            "body": "Test comment",
            "public": True,
        }
        # Verify experimental header is included
        headers = call_args[1]["headers"]
        assert headers["X-ExperimentalApi"] == "opt-in"
        assert result["public"] is True
        assert result["id"] == "10001"
        assert result["author"] == "Test User"

    def test_add_comment_servicedesk_internal(self, comments_mixin):
        """public=False routes through ServiceDesk API as internal."""
        response = {**self.SERVICEDESK_COMMENT_RESPONSE, "public": False}
        comments_mixin.jira.post.return_value = response

        result = comments_mixin.add_comment("TEST-123", "Internal note", public=False)

        call_args = comments_mixin.jira.post.call_args
        assert call_args[1]["data"] == {
            "body": "Internal note",
            "public": False,
        }
        assert result["public"] is False

    def test_add_comment_servicedesk_cloud(self, comments_mixin):
        """public=True on Cloud uses ServiceDesk API, not ADF/v3."""
        response = {**self.SERVICEDESK_COMMENT_RESPONSE}
        comments_mixin.jira.post.return_value = response
        comments_mixin._post_api3 = Mock()

        comments_mixin.add_comment("TEST-123", "Test", public=True)

        # ServiceDesk path should use jira.post, NOT _post_api3
        comments_mixin.jira.post.assert_called_once()
        comments_mixin._post_api3.assert_not_called()

    def test_add_comment_servicedesk_403(self, comments_mixin):
        """public=True on non-JSM project gives clear 403 error."""
        comments_mixin.jira.post.side_effect = Exception("403 Client Error: Forbidden")

        with pytest.raises(Exception, match="not a JSM service desk issue"):
            comments_mixin.add_comment("TEST-123", "Test", public=True)

    def test_add_servicedesk_comment_404_is_strict(self, comments_mixin):
        """The ServiceDesk helper keeps raising its 404 error."""
        comments_mixin.jira.post.side_effect = Exception("404 Client Error: Not Found")

        with pytest.raises(Exception, match="not a JSM service desk issue"):
            comments_mixin._add_servicedesk_comment("TEST-123", "Test", public=True)

    def test_add_comment_servicedesk_failure_never_reaches_jira(self, comments_mixin):
        """A failed internal-comment request must not become an ordinary one.

        Falling through to the normal Jira comment path could publish the text to
        the customer portal, so the request has to fail instead.
        """
        comments_mixin.jira.post.side_effect = HTTPError(response=Mock(status_code=404))
        comments_mixin._post_api3 = Mock()
        comments_mixin.jira.issue_add_comment = Mock()

        with pytest.raises(Exception, match="ServiceDesk"):
            comments_mixin.add_comment("TEST-123", "Internal note", public=False)

        comments_mixin._post_api3.assert_not_called()
        comments_mixin.jira.issue_add_comment.assert_not_called()

    def test_add_comment_public_with_visibility_raises(self, comments_mixin):
        """public + visibility together raises ValueError."""
        with pytest.raises(ValueError, match="Cannot use both"):
            comments_mixin.add_comment(
                "TEST-123",
                "Test",
                visibility={"type": "group", "value": "jira-users"},
                public=True,
            )

    def test_add_comment_public_none_uses_jira_api(self, comments_mixin):
        """public=None (default) uses normal Jira API path."""
        mock_response = {
            "id": "10001",
            "body": "Normal comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        result = comments_mixin.add_comment("TEST-123", "Normal comment")

        # Should go through normal Jira path (ADF on Cloud)
        comments_mixin._post_api3.assert_called_once()
        # ServiceDesk post should NOT be called
        comments_mixin.jira.post.assert_not_called()
        assert result["id"] == "10001"


class TestInternalCommentPublicParam:
    """Regression tests for add_comment public parameter (internal comments).

    Regression for https://github.com/sooperset/mcp-atlassian/issues/716
    Feature was requested: make comment internal (public: false) via JSM API.
    Already implemented: add_comment(public=False) routes through
    _add_servicedesk_comment which posts to rest/servicedeskapi/request/.../comment.
    """

    SERVICEDESK_COMMENT_RESPONSE = {
        "id": 10001,
        "body": "Test comment",
        "public": True,
        "created": {
            "iso8601": "2024-01-01T10:00:00.000+0000",
            "jira": "2024-01-01T10:00:00.000+0000",
            "friendly": "Today 10:00 AM",
            "epochMillis": 1704099600000,
        },
        "author": {
            "accountId": "test-id",
            "displayName": "Test User",
        },
    }

    @pytest.fixture
    def comments_mixin(self, jira_client):
        """Create a CommentsMixin instance with mocked dependencies."""
        mixin = CommentsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        mixin.preprocessor = Mock()
        mixin.preprocessor.markdown_to_jira = Mock(
            return_value="*This* is _Jira_ formatted"
        )
        mixin._clean_text = Mock(side_effect=lambda x: x)
        return mixin

    def test_public_false_calls_servicedesk_comment(self, comments_mixin):
        """add_comment(public=False) routes through _add_servicedesk_comment."""
        captured: list[tuple] = []
        original = comments_mixin._add_servicedesk_comment

        def spy(*args, **kwargs):
            captured.append((args, kwargs))
            return original(*args, **kwargs)

        comments_mixin._add_servicedesk_comment = spy
        response = {**self.SERVICEDESK_COMMENT_RESPONSE, "public": False}
        comments_mixin.jira.post.return_value = response

        comments_mixin.add_comment("ISSUE-1", "Internal note", public=False)

        assert len(captured) == 1
        assert captured[0][0] == ("ISSUE-1", "Internal note", False)  # noqa: FBT003

    def test_public_true_calls_servicedesk_comment(self, comments_mixin):
        """add_comment(public=True) routes through _add_servicedesk_comment."""
        captured: list[tuple] = []
        original = comments_mixin._add_servicedesk_comment

        def spy(*args, **kwargs):
            captured.append((args, kwargs))
            return original(*args, **kwargs)

        comments_mixin._add_servicedesk_comment = spy
        response = {**self.SERVICEDESK_COMMENT_RESPONSE, "public": True}
        comments_mixin.jira.post.return_value = response

        comments_mixin.add_comment("ISSUE-1", "Customer reply", public=True)

        assert len(captured) == 1
        assert captured[0][0] == ("ISSUE-1", "Customer reply", True)  # noqa: FBT003

    def test_public_none_does_not_call_servicedesk_comment(self, comments_mixin):
        """add_comment(public=None default) does NOT call _add_servicedesk_comment."""
        captured: list[tuple] = []

        def spy(*args, **kwargs):
            captured.append((args, kwargs))

        comments_mixin._add_servicedesk_comment = spy
        mock_response = {
            "id": "10001",
            "body": "Normal comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "author": {"displayName": "John Doe"},
        }
        comments_mixin._post_api3 = Mock(return_value=mock_response)

        comments_mixin.add_comment("ISSUE-1", "text")

        assert len(captured) == 0


class TestInternalOnlyProjectsGuard:
    """Tests for the JIRA_INTERNAL_ONLY_PROJECTS server-side guard.

    Covers issue #1: add_comment must reject anything but an explicit
    public=False on a listed project, and edit_comment must reject edits
    to a currently-public comment on a listed project. The env var is
    opt-in: an unlisted project (or the default empty config used by the
    `comments_mixin`/`mixin` fixtures elsewhere in this file) must see
    zero behavior change.
    """

    @pytest.fixture
    def guarded_mixin(self, jira_config_factory):
        """CommentsMixin with 'CC' configured as an internal-only project."""
        config = jira_config_factory(internal_only_projects=frozenset({"CC"}))
        mixin = CommentsMixin(config=config)
        mixin.jira = Mock()
        mixin.jira.default_headers = {}
        mixin.preprocessor = Mock()
        mixin.preprocessor.markdown_to_jira = Mock(return_value="formatted")
        mixin._clean_text = Mock(side_effect=lambda x: x)
        return mixin

    # --- add_comment ---

    def test_add_comment_unlisted_project_unaffected(self, guarded_mixin):
        """A project not in JIRA_INTERNAL_ONLY_PROJECTS sees no behavior
        change: public=None (the API default, i.e. public) still goes
        through normally."""
        guarded_mixin._post_api3 = Mock(
            return_value={
                "id": "1",
                "body": "hi",
                "created": "2024-01-01T10:00:00.000+0000",
                "author": {"displayName": "A"},
            }
        )
        result = guarded_mixin.add_comment("TEST-123", "hi")
        guarded_mixin._post_api3.assert_called_once()
        guarded_mixin.jira.post.assert_not_called()
        assert result["id"] == "1"

    def test_add_comment_internal_only_rejects_public_true(self, guarded_mixin):
        """Listed project + public=True is rejected."""
        with pytest.raises(ValueError, match="internal-only"):
            guarded_mixin.add_comment("CC-1", "Client update", public=True)
        guarded_mixin.jira.post.assert_not_called()

    def test_add_comment_internal_only_rejects_public_absent(self, guarded_mixin):
        """Listed project + public omitted (defaults to public) is rejected."""
        with pytest.raises(ValueError, match="internal-only"):
            guarded_mixin.add_comment("CC-1", "Client update")
        guarded_mixin.jira.post.assert_not_called()

    def test_add_comment_internal_only_accepts_public_false(self, guarded_mixin):
        """Listed project + public=False passes through untouched."""
        guarded_mixin.jira.post.return_value = {
            "id": 1,
            "body": "Internal note",
            "public": False,
            "created": {"iso8601": "2024-01-01T10:00:00.000+0000"},
            "author": {"displayName": "A"},
        }
        result = guarded_mixin.add_comment("CC-1", "Internal note", public=False)
        guarded_mixin.jira.post.assert_called_once()
        assert result["public"] is False

    @pytest.mark.parametrize("status_code", [403, 404, 500])
    def test_add_comment_internal_only_failure_never_reaches_jira(
        self, guarded_mixin, status_code
    ):
        """An internal comment must never be downgraded to an ordinary one.

        Whatever the ServiceDesk API answers, falling through to the normal Jira
        comment path could publish the text to the customer portal, so the
        request has to fail instead.
        """
        guarded_mixin.jira.post.side_effect = HTTPError(
            response=Mock(status_code=status_code)
        )
        guarded_mixin._post_api3 = Mock()
        guarded_mixin.jira.issue_add_comment = Mock()

        with pytest.raises(Exception, match="ServiceDesk"):
            guarded_mixin.add_comment("CC-1", "Internal note", public=False)

        guarded_mixin.jira.post.assert_called_once()
        guarded_mixin._post_api3.assert_not_called()
        guarded_mixin.jira.issue_add_comment.assert_not_called()

    def test_add_comment_internal_only_case_insensitive_project_match(
        self, guarded_mixin
    ):
        """Project key matching is case-insensitive on both sides."""
        with pytest.raises(ValueError, match="internal-only"):
            guarded_mixin.add_comment("cc-1", "Client update", public=True)

    @pytest.mark.parametrize(
        "padded_key",
        [
            " CC-1",  # leading space
            "\tCC-1",  # leading tab
            "CC -1",  # space before the dash
            " cc-1 ",  # padded + lowercase
            "C\u200bC-1",  # zero-width space inside the project key
            "\ufeffCC-1",  # BOM before the project key
        ],
    )
    def test_add_comment_internal_only_whitespace_padded_key_still_guarded(
        self, guarded_mixin, padded_key
    ):
        """Whitespace-padded issue keys must NOT bypass the guard.

        The guard normalizes its own input: config keys are stripped at
        parse time, and the issue key is normalized (around the whole key
        AND around the extracted project segment) at check time. Pins
        the whitespace and invisible-character bypass classes.
        """
        with pytest.raises(ValueError, match="internal-only"):
            guarded_mixin.add_comment(padded_key, "Client update", public=True)

    def test_edit_comment_internal_only_whitespace_padded_key_still_guarded(
        self, guarded_mixin
    ):
        """The edit guard applies the same issue-key normalization."""
        guarded_mixin.jira.get.return_value = {"id": "5", "public": True}
        with pytest.raises(ValueError, match="PUBLIC"):
            guarded_mixin.edit_comment(" CC-1", "5", "Updated text")

    # --- edit_comment ---

    def test_edit_comment_unlisted_project_skips_visibility_fetch(self, guarded_mixin):
        """An unlisted project never pays the extra ServiceDesk lookup."""
        guarded_mixin._put_api3 = Mock(
            return_value={
                "id": "1",
                "body": "updated",
                "updated": "2024-01-01T10:00:00.000+0000",
                "author": {"displayName": "A"},
            }
        )
        result = guarded_mixin.edit_comment("TEST-1", "1", "updated")
        guarded_mixin.jira.get.assert_not_called()
        guarded_mixin._put_api3.assert_called_once()
        assert result["id"] == "1"

    def test_edit_comment_internal_only_rejects_public_comment(self, guarded_mixin):
        """Listed project + currently-public target comment is rejected."""
        guarded_mixin.jira.get.return_value = {"id": "5", "public": True}
        with pytest.raises(ValueError, match="PUBLIC"):
            guarded_mixin.edit_comment("CC-1", "5", "Updated text")
        guarded_mixin.jira.get.assert_called_once()
        call_args = guarded_mixin.jira.get.call_args
        assert "rest/servicedeskapi/request/CC-1/comment/5" in str(call_args)

    def test_edit_comment_internal_only_accepts_internal_comment(self, guarded_mixin):
        """Listed project + currently-internal target comment passes through."""
        guarded_mixin.jira.get.return_value = {"id": "5", "public": False}
        guarded_mixin._put_api3 = Mock(
            return_value={
                "id": "5",
                "body": "updated",
                "updated": "2024-01-01T10:00:00.000+0000",
                "author": {"displayName": "A"},
            }
        )
        result = guarded_mixin.edit_comment("CC-1", "5", "Updated text")
        guarded_mixin.jira.get.assert_called_once()
        guarded_mixin._put_api3.assert_called_once()
        assert result["id"] == "5"

    def test_edit_comment_internal_only_visibility_lookup_fails_closed(
        self, guarded_mixin
    ):
        """If the ServiceDesk visibility lookup errors, the edit is refused
        rather than silently allowed through (fail closed)."""
        guarded_mixin.jira.get.side_effect = Exception("500 Server Error")
        with pytest.raises(Exception, match="Could not verify"):
            guarded_mixin.edit_comment("CC-1", "5", "Updated text")

    @pytest.mark.parametrize("public", [None, 0, 1, "false", []])
    def test_edit_comment_internal_only_non_boolean_visibility_fails_closed(
        self, guarded_mixin, public
    ):
        """Only a real boolean false proves that a comment is internal."""
        response = {"id": "5"}
        if public is not None:
            response["public"] = public
        guarded_mixin.jira.get.return_value = response
        with pytest.raises(ValueError, match="PUBLIC"):
            guarded_mixin.edit_comment("CC-1", "5", "Updated text")


def _strong_text_nodes(adf: dict) -> list[str]:
    """Collect the text of every node carrying a `strong` mark in an ADF doc."""
    out: list[str] = []

    def walk(node: dict) -> None:
        marks = [m.get("type") for m in node.get("marks", [])]
        if node.get("type") == "text" and "strong" in marks:
            out.append(node.get("text", ""))
        for child in node.get("content", []):
            walk(child)

    walk(adf)
    return out


def _node_types(adf: dict) -> list[str]:
    """Flatten all node `type` values in an ADF doc (depth-first)."""
    out: list[str] = []

    def walk(node: dict) -> None:
        if "type" in node:
            out.append(node["type"])
        for child in node.get("content", []):
            walk(child)

    walk(adf)
    return out


class TestAddEditConversionParity:
    """Regression guard: add_comment must not double-convert markdown.

    The bug: the ADD path applied an extra markdown→jira-wiki-ish
    transformation before markdown_to_adf, so `**bold**` reached the
    converter as `****bold****` (stray `*` text nodes around the strong
    mark) and `## Heading` was turned into a numbered/ordered list.
    The EDIT path never did this. These tests pin add_comment's posted
    body to be byte-identical to edit_comment's for the same markdown,
    and assert the conversion happens exactly once with the output
    posted unmodified.
    """

    @pytest.fixture
    def mixin(self, jira_client):
        mixin = CommentsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        mixin.preprocessor = Mock()
        mixin.preprocessor.markdown_to_jira = Mock(
            return_value="should-not-be-used-on-cloud"
        )
        mixin._clean_text = Mock(side_effect=lambda x: x)
        return mixin

    MARKDOWN = "## Heading\n\nThis is **bold** and `code_x` text.\n\n- one\n- two"

    def _add_body(self, mixin) -> dict:
        mixin._post_api3 = Mock(
            return_value={
                "id": "1",
                "body": {},
                "created": "2024-01-01T10:00:00.000+0000",
                "author": {"displayName": "A"},
            }
        )
        mixin.add_comment("TEST-1", self.MARKDOWN)
        return mixin._post_api3.call_args[0][1]["body"]

    def _edit_body(self, mixin) -> dict:
        mixin._put_api3 = Mock(
            return_value={
                "id": "1",
                "body": {},
                "updated": "2024-01-01T10:00:00.000+0000",
                "author": {"displayName": "A"},
            }
        )
        mixin.edit_comment("TEST-1", "1", self.MARKDOWN)
        return mixin._put_api3.call_args[0][1]["body"]

    def test_add_body_equals_edit_body(self, mixin):
        """add_comment and edit_comment produce identical ADF for same markdown."""
        assert self._add_body(mixin) == self._edit_body(mixin)

    def test_add_body_is_clean_adf(self, mixin):
        """The ADD body has clean marks: no stray '*', heading lvl2, code mark."""
        body = self._add_body(mixin)
        # bold renders as a strong-marked node with text exactly "bold"
        # (not "*bold*" / "**bold**" which is the double-conversion signature)
        assert _strong_text_nodes(body) == ["bold"]
        types = _node_types(body)
        # "## Heading" is a heading, NOT an ordered list
        assert "heading" in types
        assert "orderedList" not in types
        # heading level is 2
        heading = next(n for n in body["content"] if n.get("type") == "heading")
        assert heading["attrs"]["level"] == 2
        # `code_x` carries a code mark
        assert "code" in [m for n in _node_types_with_marks(body) for m in n]

    def test_add_calls_markdown_to_jira_once_and_posts_unmodified(self, mixin):
        """_markdown_to_jira is invoked exactly once; its output is posted as-is."""
        sentinel = {"version": 1, "type": "doc", "content": [{"type": "x"}]}
        mixin._markdown_to_jira = Mock(return_value=sentinel)
        mixin._post_api3 = Mock(
            return_value={
                "id": "1",
                "body": {},
                "created": "2024-01-01T10:00:00.000+0000",
                "author": {"displayName": "A"},
            }
        )
        mixin.add_comment("TEST-1", self.MARKDOWN)
        mixin._markdown_to_jira.assert_called_once_with(self.MARKDOWN)
        # posted body is the exact object returned by _markdown_to_jira
        assert mixin._post_api3.call_args[0][1]["body"] is sentinel
        # and the Cloud ADD path must not touch the wiki preprocessor
        mixin.preprocessor.markdown_to_jira.assert_not_called()


def _node_types_with_marks(adf: dict) -> list[list[str]]:
    """For every node, return its list of mark types (for code-mark checks)."""
    out: list[list[str]] = []

    def walk(node: dict) -> None:
        out.append([m.get("type") for m in node.get("marks", [])])
        for child in node.get("content", []):
            walk(child)

    walk(adf)
    return out
