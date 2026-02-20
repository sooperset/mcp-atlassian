from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.jira.issues import IssuesMixin
from mcp_atlassian.jira.protocols import (
    AttachmentsOperationsProto,
    EpicOperationsProto,
    FieldsOperationsProto,
    IssueOperationsProto,
    ProjectsOperationsProto,
    UsersOperationsProto,
)


class ConcreteIssuesMixin(
    IssuesMixin,
    AttachmentsOperationsProto,
    EpicOperationsProto,
    FieldsOperationsProto,
    IssueOperationsProto,
    ProjectsOperationsProto,
    UsersOperationsProto,
):
    def _generate_field_map(self):
        pass

    def _get_account_id(self, user_identifier):
        pass

    def _try_discover_fields_from_existing_epic(self):
        pass

    def get_field_by_id(self, field_id):
        pass

    def get_field_ids_to_epic(self):
        pass

    def get_project_issue_types(self, project_key):
        pass

    def get_required_fields(self, project_key, issue_type_name):
        pass

    def get_issue_forms(self, issue_key):
        pass

    def get_form_details(self, issue_key, form_id):
        pass

    def prepare_epic_fields(self, fields, summary, kwargs, project_key):
        pass

    def update_epic_fields(self, issue_key, epic_fields):
        pass

    def upload_attachments(self, issue_key, attachment_paths):
        pass

    def _format_field_value_for_write(self, field_id, value, field_definition):
        pass


@pytest.fixture
def issues_mixin():
    """Fixture to create an instance of IssuesMixin with a mocked jira client."""
    with patch("mcp_atlassian.jira.config.JiraConfig.from_env") as mock_from_env:
        mock_config = MagicMock()
        mock_config.is_cloud = True
        mock_from_env.return_value = mock_config

        mixin = ConcreteIssuesMixin()
        mixin.jira = MagicMock()
        mixin.config = mock_config
        # Mock methods that are not part of the mixin but are called by it
        mixin.get_project_issue_types = MagicMock()
        mixin._markdown_to_jira = MagicMock(side_effect=lambda x: x)
        mixin._get_account_id = MagicMock(return_value="account_id_123")
        mixin._add_assignee_to_fields = MagicMock()
        mixin._prepare_epic_fields = MagicMock()
        mixin._prepare_parent_fields = MagicMock()
        mixin._process_additional_fields = MagicMock()
        mixin._handle_create_issue_error = MagicMock()

        # Mock the final call to get the created issue
        created_issue_response = {
            "key": "PROJ-123",
            "fields": {"summary": "Test Summary"},
        }
        mixin.jira.get_issue.return_value = created_issue_response

        return mixin


def test_create_issue_uses_epic_id_when_found(issues_mixin):
    """Verify create_issue uses the issue type ID for 'Epic' when found."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10000", "name": "Story", "subtask": False},
        {"id": "10001", "name": "Epic", "subtask": False},
    ]
    issues_mixin.jira.create_issue.return_value = {"key": "PROJ-1"}

    issues_mixin.create_issue(
        project_key="PROJ",
        summary="New Epic",
        issue_type="Epic",
    )

    call_args = issues_mixin.jira.create_issue.call_args
    assert call_args is not None
    fields = call_args[1]["fields"]
    assert "id" in fields["issuetype"].keys()
    assert "name" in fields["issuetype"].keys()
    assert fields["issuetype"]["id"] == "10001"


def test_create_issue_uses_subtask_id_when_found(issues_mixin):
    """Verify create_issue uses the issue type ID for 'Subtask' when found."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10002", "name": "Sub-task", "subtask": True},
    ]
    issues_mixin.jira.create_issue.return_value = {"key": "PROJ-2"}

    issues_mixin.create_issue(
        project_key="PROJ",
        summary="New Subtask",
        issue_type="Subtask",
        parent="PROJ-1",
    )

    call_args = issues_mixin.jira.create_issue.call_args
    assert call_args is not None
    fields = call_args[1]["fields"]
    assert "id" in fields["issuetype"].keys()
    assert "name" in fields["issuetype"].keys()
    assert fields["issuetype"]["id"] == "10002"


def test_create_issue_falls_back_to_name_if_id_not_found(issues_mixin):
    """Verify create_issue falls back to name if a type ID is not found."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10000", "name": "Story", "subtask": False},
    ]
    issues_mixin.jira.create_issue.return_value = {"key": "PROJ-3"}

    issues_mixin.create_issue(
        project_key="PROJ",
        summary="New Epic with no ID",
        issue_type="Epic",
    )

    call_args = issues_mixin.jira.create_issue.call_args
    assert call_args is not None
    fields = call_args[1]["fields"]
    assert fields["issuetype"] == {"name": "Epic"}


def test_find_epic_issue_type_id_returns_id(issues_mixin):
    """Verify _find_epic_issue_type_id returns the correct ID."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10001", "name": "Epic", "subtask": False},
    ]

    epic_id = issues_mixin._find_epic_issue_type_id("PROJ")
    assert epic_id == "10001"


def test_find_subtask_issue_type_id_returns_id(issues_mixin):
    """Verify _find_subtask_issue_type_id returns the correct ID."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10002", "name": "Sub-task", "subtask": True},
    ]

    subtask_id = issues_mixin._find_subtask_issue_type_id("PROJ")
    assert subtask_id == "10002"


def test_find_epic_issue_type_id_returns_none_if_not_found(issues_mixin):
    """Verify _find_epic_issue_type_id returns None when no Epic type exists."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10000", "name": "Story", "subtask": False},
    ]

    epic_id = issues_mixin._find_epic_issue_type_id("PROJ")
    assert epic_id is None


def test_find_subtask_issue_type_id_returns_none_if_not_found(issues_mixin):
    """Verify _find_subtask_issue_type_id returns None when no Sub-task type exists."""
    issues_mixin.get_project_issue_types.return_value = [
        {"id": "10000", "name": "Story", "subtask": False},
    ]

    subtask_id = issues_mixin._find_subtask_issue_type_id("PROJ")
    assert subtask_id is None
