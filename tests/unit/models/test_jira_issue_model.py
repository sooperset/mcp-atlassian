"""
Tests for the JiraIssue Pydantic model.

Tests for the JiraIssue model including custom field handling,
epic field extraction, and simplified dict conversion.
"""

import re

import pytest

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from mcp_atlassian.models.jira import (
    JiraIssue,
    JiraIssueLink,
    JiraProject,
    JiraResolution,
    JiraTimetracking,
)


class TestJiraIssue:
    """Tests for the JiraIssue model."""

    def test_from_api_response_with_valid_data(self, jira_issue_data):
        """Test creating a JiraIssue from valid API data."""
        issue = JiraIssue.from_api_response(jira_issue_data)

        assert issue.id == "12345"
        assert issue.key == "PROJ-123"
        assert issue.summary == "Test Issue Summary"
        assert issue.description == "This is a test issue description"
        assert issue.created == "2024-01-01T10:00:00.000+0000"
        assert issue.updated == "2024-01-02T15:30:00.000+0000"

        assert issue.status is not None
        assert issue.status.name == "In Progress"
        assert issue.status.category is not None
        assert issue.status.category.name == "In Progress"

        assert issue.issue_type is not None
        assert issue.issue_type.name == "Task"

        assert issue.priority is not None
        assert issue.priority.name == "Medium"

        assert issue.assignee is not None
        assert issue.assignee.display_name == "Test User"

        assert issue.reporter is not None
        assert issue.reporter.display_name == "Reporter User"

        assert len(issue.labels) == 1
        assert issue.labels[0] == "test-label"

        assert len(issue.comments) == 1
        assert issue.comments[0].body == "This is a test comment"

        assert isinstance(issue.fix_versions, list)
        assert "v1.0" in issue.fix_versions

        assert isinstance(issue.attachments, list)
        assert len(issue.attachments) == 1
        assert issue.attachments[0].filename == "test_attachment.txt"

        assert isinstance(issue.timetracking, JiraTimetracking)
        assert issue.timetracking.original_estimate == "1d"

        assert issue.project is not None
        assert issue.project.key == "PROJ"
        assert issue.project.name == "Test Project"
        assert issue.resolution is not None
        assert issue.resolution.name == "Fixed"
        assert issue.duedate == "2024-12-31"
        assert issue.resolutiondate == "2024-01-15T11:00:00.000+0000"
        assert issue.parent is not None
        assert issue.parent["key"] == "PROJ-122"
        assert issue.subtasks is not None
        assert len(issue.subtasks) == 1
        assert issue.subtasks[0]["key"] == "PROJ-124"
        assert issue.security is not None
        assert issue.security["name"] == "Internal"
        assert issue.worklog is not None
        assert issue.worklog["total"] == 0
        assert issue.worklog["maxResults"] == 20

        # Verify custom_fields structure after from_api_response
        assert "customfield_10001" in issue.custom_fields
        assert issue.custom_fields["customfield_10001"] == {
            "value": "Custom Text Field Value",
            "name": "My Custom Text Field",
        }
        assert "customfield_10002" in issue.custom_fields
        assert issue.custom_fields["customfield_10002"] == {
            "value": {"value": "Custom Select Value"},  # Original value is a dict
            "name": "My Custom Select",
        }

    def test_from_api_response_with_new_fields(self):
        """Test creating a JiraIssue focusing on parsing the new fields."""
        # Construct local mock data including the new fields
        local_issue_data = {
            "id": "9999",
            "key": "NEW-1",
            "fields": {
                "summary": "Issue testing new fields",
                "project": {
                    "id": "10001",
                    "key": "NEWPROJ",
                    "name": "New Project",
                    "avatarUrls": {"48x48": "url"},
                },
                "resolution": {"id": "10002", "name": "Fixed"},
                "duedate": "2025-01-31",
                "resolutiondate": "2024-08-01T12:00:00.000+0000",
                "parent": {
                    "id": "9998",
                    "key": "NEW-0",
                    "fields": {"summary": "Parent Task"},
                },
                "subtasks": [
                    {"id": "10000", "key": "NEW-2", "fields": {"summary": "Subtask 1"}},
                    {"id": "10001", "key": "NEW-3", "fields": {"summary": "Subtask 2"}},
                ],
                "security": {"id": "10003", "name": "Dev Only"},
                "worklog": {"total": 2, "maxResults": 20, "worklogs": []},
            },
        }
        issue = JiraIssue.from_api_response(local_issue_data)

        assert issue.id == "9999"
        assert issue.key == "NEW-1"
        assert issue.summary == "Issue testing new fields"

        # Assertions for new fields using LOCAL data
        assert isinstance(issue.project, JiraProject)
        assert issue.project.key == "NEWPROJ"
        assert issue.project.name == "New Project"
        assert isinstance(issue.resolution, JiraResolution)
        assert issue.resolution.name == "Fixed"
        assert issue.duedate == "2025-01-31"
        assert issue.resolutiondate == "2024-08-01T12:00:00.000+0000"
        assert isinstance(issue.parent, dict)
        assert issue.parent["key"] == "NEW-0"
        assert isinstance(issue.subtasks, list)
        assert len(issue.subtasks) == 2
        assert issue.subtasks[0]["key"] == "NEW-2"
        assert isinstance(issue.security, dict)
        assert issue.security["name"] == "Dev Only"
        assert isinstance(issue.worklog, dict)
        assert issue.worklog["total"] == 2

    def test_from_api_response_with_issuelinks(self, jira_issue_data):
        """Test creating a JiraIssue with issue links."""
        # Augment jira_issue_data with mock issuelinks
        mock_issuelinks_data = [
            {
                "id": "10000",
                "type": {
                    "id": "10000",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "outwardIssue": {
                    "id": "10001",
                    "key": "PROJ-789",
                    "self": "https://example.atlassian.net/rest/api/2/issue/10001",
                    "fields": {
                        "summary": "Blocked Issue",
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "issuetype": {"name": "Task"},
                    },
                },
            },
            {
                "id": "10001",
                "type": {
                    "id": "10001",
                    "name": "Relates to",
                    "inward": "relates to",
                    "outward": "relates to",
                },
                "inwardIssue": {
                    "id": "10002",
                    "key": "PROJ-111",
                    "self": "https://example.atlassian.net/rest/api/2/issue/10002",
                    "fields": {
                        "summary": "Related Issue",
                        "status": {"name": "In Progress"},
                        "priority": {"name": "Medium"},
                        "issuetype": {"name": "Story"},
                    },
                },
            },
        ]
        jira_issue_data_with_links = jira_issue_data.copy()
        # Ensure fields dictionary exists
        if "fields" not in jira_issue_data_with_links:
            jira_issue_data_with_links["fields"] = {}
        jira_issue_data_with_links["fields"]["issuelinks"] = mock_issuelinks_data

        issue = JiraIssue.from_api_response(
            jira_issue_data_with_links, requested_fields="*all"
        )

        assert issue.issuelinks is not None
        assert len(issue.issuelinks) == 2
        assert isinstance(issue.issuelinks[0], JiraIssueLink)

        # Check first link (outward)
        assert issue.issuelinks[0].id == "10000"
        assert issue.issuelinks[0].type is not None
        assert issue.issuelinks[0].type.name == "Blocks"
        assert issue.issuelinks[0].outward_issue is not None
        assert issue.issuelinks[0].outward_issue.key == "PROJ-789"
        assert issue.issuelinks[0].outward_issue.fields is not None
        assert issue.issuelinks[0].outward_issue.fields.summary == "Blocked Issue"
        assert issue.issuelinks[0].inward_issue is None

        # Test simplified dict output
        simplified = issue.to_simplified_dict()
        assert "issuelinks" in simplified
        assert len(simplified["issuelinks"]) == 2
        assert simplified["issuelinks"][0]["type"]["name"] == "Blocks"
        assert simplified["issuelinks"][0]["outward_issue"]["key"] == "PROJ-789"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssue from empty data."""
        issue = JiraIssue.from_api_response({})
        assert issue.id == JIRA_DEFAULT_ID
        assert issue.key == "UNKNOWN-0"
        assert issue.summary == EMPTY_STRING
        assert issue.description is None
        assert issue.created == EMPTY_STRING
        assert issue.updated == EMPTY_STRING
        assert issue.status is None
        assert issue.issue_type is None
        assert issue.priority is None
        assert issue.assignee is None
        assert issue.reporter is None
        assert len(issue.labels) == 0
        assert len(issue.comments) == 0
        assert issue.project is None
        assert issue.resolution is None
        assert issue.duedate is None
        assert issue.resolutiondate is None
        assert issue.parent is None
        assert issue.subtasks == []
        assert issue.security is None
        assert issue.worklog is None

    def test_to_simplified_dict(self, jira_issue_data):
        """Test converting a JiraIssue to a simplified dictionary."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        simplified = issue.to_simplified_dict()

        # Essential fields from original test
        assert isinstance(simplified, dict)
        assert "key" in simplified
        assert simplified["key"] == "PROJ-123"
        assert "summary" in simplified
        assert simplified["summary"] == "Test Issue Summary"

        assert "created" in simplified
        assert isinstance(simplified["created"], str)
        assert "updated" in simplified
        assert isinstance(simplified["updated"], str)

        if isinstance(simplified["status"], str):
            assert simplified["status"] == "In Progress"
        elif isinstance(simplified["status"], dict):
            assert simplified["status"]["name"] == "In Progress"

        if isinstance(simplified["issue_type"], str):
            assert simplified["issue_type"] == "Task"
        elif isinstance(simplified["issue_type"], dict):
            assert simplified["issue_type"]["name"] == "Task"

        if isinstance(simplified["priority"], str):
            assert simplified["priority"] == "Medium"
        elif isinstance(simplified["priority"], dict):
            assert simplified["priority"]["name"] == "Medium"

        assert "assignee" in simplified
        assert "reporter" in simplified

        # Test with "*all"
        issue_all = JiraIssue.from_api_response(
            jira_issue_data, requested_fields="*all"
        )
        simplified_all = issue_all.to_simplified_dict()

        # Check keys for all standard fields (new and old) are present
        all_standard_keys = {
            "id",
            "key",
            "summary",
            "description",
            "created",
            "updated",
            "status",
            "issue_type",
            "priority",
            "assignee",
            "reporter",
            "labels",
            "components",
            "timetracking",
            "comments",
            "attachments",
            "url",
            "epic_key",
            "epic_name",
            "fix_versions",
            "project",
            "resolution",
            "duedate",
            "resolutiondate",
            "parent",
            "subtasks",
            "security",
            "worklog",
            # Custom fields present in the mock data should be at the root level when requesting *all
            "customfield_10011",
            "customfield_10014",
            "customfield_10001",
            "customfield_10002",
            "customfield_10003",
        }
        assert all_standard_keys.issubset(simplified_all.keys())

        # Check values for new fields based on mock data
        assert simplified_all["project"]["key"] == "PROJ"
        assert simplified_all["resolution"]["name"] == "Fixed"
        assert simplified_all["duedate"] == "2024-12-31"
        assert simplified_all["resolutiondate"] == "2024-01-15T11:00:00.000+0000"
        assert simplified_all["parent"]["key"] == "PROJ-122"
        assert len(simplified_all["subtasks"]) == 1
        assert simplified_all["security"]["name"] == "Internal"
        assert isinstance(simplified_all["worklog"], dict)

        requested = [
            "key",
            "summary",
            "project",
            "resolution",
            "subtasks",
            "customfield_10011",
        ]
        issue_specific = JiraIssue.from_api_response(
            jira_issue_data, requested_fields=requested
        )
        simplified_specific = issue_specific.to_simplified_dict()

        # Check the requested keys are present
        assert set(simplified_specific.keys()) == {
            "id",
            "key",
            "summary",
            "project",
            "resolution",
            "subtasks",
            "customfield_10011",
        }

        # Check values based on mock data
        assert simplified_specific["project"]["key"] == "PROJ"
        assert simplified_specific["resolution"]["name"] == "Fixed"
        assert len(simplified_specific["subtasks"]) == 1
        # Check custom field output
        assert (
            simplified_specific["customfield_10011"]
            == {
                "value": "Epic Name Example",
                "name": "Epic Name",  # Comes from the "names" map in MOCK_JIRA_ISSUE_RESPONSE
            }
        )

    def test_find_custom_field_in_api_response(self):
        """Test the _find_custom_field_in_api_response method with different field patterns."""
        fields = {
            "customfield_10014": "EPIC-123",
            "customfield_10011": "Epic Name Test",
            "customfield_10000": "Another value",
            "schema": {
                "fields": {
                    "customfield_10014": {"name": "Epic Link", "type": "string"},
                    "customfield_10011": {"name": "Epic Name", "type": "string"},
                    "customfield_10000": {"name": "Custom Field", "type": "string"},
                }
            },
        }

        result = JiraIssue._find_custom_field_in_api_response(fields, ["Epic Link"])
        assert result == "EPIC-123"

        result = JiraIssue._find_custom_field_in_api_response(fields, ["Epic Name"])
        assert result == "Epic Name Test"

        result = JiraIssue._find_custom_field_in_api_response(fields, ["epic link"])
        assert result == "EPIC-123"

        result = JiraIssue._find_custom_field_in_api_response(
            fields, ["epic-link", "epiclink"]
        )
        assert result == "EPIC-123"

        result = JiraIssue._find_custom_field_in_api_response(
            fields, ["Non Existent Field"]
        )
        assert result is None

        result = JiraIssue._find_custom_field_in_api_response({}, ["Epic Link"])
        assert result is None

        result = JiraIssue._find_custom_field_in_api_response(None, ["Epic Link"])
        assert result is None

    def test_epic_field_extraction_different_field_ids(self):
        """Test finding epic fields with different customfield IDs."""
        test_data = {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test Issue",
                "customfield_20100": "EPIC-456",
                "customfield_20200": "My Epic Name",
                "schema": {
                    "fields": {
                        "customfield_20100": {"name": "Epic Link", "type": "string"},
                        "customfield_20200": {"name": "Epic Name", "type": "string"},
                    }
                },
            },
        }
        issue = JiraIssue.from_api_response(test_data)
        assert issue.epic_key == "EPIC-456"
        assert issue.epic_name == "My Epic Name"

    def test_epic_field_extraction_fallback(self):
        """Test using common field names without relying on metadata."""
        test_data = {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test Issue",
                "customfield_10014": "EPIC-456",
                "customfield_10011": "My Epic Name",
            },
        }

        original_method = JiraIssue._find_custom_field_in_api_response
        try:

            def mocked_find_field(fields, name_patterns):
                normalized_patterns = []
                for pattern in name_patterns:
                    norm_pattern = pattern.lower()
                    norm_pattern = re.sub(r"[_\-\s]", "", norm_pattern)
                    normalized_patterns.append(norm_pattern)

                if any("epiclink" in p for p in normalized_patterns):
                    return fields.get("customfield_10014")
                if any("epicname" in p for p in normalized_patterns):
                    return fields.get("customfield_10011")
                return None

            JiraIssue._find_custom_field_in_api_response = staticmethod(
                mocked_find_field
            )

            issue = JiraIssue.from_api_response(test_data)
            assert issue.epic_key == "EPIC-456"
            assert issue.epic_name == "My Epic Name"
        finally:
            JiraIssue._find_custom_field_in_api_response = staticmethod(original_method)

    def test_epic_field_extraction_advanced_patterns(self):
        """Test finding epic fields using various naming patterns."""
        test_data = {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test Issue",
                "customfield_12345": "EPIC-456",
                "customfield_67890": "Epic Name Value",
                "schema": {
                    "fields": {
                        "customfield_12345": {
                            "name": "Epic-Link Field",
                            "type": "string",
                        },
                        "customfield_67890": {"name": "EpicName", "type": "string"},
                    }
                },
            },
        }
        issue = JiraIssue.from_api_response(test_data)
        assert issue.epic_key == "EPIC-456"
        assert issue.epic_name == "Epic Name Value"

    def test_fields_with_names(self):
        """Test using the names to find fields."""

        fields = {
            "customfield_55555": "EPIC-789",
            "customfield_66666": "Special Epic Name",
            "names": {
                "customfield_55555": "Epic Link",
                "customfield_66666": "Epic Name",
            },
        }

        result = JiraIssue._find_custom_field_in_api_response(fields, ["Epic Link"])
        assert result == "EPIC-789"

        test_data = {"id": "12345", "key": "PROJ-123", "fields": fields}
        issue = JiraIssue.from_api_response(test_data)
        assert issue.epic_key == "EPIC-789"
        assert issue.epic_name == "Special Epic Name"

    def test_jira_issue_with_custom_fields(self, jira_issue_data):
        """Test JiraIssue handling of custom fields."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        simplified = issue.to_simplified_dict()
        assert simplified["key"] == "PROJ-123"
        assert simplified["summary"] == "Test Issue Summary"
        # By default (no requested_fields or default set), custom fields are not included
        # unless they are part of DEFAULT_READ_JIRA_FIELDS (which they are not).
        # So, this assertion should be that they are NOT present.
        assert "customfield_10001" not in simplified
        assert "customfield_10002" not in simplified
        assert "customfield_10003" not in simplified

        issue = JiraIssue.from_api_response(
            jira_issue_data, requested_fields="summary,customfield_10001"
        )
        simplified = issue.to_simplified_dict()
        assert "key" in simplified
        assert "summary" in simplified
        assert "customfield_10001" in simplified
        assert simplified["customfield_10001"]["value"] == "Custom Text Field Value"
        assert simplified["customfield_10001"]["name"] == "My Custom Text Field"
        assert "customfield_10002" not in simplified

        issue = JiraIssue.from_api_response(
            jira_issue_data, requested_fields=["key", "customfield_10002"]
        )
        simplified = issue.to_simplified_dict()
        assert "key" in simplified
        assert "customfield_10002" in simplified
        assert "summary" not in simplified
        assert "customfield_10001" not in simplified
        assert simplified["customfield_10002"]["value"] == "Custom Select Value"
        assert simplified["customfield_10002"]["name"] == "My Custom Select"

        issue = JiraIssue.from_api_response(jira_issue_data, requested_fields="*all")
        simplified = issue.to_simplified_dict()
        assert "key" in simplified
        assert "summary" in simplified
        assert "customfield_10001" in simplified
        assert simplified["customfield_10001"]["value"] == "Custom Text Field Value"
        assert simplified["customfield_10001"]["name"] == "My Custom Text Field"
        assert "customfield_10002" in simplified
        assert simplified["customfield_10002"]["value"] == "Custom Select Value"
        assert simplified["customfield_10002"]["name"] == "My Custom Select"
        assert "customfield_10003" in simplified

        issue_specific = JiraIssue.from_api_response(
            jira_issue_data, requested_fields="key,customfield_10014"
        )
        simplified_specific = issue_specific.to_simplified_dict()
        assert "customfield_10014" in simplified_specific
        assert simplified_specific.get("customfield_10014") == {
            "value": "EPIC-KEY-1",
            "name": "Epic Link",
        }

    def test_jira_issue_with_default_fields(self, jira_issue_data):
        """Test that JiraIssue returns only essential fields by default."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        simplified = issue.to_simplified_dict()
        # Check essential fields ARE present
        essential_keys = {
            "id",
            "key",
            "summary",
            "url",
            "description",
            "status",
            "issue_type",
            "priority",
            "project",
            "resolution",
            "duedate",
            "resolutiondate",
            "parent",
            "subtasks",
            "security",
            "worklog",
            "assignee",
            "reporter",
            "labels",
            "components",
            "fix_versions",
            "epic_key",
            "epic_name",
            "timetracking",
            "created",
            "updated",
            "comments",
            "attachments",
        }
        # We check if the key is present; value might be None if not in source data
        for key in essential_keys:
            assert key in simplified, (
                f"Essential key '{key}' missing from default simplified dict"
            )
        assert "customfield_10001" not in simplified
        assert "customfield_10002" not in simplified

        issue = JiraIssue.from_api_response(jira_issue_data, requested_fields="*all")
        simplified = issue.to_simplified_dict()
        assert "customfield_10001" in simplified
        assert "customfield_10002" in simplified

    def test_timetracking_field_processing(self, jira_issue_data):
        """Test that timetracking data is properly processed."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        assert issue.timetracking is not None
        assert issue.timetracking.original_estimate == "1d"
        assert issue.timetracking.remaining_estimate == "4h"
        assert issue.timetracking.time_spent == "4h"
        assert issue.timetracking.original_estimate_seconds == 28800
        assert issue.timetracking.remaining_estimate_seconds == 14400
        assert issue.timetracking.time_spent_seconds == 14400

        issue.requested_fields = "*all"
        simplified = issue.to_simplified_dict()
        assert "timetracking" in simplified
        assert simplified["timetracking"]["original_estimate"] == "1d"

        issue.requested_fields = ["summary", "timetracking"]
        simplified = issue.to_simplified_dict()
        assert "timetracking" in simplified
        assert simplified["timetracking"]["original_estimate"] == "1d"


class TestProcessCustomFieldValue:
    """Tests for _process_custom_field_value."""

    @pytest.fixture()
    def issue(self):
        """Create a minimal JiraIssue for testing _process_custom_field_value."""
        return JiraIssue(
            id="1",
            key="TEST-1",
            summary="test",
        )

    @pytest.mark.parametrize(
        ("field_value", "expected"),
        [
            pytest.param(None, None, id="none"),
            pytest.param("text", "text", id="string"),
            pytest.param(42, 42, id="integer"),
            pytest.param(True, True, id="boolean"),
            pytest.param(3.14, 3.14, id="float"),
        ],
    )
    def test_primitives_unchanged(self, issue, field_value, expected):
        """Primitive values pass through unchanged."""
        assert issue._process_custom_field_value(field_value) == expected

    def test_dict_with_value_key(self, issue):
        """Dicts with 'value' key return that value (select options)."""
        assert issue._process_custom_field_value({"value": "Option A"}) == "Option A"

    def test_jira_reference_object_simplified(self, issue):
        """Jira reference objects (with 'self' URL) simplify to name."""
        ref = {
            "name": "High",
            "self": "https://jira.example.com/rest/api/2/priority/3",
            "id": "3",
        }
        assert issue._process_custom_field_value(ref) == "High"

    def test_plugin_data_object_preserved(self, issue):
        """Plugin data objects (no 'self' key) are preserved in full."""
        checklist_item = {"name": "Item A", "checked": True, "id": 1, "rank": 0}
        result = issue._process_custom_field_value(checklist_item)
        assert result == checklist_item

    def test_list_of_plugin_data_preserved(self, issue):
        """Lists of plugin data objects are preserved in full."""
        items = [
            {"name": "Item A", "checked": True, "id": 1, "rank": 0},
            {"name": "Item B", "checked": False, "id": 2, "rank": 1, "isHeader": True},
        ]
        result = issue._process_custom_field_value(items)
        assert result == items

    def test_list_of_jira_references_simplified(self, issue):
        """Lists of Jira reference objects simplify to names."""
        refs = [
            {
                "name": "Group A",
                "self": "https://jira.example.com/rest/api/2/group?name=A",
            },
            {
                "name": "Group B",
                "self": "https://jira.example.com/rest/api/2/group?name=B",
            },
        ]
        result = issue._process_custom_field_value(refs)
        assert result == ["Group A", "Group B"]

    def test_dict_without_name_or_value_preserved(self, issue):
        """Dicts without 'name' or 'value' keys are preserved as-is."""
        data = {"foo": "bar", "baz": 42}
        assert issue._process_custom_field_value(data) == data

    def test_checklist_custom_field_end_to_end(self):
        """End-to-end: checklist custom field preserved through from_api_response → to_simplified_dict."""
        checklist_items = [
            {"name": "Task 1", "checked": True, "id": 1, "rank": 0},
            {"name": "Task 2", "checked": False, "id": 2, "rank": 1},
            {"name": "Section", "checked": False, "id": 3, "rank": 2, "isHeader": True},
        ]
        api_data = {
            "id": "99",
            "key": "CHECK-1",
            "fields": {
                "summary": "Checklist issue",
                "issuetype": {"name": "Task"},
                "status": {"name": "Open", "statusCategory": {"name": "To Do"}},
                "customfield_10200": checklist_items,
            },
            "names": {
                "customfield_10200": "Okapya Checklist",
            },
        }
        issue = JiraIssue.from_api_response(api_data, requested_fields="*all")
        simplified = issue.to_simplified_dict()
        field = simplified["customfield_10200"]
        assert field["name"] == "Okapya Checklist"
        assert field["value"] == checklist_items
