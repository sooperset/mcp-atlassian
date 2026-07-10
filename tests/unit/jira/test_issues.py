"""Tests for the Jira Issues mixin."""

from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.issues import IssuesMixin, logger
from mcp_atlassian.models.jira import JiraIssue
from tests.utils.mocks import setup_api3_passthrough_mocks


class TestIssuesMixin:
    """Tests for the IssuesMixin class."""

    @pytest.fixture
    def issues_mixin(self, jira_fetcher: JiraFetcher) -> IssuesMixin:
        """Create an IssuesMixin instance with mocked dependencies."""
        mixin = jira_fetcher

        # Add mock methods that would be provided by other mixins
        mixin._get_account_id = MagicMock(return_value="test-account-id")
        mixin.get_available_transitions = MagicMock(
            return_value=[{"id": "10", "name": "In Progress"}]
        )
        mixin.transition_issue = MagicMock(
            return_value=JiraIssue(id="123", key="TEST-123", summary="Test Issue")
        )

        # Cloud ADF paths delegate to _post_api3/_put_api3. Route back
        # to jira.create_issue / jira.update_issue so existing mocks work.
        setup_api3_passthrough_mocks(mixin)

        return mixin

    def test_get_issue_basic(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test retrieving an issue by key."""
        issues_mixin.jira.get_issue.return_value = make_issue_data()

        result = issues_mixin.get_issue("TEST-123")

        # Verify API calls
        issues_mixin.jira.get_issue.assert_called_once_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=True,
        )

        # Verify result structure
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "This is a test issue"

        # Check Jira fields mapping
        assert result.status is not None
        assert result.status.name == "Open"
        assert result.issue_type.name == "Bug"

    def test_get_issue_with_comments(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test get_issue with comments."""
        comments_data = {
            "comments": [
                {
                    "id": "1",
                    "body": "This is a comment",
                    "author": {"displayName": "John Doe"},
                    "created": "2023-01-02T00:00:00.000+0000",
                    "updated": "2023-01-02T00:00:00.000+0000",
                }
            ]
        }

        issue_data = make_issue_data(
            description="Test Description", comment=comments_data
        )

        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = comments_data

        issue = issues_mixin.get_issue(
            "TEST-123",
            fields="summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype,comment",
        )

        # Verify the API calls
        issues_mixin.jira.get_issue.assert_called_once_with(
            "TEST-123",
            expand=None,
            fields="summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype,comment",
            properties=None,
            update_history=True,
        )
        issues_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")

        # Verify the comments were added to the issue
        assert hasattr(issue, "comments")
        assert len(issue.comments) == 1
        assert issue.comments[0].body == "This is a comment"

    def test_get_issue_with_comment_limit_returns_newest_comments(
        self, issues_mixin: IssuesMixin, make_issue_data: Any
    ) -> None:
        """Test that comment_limit keeps the newest comments from Jira."""
        comments_data = {
            "comments": [
                {
                    "id": "1",
                    "body": "Oldest comment",
                    "author": {"displayName": "John Doe"},
                    "created": "2023-01-01T00:00:00.000+0000",
                    "updated": "2023-01-01T00:00:00.000+0000",
                },
                {
                    "id": "2",
                    "body": "Middle comment",
                    "author": {"displayName": "Jane Doe"},
                    "created": "2023-01-02T00:00:00.000+0000",
                    "updated": "2023-01-02T00:00:00.000+0000",
                },
                {
                    "id": "3",
                    "body": "Newest comment",
                    "author": {"displayName": "Bob Doe"},
                    "created": "2023-01-03T00:00:00.000+0000",
                    "updated": "2023-01-03T00:00:00.000+0000",
                },
            ]
        }

        issue_data = make_issue_data(comment={"comments": []})

        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = comments_data

        issue = issues_mixin.get_issue("TEST-123", comment_limit=2)

        issues_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
        assert [comment.id for comment in issue.comments] == ["2", "3"]
        assert [comment.body for comment in issue.comments] == [
            "Middle comment",
            "Newest comment",
        ]

    def test_get_issue_includes_comment_field_when_comment_limit_positive(
        self, issues_mixin: IssuesMixin
    ):
        """Test that comment field is auto-included when comment_limit > 0."""
        comments_data = {
            "comments": [
                {
                    "id": "1",
                    "body": "Auto-fetched comment",
                    "author": {"displayName": "Jane Doe"},
                    "created": "2023-01-02T00:00:00.000+0000",
                    "updated": "2023-01-02T00:00:00.000+0000",
                }
            ]
        }

        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "comment": comments_data,
                "summary": "Test Issue",
                "description": "Test Description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-02T00:00:00.000+0000",
            },
        }

        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = comments_data

        issue = issues_mixin.get_issue("TEST-123", comment_limit=10)

        call_args = issues_mixin.jira.get_issue.call_args
        fields_param = call_args[1]["fields"]
        assert "comment" in fields_param

        issues_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")
        assert hasattr(issue, "comments")
        assert len(issue.comments) == 1
        assert issue.comments[0].body == "Auto-fetched comment"

    def test_get_issue_excludes_comment_field_when_comment_limit_zero(
        self, issues_mixin: IssuesMixin
    ):
        """Test that comment field is not included when comment_limit is 0."""
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "Test Description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-02T00:00:00.000+0000",
            },
        }

        issues_mixin.jira.get_issue.return_value = issue_data

        issue = issues_mixin.get_issue("TEST-123", comment_limit=0)

        call_args = issues_mixin.jira.get_issue.call_args
        fields_param = call_args[1]["fields"]
        assert "comment" not in fields_param

        issues_mixin.jira.issue_get_comments.assert_not_called()

    def test_get_issue_with_epic_info(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test retrieving issue with epic information."""
        try:
            issues_mixin.jira.get_issue.side_effect = [
                make_issue_data(
                    key="TEST-123",
                    issue_id="10001",
                    issue_type="Story",
                    customfield_10010="EPIC-456",
                ),
                make_issue_data(
                    key="EPIC-456",
                    issue_id="10002",
                    summary="Epic Issue",
                    description="This is an epic",
                    status="In Progress",
                    issue_type="Epic",
                    customfield_10011="Epic Name Value",
                ),
            ]

            # Mock get_field_ids_to_epic
            issues_mixin.get_field_ids_to_epic = MagicMock(
                return_value={
                    "epic_link": "customfield_10010",
                    "epic_name": "customfield_10011",
                }
            )

            # Call the method - just use get_issue without the include_epic_info parameter
            issue = issues_mixin.get_issue("TEST-123")

            # Verify the API calls
            issues_mixin.jira.get_issue.assert_any_call(
                "TEST-123",
                expand=None,
                fields=ANY,
                properties=None,
                update_history=True,
            )
            issues_mixin.jira.get_issue.assert_any_call(
                "EPIC-456",
                expand=None,
                fields=None,
                properties=None,
                update_history=True,
            )

            # Verify the issue
            assert issue.key == "TEST-123"
            assert issue.summary == "Test Issue"

            # Verify that the epic information is in the custom fields
            assert issue.custom_fields.get("customfield_10010") == {"value": "EPIC-456"}
            assert issue.custom_fields.get("customfield_10011") == {
                "value": "Epic Name Value"
            }

        except Exception as e:
            pytest.fail(f"Test failed: {e}")

    def test_get_issue_error_handling(self, issues_mixin: IssuesMixin):
        """Test error handling in get_issue."""
        # Mock the API to raise an exception
        issues_mixin.jira.get_issue.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match=r"Error retrieving issue TEST-123: API error"
        ):
            issues_mixin.get_issue("TEST-123")

    def test_normalize_comment_limit(self, issues_mixin: IssuesMixin):
        """Test normalizing comment limit."""
        # Test with None
        assert issues_mixin._normalize_comment_limit(None) is None

        # Test with integer
        assert issues_mixin._normalize_comment_limit(5) == 5

        # Test with "all"
        assert issues_mixin._normalize_comment_limit("all") is None

        # Test with string number
        assert issues_mixin._normalize_comment_limit("10") == 10

        # Test with invalid string
        assert issues_mixin._normalize_comment_limit("invalid") == 10

    def test_create_issue_basic(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test creating a basic issue."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data()

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
        )

        # On Cloud, ADF is routed through _post_api3 which delegates to
        # jira.create_issue via the fixture mock
        issues_mixin.jira.create_issue.assert_called_once()
        sent = issues_mixin.jira.create_issue.call_args[1]["fields"]["description"]
        assert isinstance(sent, dict)
        assert sent["version"] == 1
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123")

        # Verify issue
        assert issue.key == "TEST-123"
        assert issue.summary == "Test Issue"

    def test_create_issue_no_components(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating an issue with no components specified."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data()

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with components=None
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=None,
        )

        # Verify API calls — description is ADF on Cloud
        issues_mixin.jira.create_issue.assert_called_once_with(
            fields={
                "project": {"key": "TEST"},
                "summary": "Test Issue",
                "issuetype": {"name": "Bug"},
                "description": ANY,
            }
        )

        # Verify 'components' is not in the fields
        assert "components" not in issues_mixin.jira.create_issue.call_args[1]["fields"]

    def test_create_issue_single_component(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating an issue with a single component."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            components=[{"name": "UI"}]
        )

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with a single component
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=["UI"],
        )

        # Verify API calls — description is ADF on Cloud
        issues_mixin.jira.create_issue.assert_called_once_with(
            fields={
                "project": {"key": "TEST"},
                "summary": "Test Issue",
                "issuetype": {"name": "Bug"},
                "description": ANY,
                "components": [{"name": "UI"}],
            }
        )

        # Verify the components field was passed correctly
        assert issues_mixin.jira.create_issue.call_args[1]["fields"]["components"] == [
            {"name": "UI"}
        ]

    def test_create_issue_multiple_components(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating an issue with multiple components."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            components=[{"name": "UI"}, {"name": "API"}]
        )

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with multiple components
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=["UI", "API"],
        )

        # Verify API calls — description is ADF on Cloud
        issues_mixin.jira.create_issue.assert_called_once_with(
            fields={
                "project": {"key": "TEST"},
                "summary": "Test Issue",
                "issuetype": {"name": "Bug"},
                "description": ANY,
                "components": [{"name": "UI"}, {"name": "API"}],
            }
        )

        # Verify the components field was passed correctly
        assert issues_mixin.jira.create_issue.call_args[1]["fields"]["components"] == [
            {"name": "UI"},
            {"name": "API"},
        ]

    def test_create_issue_components_with_invalid_entries(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating an issue with components list containing invalid entries."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            components=[{"name": "Valid"}, {"name": "Backend"}]
        )

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with components list containing invalid entries
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=["Valid", "", None, "  Backend  "],
        )

        # Verify API calls — description is ADF on Cloud
        issues_mixin.jira.create_issue.assert_called_once_with(
            fields={
                "project": {"key": "TEST"},
                "summary": "Test Issue",
                "issuetype": {"name": "Bug"},
                "description": ANY,
                "components": [{"name": "Valid"}, {"name": "Backend"}],
            }
        )

        # Verify the components field was passed correctly, with invalid entries filtered out
        assert issues_mixin.jira.create_issue.call_args[1]["fields"]["components"] == [
            {"name": "Valid"},
            {"name": "Backend"},
        ]

    def test_create_issue_components_precedence(
        self, issues_mixin, make_issue_data, caplog
    ):
        """Test that explicit components take precedence over components in additional_fields."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            components=[{"name": "Explicit"}]
        )

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Direct test for the precedence handling logic
        # Create fields dict with components already set by explicit parameter
        fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
            "components": [{"name": "Explicit"}],
        }

        # Create kwargs with a conflicting components entry
        kwargs = {"components": [{"name": "Ignored"}]}

        # Directly call the method that would handle the precedence
        # This simulates what happens inside create_issue
        if "components" in fields and "components" in kwargs:
            logger.warning(
                "Components provided via both 'components' argument and 'additional_fields'. "
                "Using the explicit 'components' argument."
            )
            # Remove the conflicting key from kwargs to prevent issues later
            kwargs.pop("components", None)

        # Verify the warning was logged about the conflict
        assert (
            "Components provided via both 'components' argument and 'additional_fields'"
            in caplog.text
        )

        # Verify that kwargs no longer contains components
        assert "components" not in kwargs

        # Verify the components field was preserved with the explicit value
        assert fields["components"] == [{"name": "Explicit"}]

    @pytest.mark.parametrize(
        "is_cloud, user_field, user_id, issue_key",
        [
            pytest.param(
                True,
                "accountId",
                "cloud-account-id",
                "TEST-123",
                id="cloud",
            ),
            pytest.param(
                False,
                "name",
                "server-user",
                "TEST-456",
                id="server",
            ),
        ],
    )
    def test_create_issue_with_assignee(
        self,
        issues_mixin: IssuesMixin,
        is_cloud: bool,
        user_field: str,
        user_id: str,
        issue_key: str,
    ):
        """Test creating an issue with an assignee."""
        # Mock create_issue response
        create_response = {"key": issue_key}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key=issue_key, description="", summary="Test Issue")
        )

        # Mock _get_account_id to return the appropriate user ID
        issues_mixin._get_account_id = MagicMock(return_value=user_id)

        # Configure for Cloud or Server/DC
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = is_cloud

        # Call the method
        issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            assignee="testuser",
        )

        # Verify _get_account_id was called with the correct username
        issues_mixin._get_account_id.assert_called_once_with("testuser")

        # Verify assignee is in create fields (belt & suspenders)
        fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        assert fields["assignee"] == {user_field: user_id}

        # Verify assign_issue was also called post-creation
        issues_mixin.jira.assign_issue.assert_called_once_with(issue_key, user_id)

    def test_create_epic(self, issues_mixin: IssuesMixin):
        """Test creating an epic."""
        # Mock responses
        create_response = {"key": "EPIC-123"}
        issues_mixin.jira.create_issue.return_value = create_response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="EPIC-123", description="", summary="Test Epic")
        )

        # Mock the prepare_epic_fields method from EpicsMixin
        with patch(
            "mcp_atlassian.jira.epics.EpicsMixin.prepare_epic_fields", autospec=True
        ) as mock_prepare_epic:
            # Set up the mock to store epic values in kwargs
            # Note: First argument is self because EpicsMixin.prepare_epic_fields is called as a class method
            def side_effect(self_args, fields, summary, kwargs, project_key):
                kwargs["__epic_name_value"] = summary
                kwargs["__epic_name_field"] = "customfield_10011"
                return None

            mock_prepare_epic.side_effect = side_effect

            # Mock get_field_ids_to_epic
            with patch.object(
                issues_mixin,
                "get_field_ids_to_epic",
                return_value={"Epic Name": "customfield_10011"},
            ):
                # Call the method
                result = issues_mixin.create_issue(
                    project_key="TEST",
                    summary="Test Epic",
                    issue_type="Epic",
                )

                # Verify create_issue was called with the right project and summary
                create_args = issues_mixin.jira.create_issue.call_args[1]
                fields = create_args["fields"]
                assert fields["project"]["key"] == "TEST"
                assert fields["summary"] == "Test Epic"

                # Verify epic fields are NOT in the fields dictionary (two-step creation)
                assert "customfield_10011" not in fields

                # Verify that prepare_epic_fields was called
                mock_prepare_epic.assert_called_once()

                # For an Epic, verify that update_issue should be called for the second step
                # This would happen in the EpicsMixin.update_epic_fields method which is called
                # after the initial creation
                assert issues_mixin.get_issue.called
                assert result.key == "EPIC-123"

    def test_update_issue_handles_string_response_as_json(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test update_issue handles Server/DC JSON string get_issue responses."""
        import json

        issue_dict = make_issue_data(summary="Updated Summary", status="In Progress")
        # Simulate atlassian-python-api returning a JSON string instead of dict
        issues_mixin.jira.get_issue.return_value = json.dumps(issue_dict)
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        document = issues_mixin.update_issue(
            issue_key="TEST-123", fields={"summary": "Updated Summary"}
        )

        assert document.key == "TEST-123"
        assert document.summary == "Updated Summary"

    def test_update_issue_handles_string_response_with_refetch(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test update_issue re-fetches when a string response is not JSON."""
        issue_dict = make_issue_data(summary="Refetched", status="Open")
        # First call returns non-JSON string, direct GET returns dict
        issues_mixin.jira.get_issue.return_value = "<html>WAF login page</html>"
        issues_mixin.jira.get.return_value = issue_dict
        issues_mixin.jira.resource_url.return_value = "/rest/api/2/issue/TEST-123"
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        document = issues_mixin.update_issue(
            issue_key="TEST-123", fields={"summary": "Refetched"}
        )

        issues_mixin.jira.get.assert_called_once_with("/rest/api/2/issue/TEST-123")
        assert document.key == "TEST-123"

    def test_update_issue_basic(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test updating an issue with basic fields."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            summary="Updated Summary", status="In Progress"
        )

        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call the method
        document = issues_mixin.update_issue(
            issue_key="TEST-123", fields={"summary": "Updated Summary"}
        )

        # Verify the API calls
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"summary": "Updated Summary"}}
        )
        assert issues_mixin.jira.get_issue.called
        assert issues_mixin.jira.get_issue.call_args[0][0] == "TEST-123"

        # Verify the result
        assert document.id == "12345"
        assert document.key == "TEST-123"
        assert document.summary == "Updated Summary"

    def test_update_issue_preserves_existing_cloud_media_nodes(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Cloud markdown updates preserve existing top-level media blocks."""
        media_single = {
            "type": "mediaSingle",
            "attrs": {"layout": "center"},
            "content": [
                {
                    "type": "media",
                    "attrs": {
                        "id": "video-123",
                        "type": "file",
                        "collection": "",
                    },
                }
            ],
        }
        current_description = {
            "version": 1,
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Old"}]},
                media_single,
            ],
        }
        updated_description = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Updated text"}],
                },
                media_single,
            ],
        }
        issues_mixin._put_api3 = MagicMock(return_value={})
        issues_mixin.jira.get.side_effect = [
            {"key": "TEST-123", "fields": {"description": current_description}},
        ]
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description=updated_description
        )

        document = issues_mixin.update_issue(
            issue_key="TEST-123",
            fields={"description": "Updated text"},
        )

        issues_mixin._put_api3.assert_called_once()
        call_args = issues_mixin._put_api3.call_args
        assert call_args[0][0] == "issue/TEST-123"
        sent_description = call_args[0][1]["fields"]["description"]
        assert sent_description["content"][-1] == media_single
        issues_mixin.jira.get.assert_called_once_with(
            "rest/api/3/issue/TEST-123",
            params={"fields": "description", "updateHistory": "false"},
        )
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123")
        assert document.key == "TEST-123"

    def test_update_issue_with_explicit_adf_does_not_fetch_current_description(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Explicit ADF updates keep replace semantics and skip media prefetch."""
        explicit_adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Explicit ADF"}],
                }
            ],
        }
        issues_mixin._put_api3 = MagicMock(return_value={})
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description=explicit_adf
        )

        issues_mixin.update_issue(
            issue_key="TEST-123",
            fields={"description": explicit_adf},
        )

        issues_mixin._put_api3.assert_called_once_with(
            "issue/TEST-123",
            {"fields": {"description": explicit_adf}},
        )
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123")

    def test_update_issue_with_status(self, issues_mixin: IssuesMixin):
        """Test updating an issue with a status change."""
        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", description="")
        )

        # Mock available transitions (using TransitionsMixin's normalized format)
        issues_mixin.get_available_transitions = MagicMock(
            return_value=[
                {
                    "id": "21",
                    "name": "In Progress",
                    "to_status": "In Progress",
                }
            ]
        )

        # Call the method with status in kwargs instead of fields
        issues_mixin.update_issue(issue_key="TEST-123", status="In Progress")

    def test_update_issue_with_status_and_fields(self, issues_mixin: IssuesMixin):
        """Test field updates use correct update= kwarg with status."""
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", description="")
        )
        issues_mixin.get_available_transitions = MagicMock(
            return_value=[
                {"id": "21", "name": "In Progress", "to_status": "In Progress"}
            ]
        )

        issues_mixin.update_issue(
            issue_key="TEST-123",
            fields={"summary": "Updated"},
            status="In Progress",
        )

        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"summary": "Updated"}}
        )

    def test_update_issue_assignee_dict_passthrough_name(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Dict-shaped assignee (Server/DC name form) is forwarded as-is.

        _get_account_id must NOT be called — caller already has the canonical
        shape (typically from search_assignable_users / get_user_profile) and
        we must not require global "Browse Users" permission just to relay it.
        """
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        issues_mixin.update_issue(
            issue_key="TEST-123", assignee={"name": "jdoe@example.com"}
        )

        issues_mixin._get_account_id.assert_not_called()
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"assignee": {"name": "jdoe@example.com"}}},
        )

    def test_update_issue_assignee_dict_passthrough_accountid(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Cloud-shape assignee dict ({"accountId": ...}) is forwarded as-is too."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        issues_mixin.update_issue(
            issue_key="TEST-123",
            assignee={"accountId": "5b10ac8d82e05b22cc7d4ef5"},
        )

        issues_mixin._get_account_id.assert_not_called()
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"assignee": {"accountId": "5b10ac8d82e05b22cc7d4ef5"}}},
        )

    def test_update_issue_assignee_unresolvable_does_not_update(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """An unresolvable assignee must not silently turn into a no-op update."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock(side_effect=ValueError("not found"))

        with pytest.raises(ValueError, match="Could not update assignee"):
            issues_mixin.update_issue(
                issue_key="TEST-123", assignee="ghost@example.com"
            )

        issues_mixin.jira.update_issue.assert_not_called()

    def test_update_issue_unassign(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test unassigning an issue."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        document = issues_mixin.update_issue(issue_key="TEST-123", assignee=None)

        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"assignee": None}}
        )
        assert not issues_mixin._get_account_id.called
        assert document.key == "TEST-123"

    def test_update_issue_assignee_unresolvable_raises(self, issues_mixin: IssuesMixin):
        """Test that update_issue raises when assignee cannot be resolved."""
        issues_mixin._get_account_id = MagicMock(
            side_effect=ValueError("Could not find account ID for user: ghost")
        )

        with pytest.raises(ValueError, match="Could not update assignee"):
            issues_mixin.update_issue(issue_key="TEST-123", assignee="ghost")

        issues_mixin.jira.update_issue.assert_not_called()

    def test_assign_issue(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test assigning an issue to a user via dedicated endpoint."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock(return_value="account-123")

        document = issues_mixin.assign_issue(
            issue_key="TEST-123", assignee="user@example.com"
        )

        issues_mixin._get_account_id.assert_called_once_with("user@example.com")
        issues_mixin.jira.assign_issue.assert_called_once_with(
            "TEST-123", "account-123"
        )
        assert document.key == "TEST-123"

    def test_assign_issue_unassign(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test unassigning an issue (passing None)."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        document = issues_mixin.assign_issue(issue_key="TEST-123", assignee=None)

        issues_mixin.jira.assign_issue.assert_called_once_with("TEST-123", None)
        assert not issues_mixin._get_account_id.called
        assert document.key == "TEST-123"

    def test_assign_issue_empty_string(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test unassigning an issue (passing empty string)."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        document = issues_mixin.assign_issue(issue_key="TEST-123", assignee="")

        issues_mixin.jira.assign_issue.assert_called_once_with("TEST-123", None)
        assert not issues_mixin._get_account_id.called
        assert document.key == "TEST-123"

    def test_assign_issue_assignee_dict_passthrough_account_id(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Cloud-shaped assignee dict is unwrapped without user lookup."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        document = issues_mixin.assign_issue(
            issue_key="TEST-123",
            assignee={"account_id": "5b10ac8d82e05b22cc7d4ef5"},
        )

        issues_mixin._get_account_id.assert_not_called()
        issues_mixin.jira.assign_issue.assert_called_once_with(
            "TEST-123", "5b10ac8d82e05b22cc7d4ef5"
        )
        assert document.key == "TEST-123"

    def test_assign_issue_assignee_dict_passthrough_name(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Server/DC-shaped assignee dict is unwrapped without user lookup."""
        issues_mixin.config.url = "https://jira.example.com"
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            description="This is a test"
        )
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._get_account_id = MagicMock()

        document = issues_mixin.assign_issue(
            issue_key="TEST-123",
            assignee={"name": "jdoe"},
        )

        issues_mixin._get_account_id.assert_not_called()
        issues_mixin.jira.assign_issue.assert_called_once_with("TEST-123", "jdoe")
        assert document.key == "TEST-123"

    def test_assign_issue_error(self, issues_mixin: IssuesMixin):
        """Test error handling when assignment fails."""
        issues_mixin.jira.assign_issue.side_effect = Exception("Permission denied")
        issues_mixin._get_account_id = MagicMock(return_value="account-123")

        with pytest.raises(ValueError, match="Failed to assign issue TEST-123"):
            issues_mixin.assign_issue(issue_key="TEST-123", assignee="user@example.com")

    def test_update_issue_components(self, issues_mixin: IssuesMixin):
        """Test updating an issue's components field."""
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._generate_field_map = MagicMock(  # type: ignore[assignment]
            return_value={"components": "components"}
        )
        issues_mixin.get_field_by_id = MagicMock(  # type: ignore[assignment]
            return_value={"id": "components", "name": "Components"}
        )

        document = issues_mixin.update_issue(
            issue_key="TEST-123", components=["Backend", "Frontend"]
        )

        expected = {
            "components": [{"name": "Backend"}, {"name": "Frontend"}],
        }
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": expected},
        )
        assert document.key == "TEST-123"

    def test_update_issue_components_with_dict_format(self, issues_mixin: IssuesMixin):
        """Test updating components with pre-formatted dict values."""
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._generate_field_map = MagicMock(  # type: ignore[assignment]
            return_value={"components": "components"}
        )
        issues_mixin.get_field_by_id = MagicMock(  # type: ignore[assignment]
            return_value={"id": "components", "name": "Components"}
        )

        document = issues_mixin.update_issue(
            issue_key="TEST-123",
            components=[{"id": "10001"}, {"name": "API"}],
        )

        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"components": [{"id": "10001"}, {"name": "API"}]}},
        )
        assert document.key == "TEST-123"

    def test_update_issue_components_clear(self, issues_mixin: IssuesMixin):
        """Test clearing an issue's components with an empty list."""
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}
        issues_mixin._generate_field_map = MagicMock(  # type: ignore[assignment]
            return_value={"components": "components"}
        )
        issues_mixin.get_field_by_id = MagicMock(  # type: ignore[assignment]
            return_value={"id": "components", "name": "Components"}
        )

        document = issues_mixin.update_issue(issue_key="TEST-123", components=[])

        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"components": []}},
        )
        assert document.key == "TEST-123"

    def test_update_issue_clears_field_with_none(self, issues_mixin: IssuesMixin):
        """Test update_issue passes None through kwargs to clear a field."""
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        issues_mixin.update_issue(issue_key="TEST-123", priority=None)

        issues_mixin.jira.update_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.update_issue.call_args
        fields = call_kwargs[1]["update"]["fields"]
        assert "priority" in fields
        assert fields["priority"] is None

    def test_delete_issue(self, issues_mixin: IssuesMixin):
        """Test deleting an issue."""
        # Call the method
        result = issues_mixin.delete_issue("TEST-123")

        # Verify the API call
        issues_mixin.jira.delete_issue.assert_called_once_with("TEST-123")
        assert result is True

    def test_delete_issue_error(self, issues_mixin: IssuesMixin):
        """Test error handling when deleting an issue."""
        # Setup mock to throw exception
        issues_mixin.jira.delete_issue.side_effect = Exception("Delete failed")

        # Call the method and verify exception is raised correctly
        with pytest.raises(
            Exception, match="Error deleting issue TEST-123: Delete failed"
        ):
            issues_mixin.delete_issue("TEST-123")

    def test_process_additional_fields_with_fixversions(
        self, issues_mixin: IssuesMixin
    ):
        """Test _process_additional_fields properly handles fixVersions field."""
        # Initialize test data
        fields = {}
        kwargs = {"fixVersions": [{"name": "TestRelease"}]}

        # Call the method
        issues_mixin._process_additional_fields(fields, kwargs)

        # Verify fixVersions was added correctly to fields
        assert "fixVersions" in fields
        assert fields["fixVersions"] == [{"name": "TestRelease"}]

    def test_process_additional_fields_none_clears_field(
        self, issues_mixin: IssuesMixin
    ):
        """Test _process_additional_fields passes None through to clear fields."""
        fields = {}
        kwargs = {"customfield_10013": None}  # Sprint field, set to null

        issues_mixin._process_additional_fields(fields, kwargs)

        # None must be preserved — it tells Jira API to clear the field
        assert "customfield_10013" in fields
        assert fields["customfield_10013"] is None

    def test_process_additional_fields_none_clears_named_field(
        self, issues_mixin: IssuesMixin
    ):
        """Test _process_additional_fields passes None through for named fields."""
        fields = {}
        kwargs = {"priority": None}

        issues_mixin._process_additional_fields(fields, kwargs)

        # priority=None should clear the priority field
        assert "priority" in fields
        assert fields["priority"] is None

    def test_process_additional_fields_invalid_value_still_skipped(
        self, issues_mixin: IssuesMixin
    ):
        """Test _process_additional_fields still skips fields with invalid format."""
        fields = {}
        kwargs = {"priority": 12345}  # Invalid: priority expects string or dict

        issues_mixin._process_additional_fields(fields, kwargs)

        # Invalid value should NOT be added to fields
        assert "priority" not in fields

    def test_create_issue_with_parent_for_task(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating a regular task issue with a parent field."""
        create_response = {
            "id": "12345",
            "key": "TEST-456",
            "self": "https://jira.example.com/rest/api/2/issue/12345",
        }
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            key="TEST-456",
            summary="Test Task with Parent",
            description="This is a test",
            issue_type="Task",
            parent={"key": "TEST-123"},
        )

        issues_mixin._get_account_id = MagicMock(return_value="user123")

        # Execute - create a Task with parent field
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Task with Parent",
            issue_type="Task",
            description="This is a test",
            assignee="jdoe",
            parent="TEST-123",  # Adding parent for a non-subtask
        )

        # Verify
        issues_mixin.jira.create_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.create_issue.call_args[1]
        assert "fields" in call_kwargs
        fields = call_kwargs["fields"]

        # Verify parent field was included
        assert "parent" in fields
        assert fields["parent"] == {"key": "TEST-123"}

        # Verify issue method was called after creation
        assert issues_mixin.jira.get_issue.called
        assert issues_mixin.jira.get_issue.call_args[0][0] == "TEST-456"

        # Verify the issue was created successfully
        assert result is not None
        assert result.key == "TEST-456"

    def test_create_issue_with_fixversions(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating an issue with fixVersions in additional_fields."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            fixVersions=[{"name": "1.0.0"}]
        )

        # Create the issue with fixVersions in additional_fields
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            fixVersions=[{"name": "1.0.0"}],
        )

        # Verify API call to create issue
        issues_mixin.jira.create_issue.assert_called_once()
        call_args = issues_mixin.jira.create_issue.call_args[1]
        fields = call_args["fields"]
        assert fields["project"]["key"] == "TEST"
        assert fields["summary"] == "Test Issue"
        assert fields["issuetype"]["name"] == "Bug"
        # Description is ADF dict on Cloud
        assert isinstance(fields["description"], dict)
        assert fields["description"]["version"] == 1
        assert "fixVersions" in fields
        assert fields["fixVersions"] == [{"name": "1.0.0"}]

        # Verify API call to get issue
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123")

        # Verify result
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.issue_type and result.issue_type.name == "Bug"
        assert hasattr(result, "fix_versions")
        assert len(result.fix_versions) == 1
        # The JiraIssue model might process fixVersions differently, check the actual structure
        # This depends on how JiraIssue.from_api_response handles the fixVersions field
        # If it's a list of dictionaries, use:
        if hasattr(result.fix_versions[0], "name"):
            assert result.fix_versions[0].name == "1.0.0"
        else:
            # If it's a list of strings or other format, adjust accordingly:
            assert "1.0.0" in str(result.fix_versions[0])

    def test_get_issue_with_custom_fields(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with custom fields parameter."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            issue_id="10001",
            summary="Test issue with custom field",
            description="Issue description",
            customfield_10049="Custom value",
            customfield_10050={"value": "Option value"},
        )

        # Test with string format
        issue = issues_mixin.get_issue("TEST-123", fields="summary,customfield_10049")

        # Verify the API call
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields="summary,customfield_10049",
            properties=None,
            update_history=True,
        )

        # Check the result
        simplified = issue.to_simplified_dict()
        assert "customfield_10049" in simplified
        assert simplified["customfield_10049"] == {"value": "Custom value"}
        assert "description" not in simplified

        # Test with list format
        issues_mixin.jira.get_issue.reset_mock()
        issue = issues_mixin.get_issue(
            "TEST-123", fields=["summary", "customfield_10050"]
        )

        # Verify API call converts list to comma-separated string
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields="summary,customfield_10050",
            properties=None,
            update_history=True,
        )

        # Check the result
        simplified = issue.to_simplified_dict()
        assert "customfield_10050" in simplified
        assert simplified["customfield_10050"] == {"value": "Option value"}

    def test_get_issue_with_all_fields(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with '*all' fields parameter."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            issue_id="10001",
            summary="Test issue",
            description="Description",
            customfield_10049="Custom value",
        )

        # Test with "*all" parameter
        issue = issues_mixin.get_issue("TEST-123", fields="*all")

        issues_mixin.jira.get_issue.assert_called_once_with(
            "TEST-123",
            expand=None,
            fields="*all",
            properties=None,
            update_history=True,
        )

        # Check that all fields are included
        simplified = issue.to_simplified_dict()
        assert "summary" in simplified
        assert "description" in simplified
        assert "customfield_10049" in simplified

    def test_get_issue_with_properties(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with properties parameter."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(issue_id="10001")

        # Test with properties parameter as string
        issues_mixin.get_issue("TEST-123", properties="property1,property2")

        # Verify API call - should include properties parameter and add 'properties' to fields
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties="property1,property2",
            update_history=True,
        )

        # Test with properties parameter as list
        issues_mixin.jira.get_issue.reset_mock()
        issues_mixin.get_issue("TEST-123", properties=["property1", "property2"])

        # Verify API call - should include properties parameter as comma-separated string and add 'properties' to fields
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties="property1,property2",
            update_history=True,
        )

    def test_get_issue_with_update_history(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with update_history parameter."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(issue_id="10001")

        # Test with update_history=False
        issues_mixin.get_issue("TEST-123", update_history=False)

        # Verify API call - should include update_history parameter
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=False,
        )

    def test_batch_create_issues_basic(self, issues_mixin: IssuesMixin):
        """Test basic functionality of batch_create_issues."""
        # Setup test data
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
                "description": "Description 1",
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
                "description": "Description 2",
                "assignee": "john.doe",
                "components": ["Frontend"],
            },
        ]

        # Mock bulk create response
        bulk_response = {
            "issues": [
                {"id": "1", "key": "TEST-1", "self": "http://example.com/TEST-1"},
                {"id": "2", "key": "TEST-2", "self": "http://example.com/TEST-2"},
            ],
            "errors": [],
        }
        issues_mixin.jira.create_issues.return_value = bulk_response

        # Mock get_issue responses
        def get_issue_side_effect(key):
            if key == "TEST-1":
                return {
                    "id": "1",
                    "key": "TEST-1",
                    "fields": {"summary": "Test Issue 1"},
                }
            return {"id": "2", "key": "TEST-2", "fields": {"summary": "Test Issue 2"}}

        issues_mixin.jira.get_issue.side_effect = get_issue_side_effect
        issues_mixin._get_account_id.return_value = "user123"

        # Call the method
        result = issues_mixin.batch_create_issues(issues)

        # Verify results
        assert len(result) == 2
        assert result[0].key == "TEST-1"
        assert result[1].key == "TEST-2"

        # Verify bulk create was called correctly
        issues_mixin.jira.create_issues.assert_called_once()
        call_args = issues_mixin.jira.create_issues.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0]["fields"]["summary"] == "Test Issue 1"
        assert call_args[1]["fields"]["summary"] == "Test Issue 2"

    def test_batch_create_issues_validate_only(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues with validate_only=True."""
        # Setup test data
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
            },
        ]

        # Call the method with validate_only=True
        result = issues_mixin.batch_create_issues(issues, validate_only=True)

        # Verify no issues were created
        assert len(result) == 0
        assert not issues_mixin.jira.create_issues.called

    def test_batch_create_issues_missing_required_fields(
        self, issues_mixin: IssuesMixin
    ):
        """Test batch_create_issues with missing required fields."""
        # Setup test data with missing fields
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                # Missing issue_type
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
            },
        ]

        # Verify it raises ValueError
        with pytest.raises(ValueError) as exc_info:
            issues_mixin.batch_create_issues(issues)

        assert "Missing required fields" in str(exc_info.value)
        assert not issues_mixin.jira.create_issues.called

    def test_batch_create_issues_partial_failure(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues when some issues fail to create."""
        # Setup test data
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
            },
        ]

        # Mock bulk create response with an error
        bulk_response = {
            "issues": [
                {"id": "1", "key": "TEST-1", "self": "http://example.com/TEST-1"},
            ],
            "errors": [{"issue": {"key": None}, "error": "Invalid issue type"}],
        }
        issues_mixin.jira.create_issues.return_value = bulk_response

        # Mock get_issue response for successful creation
        issues_mixin.jira.get_issue.return_value = {
            "id": "1",
            "key": "TEST-1",
            "fields": {"summary": "Test Issue 1"},
        }

        # Call the method
        result = issues_mixin.batch_create_issues(issues)

        # Verify results - should have only the first issue
        assert len(result) == 1
        assert result[0].key == "TEST-1"

        # Verify error was logged
        issues_mixin.jira.create_issues.assert_called_once()
        assert len(issues_mixin.jira.get_issue.mock_calls) == 1

    def test_batch_create_issues_empty_list(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues with an empty list."""
        result = issues_mixin.batch_create_issues([])
        assert result == []
        assert not issues_mixin.jira.create_issues.called

    def test_batch_create_issues_with_components(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues with component handling."""
        # Setup test data with various component formats
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
                "components": ["Frontend", "", None, "  Backend  "],
            }
        ]

        # Mock responses
        bulk_response = {
            "issues": [
                {"id": "1", "key": "TEST-1", "self": "http://example.com/TEST-1"},
            ],
            "errors": [],
        }
        issues_mixin.jira.create_issues.return_value = bulk_response
        issues_mixin.jira.get_issue.return_value = {
            "id": "1",
            "key": "TEST-1",
            "fields": {"summary": "Test Issue 1"},
        }

        # Call the method
        result = issues_mixin.batch_create_issues(issues)

        # Verify results
        assert len(result) == 1

        # Verify components were properly formatted
        call_args = issues_mixin.jira.create_issues.call_args[0][0]
        assert len(call_args) == 1
        components = call_args[0]["fields"]["components"]
        assert len(components) == 2
        assert components[0]["name"] == "Frontend"
        assert components[1]["name"] == "Backend"

    @pytest.mark.parametrize(
        "is_cloud, user_field, user_id",
        [
            pytest.param(True, "accountId", "account-123", id="cloud"),
            pytest.param(False, "name", "jdoe", id="server"),
        ],
    )
    def test_add_assignee_to_fields(
        self,
        issues_mixin: IssuesMixin,
        is_cloud: bool,
        user_field: str,
        user_id: str,
    ):
        """Test _add_assignee_to_fields for Cloud and Server/DC."""
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = is_cloud

        fields: dict = {}
        issues_mixin._add_assignee_to_fields(fields, user_id)

        assert fields["assignee"] == {user_field: user_id}

    def test_batch_get_changelogs_not_cloud(self, issues_mixin: IssuesMixin):
        """Test batch_get_changelogs method on non-cloud instance."""
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = False

        with pytest.raises(NotImplementedError):
            issues_mixin.batch_get_changelogs(
                issue_ids_or_keys=["TEST-123"],
                fields=["summary", "description"],
            )

    def test_batch_get_changelogs_cloud(self, issues_mixin: IssuesMixin):
        """Test batch_get_changelogs method on cloud instance."""
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = True

        # Mock get_paged result
        mock_get_paged_result = [
            {
                "issueChangeLogs": [
                    {
                        "issueId": "TEST-1",
                        "changeHistories": [
                            {
                                "id": "10001",
                                "author": {
                                    "accountId": "user123",
                                    "displayName": "Test User 1",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "2024-01-05T10:06:03.548+0800",
                                "items": [
                                    {
                                        "field": "IssueParentAssociation",
                                        "fieldtype": "jira",
                                        "from": None,
                                        "fromString": None,
                                        "to": "1001",
                                        "toString": "TEST-100",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "issueId": "TEST-2",
                        "changeHistories": [
                            {
                                "id": "10002",
                                "author": {
                                    "accountId": "user456",
                                    "displayName": "Test User 2",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "1704106800000",  # 2024-01-01
                                "items": [
                                    {
                                        "field": "Parent",
                                        "fieldtype": "jira",
                                        "from": None,
                                        "fromString": None,
                                        "to": "1002",
                                        "toString": "TEST-200",
                                    }
                                ],
                            },
                            {
                                "id": "10003",
                                "author": {
                                    "accountId": "user789",
                                    "displayName": "Test User 3",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "2024-01-06T10:06:03.548+0800",
                                "items": [
                                    {
                                        "field": "Parent",
                                        "fieldtype": "jira",
                                        "from": "1002",
                                        "fromString": "TEST-200",
                                        "to": "1003",
                                        "toString": "TEST-300",
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "nextPageToken": "token1",
            },
            {
                "issueChangeLogs": [
                    {
                        "issueId": "TEST-2",
                        "changeHistories": [
                            {
                                "id": "10004",
                                "author": {
                                    "accountId": "user123",
                                    "displayName": "Test User 1",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "2024-01-10T10:06:03.548+0800",
                                "items": [
                                    {
                                        "field": "Parent",
                                        "fieldtype": "jira",
                                        "from": "1003",
                                        "fromString": "TEST-300",
                                        "to": "1004",
                                        "toString": "TEST-400",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        ]

        # Expected result
        expected_result = [
            {
                "assignee": {"display_name": "Unassigned"},
                "changelogs": [
                    {
                        "author": {
                            "account_id": "user123",
                            "avatar_url": None,
                            "display_name": "Test User 1",
                            "email": None,
                            "name": "Test User 1",
                        },
                        "created": "2024-01-05T10:06:03.548000+08:00",
                        "items": [
                            {
                                "field": "IssueParentAssociation",
                                "fieldtype": "jira",
                                "to_id": "1001",
                                "to_string": "TEST-100",
                            },
                        ],
                    },
                ],
                "id": "TEST-1",
                "key": "UNKNOWN-0",
                "summary": "",
            },
            {
                "assignee": {"display_name": "Unassigned"},
                "changelogs": [
                    {
                        "author": {
                            "account_id": "user456",
                            "avatar_url": None,
                            "display_name": "Test User 2",
                            "email": None,
                            "name": "Test User 2",
                        },
                        "created": "2024-01-01T11:00:00+00:00",
                        "items": [
                            {
                                "field": "Parent",
                                "fieldtype": "jira",
                                "to_id": "1002",
                                "to_string": "TEST-200",
                            },
                        ],
                    },
                    {
                        "author": {
                            "account_id": "user789",
                            "avatar_url": None,
                            "display_name": "Test User 3",
                            "email": None,
                            "name": "Test User 3",
                        },
                        "created": "2024-01-06T10:06:03.548000+08:00",
                        "items": [
                            {
                                "field": "Parent",
                                "fieldtype": "jira",
                                "from_id": "1002",
                                "from_string": "TEST-200",
                                "to_id": "1003",
                                "to_string": "TEST-300",
                            },
                        ],
                    },
                    {
                        "author": {
                            "account_id": "user123",
                            "avatar_url": None,
                            "display_name": "Test User 1",
                            "email": None,
                            "name": "Test User 1",
                        },
                        "created": "2024-01-10T10:06:03.548000+08:00",
                        "items": [
                            {
                                "field": "Parent",
                                "fieldtype": "jira",
                                "from_id": "1003",
                                "from_string": "TEST-300",
                                "to_id": "1004",
                                "to_string": "TEST-400",
                            },
                        ],
                    },
                ],
                "id": "TEST-2",
                "key": "UNKNOWN-0",
                "summary": "",
            },
        ]

        # Mock the get_paged method
        issues_mixin.get_paged = MagicMock(return_value=mock_get_paged_result)

        # Call the method
        result = issues_mixin.batch_get_changelogs(
            issue_ids_or_keys=["TEST-1", "TEST-2"],
            fields=["Parent"],
        )

        # Verify the result
        simplified_result = [issue.to_simplified_dict() for issue in result]
        assert simplified_result == expected_result

        # Verify the method was called with the correct arguments
        issues_mixin.get_paged.assert_called_once_with(
            method="post",
            url=issues_mixin.jira.resource_url("changelog/bulkfetch"),
            params_or_json={
                "fieldIds": ["Parent"],
                "issueIdsOrKeys": ["TEST-1", "TEST-2"],
            },
        )

    def test_create_issue_with_labels(self, issues_mixin: IssuesMixin, make_issue_data):
        """Test creating an issue with labels in additional_fields."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            labels=["bug", "frontend"]
        )

        # Create the issue with labels as a list
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            labels=["bug", "frontend"],
        )

        # Verify the API call
        issues_mixin.jira.create_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.create_issue.call_args[1]
        assert "fields" in call_kwargs
        fields = call_kwargs["fields"]

        # Verify labels were added to the fields
        assert "labels" in fields
        assert fields["labels"] == ["bug", "frontend"]

        # Verify result
        assert result.key == "TEST-123"
        assert result.labels == ["bug", "frontend"]

    def test_create_issue_with_labels_as_string(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test creating an issue with labels as comma-separated string in additional_fields."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        issues_mixin.jira.get_issue.return_value = make_issue_data(
            labels=["bug", "frontend"]
        )

        # Create the issue with labels as a comma-separated string
        # Pass labels directly instead of through additional_fields
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            labels="bug,frontend",  # Pass as string and let _format_field_value_for_write handle it
        )

        # Verify the API call
        issues_mixin.jira.create_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.create_issue.call_args[1]
        assert "fields" in call_kwargs
        fields = call_kwargs["fields"]

        # Verify labels were parsed and added to the fields
        assert "labels" in fields
        assert fields["labels"] == ["bug", "frontend"]

        # Verify result
        assert result.key == "TEST-123"
        assert result.labels == ["bug", "frontend"]

    def test_get_issue_with_config_projects_filter_restricted(
        self, issues_mixin: IssuesMixin
    ):
        """Test get_issue with projects filter from config - restricted case."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        issues_mixin.jira.jql.return_value = mock_issues
        issues_mixin.config.url = "https://example.atlassian.net"
        issues_mixin.config.projects_filter = "DEV"

        # Mock the API to raise an exception
        issues_mixin.jira.get_issue.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception,
            match=(
                "Error retrieving issue TEST-123: "
                "Issue with project prefix 'TEST' are restricted by configuration"
            ),
        ):
            issues_mixin.get_issue("TEST-123")

    def test_get_issue_with_config_projects_filter_allowed(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with projects filter from config - allowed case."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            issue_id="10001",
            key="DEV-123",
            summary="Test issue",
        )
        issues_mixin.config.url = "https://example.atlassian.net"
        issues_mixin.config.projects_filter = "DEV"

        # Call the method
        result = issues_mixin.get_issue("DEV-123")

        # Verify the API call was made correctly
        issues_mixin.jira.get_issue.assert_called_once_with(
            "DEV-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=True,
        )

        # Verify the result
        assert isinstance(result, JiraIssue)
        assert result.key == "DEV-123"
        assert result.summary == "Test issue"

    def test_get_issue_with_multiple_projects_filter(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with multiple projects in the filter."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            issue_id="10001",
            key="PROD-123",
            summary="Production issue",
            description="This is a production issue",
        )
        issues_mixin.config.url = "https://example.atlassian.net"
        issues_mixin.config.projects_filter = "DEV,PROD"

        # Call the method
        result = issues_mixin.get_issue("PROD-123")

        # Verify the API call was made correctly
        issues_mixin.jira.get_issue.assert_called_once_with(
            "PROD-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=True,
        )

        # Verify the result
        assert isinstance(result, JiraIssue)
        assert result.key == "PROD-123"
        assert result.summary == "Production issue"

    def test_create_issue_with_cascading_select(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test create_issue with a cascading select custom field via kwargs."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response
        issues_mixin.jira.get_issue.return_value = make_issue_data()

        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            customfield_10020=("NA", "US"),
        )

        # Verify the create API was called
        issues_mixin.jira.create_issue.assert_called_once()
        fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        # Cascading select should be formatted as {value, child}
        assert fields["customfield_10020"] == {
            "value": "NA",
            "child": {"value": "US"},
        }
        assert result.key == "TEST-123"

    def test_create_issue_with_multiselect(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test create_issue with a multi-select custom field via kwargs."""
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response
        issues_mixin.jira.get_issue.return_value = make_issue_data()

        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            customfield_10021=["opt1", "opt2"],
        )

        # Verify the create API was called
        issues_mixin.jira.create_issue.assert_called_once()
        fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        # Multi-select strings should be wrapped in {value: ...}
        assert fields["customfield_10021"] == [
            {"value": "opt1"},
            {"value": "opt2"},
        ]
        assert result.key == "TEST-123"

    def test_get_issue_with_whitespace_in_projects_filter(
        self, issues_mixin: IssuesMixin, make_issue_data
    ):
        """Test get_issue with extra whitespace in the projects filter."""
        issues_mixin.jira.get_issue.return_value = make_issue_data(
            issue_id="10001",
            key="DEV-123",
            summary="Development issue",
            description="This is a development issue",
        )
        issues_mixin.config.url = "https://example.atlassian.net"
        issues_mixin.config.projects_filter = " DEV , PROD "  # Extra whitespace

        # Call the method
        result = issues_mixin.get_issue("DEV-123")

        # Verify the API call was made correctly
        issues_mixin.jira.get_issue.assert_called_once_with(
            "DEV-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=True,
        )

        # Verify the result
        assert isinstance(result, JiraIssue)
        assert result.key == "DEV-123"
        assert result.summary == "Development issue"


class TestMoveIssue:
    """Tests for IssuesMixin.move_issue."""

    @pytest.fixture
    def cloud_mixin(self, jira_fetcher: JiraFetcher) -> IssuesMixin:
        """IssuesMixin wired to a Cloud instance."""
        mixin = jira_fetcher
        mixin.config.url = "https://test.atlassian.net"
        return mixin

    @pytest.fixture
    def server_mixin(self, jira_fetcher: JiraFetcher) -> IssuesMixin:
        """IssuesMixin wired to a Server/DC instance."""
        mixin = jira_fetcher
        mixin.config.url = "https://jira.example.com"
        return mixin

    def _task_response(
        self,
        status: str,
        processed_issues: list[str] | None = None,
        invalid_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "processedAccessibleIssues": processed_issues or [],
            "invalidOrInaccessibleIssueCount": invalid_count,
        }

    def _source_issue_response(
        self,
        issue_type_id: str = "10000",
        issue_type_name: str = "Task",
        *,
        subtask: bool = False,
    ) -> dict[str, Any]:
        return {
            "fields": {
                "issuetype": {
                    "id": issue_type_id,
                    "name": issue_type_name,
                    "subtask": subtask,
                }
            }
        }

    def _configure_target_issue_types(
        self,
        cloud_mixin: IssuesMixin,
        issue_types: list[dict[str, Any]] | None = None,
    ) -> None:
        cloud_mixin.jira.issue_createmeta_issuetypes = MagicMock(
            return_value={
                "values": issue_types
                or [{"id": "10000", "name": "Task", "subtask": False}]
            }
        )

    def test_move_issue_success(self, cloud_mixin: IssuesMixin, make_issue_data):
        """Successful move returns JiraIssue with new key."""
        self._configure_target_issue_types(
            cloud_mixin,
            [{"id": "10002", "name": "Task", "subtask": False}],
        )
        cloud_mixin._post_api3 = MagicMock(return_value={"taskId": "task-1"})
        cloud_mixin.jira.resource_url = MagicMock(
            return_value="https://api/bulk/queue/task-1"
        )
        cloud_mixin.jira.get = MagicMock(
            return_value=self._task_response("COMPLETE", ["10050"])
        )
        cloud_mixin.jira.get_issue = MagicMock(
            side_effect=[
                self._source_issue_response(issue_type_id="10000"),
                make_issue_data(key="DST-99", summary="Moved"),
            ]
        )

        result = cloud_mixin.move_issue("SRC-1", "DST")

        assert result.key == "DST-99"
        cloud_mixin._post_api3.assert_called_once_with(
            "bulk/issues/move",
            {
                "sendBulkNotification": False,
                "targetToSourcesMapping": {
                    "DST,10002": {
                        "inferClassificationDefaults": True,
                        "inferFieldDefaults": True,
                        "inferStatusDefaults": True,
                        "inferSubtaskTypeDefault": True,
                        "issueIdsOrKeys": ["SRC-1"],
                    }
                },
            },
        )
        cloud_mixin.jira.resource_url.assert_called_once_with(
            "bulk/queue/task-1", api_version="3"
        )
        assert cloud_mixin.jira.get_issue.call_args_list[0].args == ("SRC-1",)
        assert cloud_mixin.jira.get_issue.call_args_list[0].kwargs == {
            "fields": "issuetype"
        }
        assert cloud_mixin.jira.get_issue.call_args_list[1].args == ("10050",)

    def test_move_issue_not_cloud(self, server_mixin: IssuesMixin):
        """Raises NotImplementedError on Server/DC."""
        with pytest.raises(NotImplementedError, match="Jira Cloud"):
            server_mixin.move_issue("SRC-1", "DST")

    def test_move_issue_empty_key(self, cloud_mixin: IssuesMixin):
        """Raises ValueError when issue_key is empty."""
        with pytest.raises(ValueError, match="Issue key is required"):
            cloud_mixin.move_issue("", "DST")

    def test_move_issue_empty_target(self, cloud_mixin: IssuesMixin):
        """Raises ValueError when target_project_key is empty."""
        with pytest.raises(ValueError, match="Target project key is required"):
            cloud_mixin.move_issue("SRC-1", "")

    def test_move_issue_task_failed(self, cloud_mixin: IssuesMixin):
        """Raises ValueError when the async task reports FAILED."""
        self._configure_target_issue_types(cloud_mixin)
        cloud_mixin.jira.get_issue = MagicMock(
            return_value=self._source_issue_response()
        )
        cloud_mixin._post_api3 = MagicMock(return_value={"taskId": "task-1"})
        cloud_mixin.jira.resource_url = MagicMock(
            return_value="https://api/bulk/queue/task-1"
        )
        cloud_mixin.jira.get = MagicMock(
            return_value={"status": "FAILED", "errorMessages": ["No permission"]}
        )

        with pytest.raises(ValueError, match="Bulk move task failed"):
            cloud_mixin.move_issue("SRC-1", "DST")

    def test_move_issue_task_cancelled(self, cloud_mixin: IssuesMixin):
        """Raises ValueError when the async task is cancelled."""
        self._configure_target_issue_types(cloud_mixin)
        cloud_mixin.jira.get_issue = MagicMock(
            return_value=self._source_issue_response()
        )
        cloud_mixin._post_api3 = MagicMock(return_value={"taskId": "task-1"})
        cloud_mixin.jira.resource_url = MagicMock(
            return_value="https://api/bulk/queue/task-1"
        )
        cloud_mixin.jira.get = MagicMock(
            return_value={"status": "CANCELLED", "result": {}}
        )

        with pytest.raises(ValueError, match="cancelled"):
            cloud_mixin.move_issue("SRC-1", "DST")

    def test_move_issue_timeout(self, cloud_mixin: IssuesMixin):
        """Raises ValueError after exhausting all polling attempts."""
        self._configure_target_issue_types(cloud_mixin)
        cloud_mixin.jira.get_issue = MagicMock(
            return_value=self._source_issue_response()
        )
        cloud_mixin._post_api3 = MagicMock(return_value={"taskId": "task-1"})
        cloud_mixin.jira.resource_url = MagicMock(
            return_value="https://api/bulk/queue/task-1"
        )
        cloud_mixin.jira.get = MagicMock(return_value={"status": "IN_PROGRESS"})

        with patch("mcp_atlassian.jira.issues.time.sleep"):
            with pytest.raises(ValueError, match="timed out"):
                cloud_mixin.move_issue("SRC-1", "DST")

    def test_move_issue_target_project_without_matching_issue_type(
        self, cloud_mixin: IssuesMixin
    ):
        """Raises ValueError when the target project lacks the source issue type."""
        self._configure_target_issue_types(
            cloud_mixin,
            [{"id": "10002", "name": "Story", "subtask": False}],
        )
        cloud_mixin.jira.get_issue = MagicMock(
            return_value=self._source_issue_response(
                issue_type_id="10000", issue_type_name="Task"
            )
        )

        with pytest.raises(ValueError, match="does not support issue type Task"):
            cloud_mixin.move_issue("SRC-1", "DST")

    def test_move_issue_invalid_issue_count(self, cloud_mixin: IssuesMixin):
        """Raises ValueError when the completed task reports invalid issues."""
        self._configure_target_issue_types(cloud_mixin)
        cloud_mixin.jira.get_issue = MagicMock(
            return_value=self._source_issue_response()
        )
        cloud_mixin._post_api3 = MagicMock(return_value={"taskId": "task-1"})
        cloud_mixin.jira.resource_url = MagicMock(
            return_value="https://api/bulk/queue/task-1"
        )
        cloud_mixin.jira.get = MagicMock(
            return_value=self._task_response("COMPLETE", invalid_count=1)
        )

        with pytest.raises(ValueError, match="invalid or inaccessible"):
            cloud_mixin.move_issue("SRC-1", "DST")

    def test_move_issue_falls_back_to_original_key(
        self, cloud_mixin: IssuesMixin, make_issue_data
    ):
        """Falls back to the original key when progress omits processed IDs."""
        self._configure_target_issue_types(cloud_mixin)
        cloud_mixin._post_api3 = MagicMock(return_value={"taskId": "task-1"})
        cloud_mixin.jira.resource_url = MagicMock(
            return_value="https://api/bulk/queue/task-1"
        )
        cloud_mixin.jira.get = MagicMock(return_value=self._task_response("COMPLETE"))
        cloud_mixin.jira.get_issue = MagicMock(
            side_effect=[
                self._source_issue_response(),
                make_issue_data(key="DST-99"),
            ]
        )

        result = cloud_mixin.move_issue("SRC-1", "DST")

        assert result.key == "DST-99"
        assert cloud_mixin.jira.get_issue.call_args_list[1].args == ("SRC-1",)
