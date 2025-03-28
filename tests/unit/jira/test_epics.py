"""Tests for the Jira Epics mixin."""

from unittest.mock import MagicMock, call

import pytest

from mcp_atlassian.jira.epics import EpicsMixin
from mcp_atlassian.models.jira import JiraIssue


class TestEpicsMixin:
    """Tests for the EpicsMixin class."""

    @pytest.fixture
    def epics_mixin(self, jira_client):
        """Create an EpicsMixin instance with mocked dependencies."""
        mixin = EpicsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Add a mock for get_issue to use when returning models
        mixin.get_issue = MagicMock(
            return_value=JiraIssue(
                id="12345",
                key="TEST-123",
                summary="Test Issue",
                description="Issue content",
            )
        )

        # Add a mock for search_issues to use for get_epic_issues
        mixin.search_issues = MagicMock(
            return_value=[
                JiraIssue(key="TEST-456", summary="Issue 1"),
                JiraIssue(key="TEST-789", summary="Issue 2"),
            ]
        )

        return mixin

    def test_get_jira_field_ids_cached(self, epics_mixin):
        """Test get_jira_field_ids returns cached values if available."""
        # Setup cached field IDs
        epics_mixin._field_ids_cache = {
            "epic_link": "customfield_10014",
            "epic_name": "customfield_10011",
        }

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the cache was used (jira.get_all_fields should not be called)
        epics_mixin.jira.get_all_fields.assert_not_called()
        assert field_ids == epics_mixin._field_ids_cache

    def test_get_jira_field_ids_from_server(self, epics_mixin):
        """Test get_jira_field_ids fetches from server if cache is empty."""
        # Ensure there's no cache
        if hasattr(epics_mixin, "_field_ids_cache"):
            delattr(epics_mixin, "_field_ids_cache")

        # Mock the server response
        mock_fields = [
            {
                "id": "customfield_10014",
                "name": "Epic Link",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-link"},
            },
            {
                "id": "customfield_10011",
                "name": "Epic Name",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-label"},
            },
        ]
        epics_mixin.jira.get_all_fields.return_value = mock_fields

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the server was queried
        epics_mixin.jira.get_all_fields.assert_called_once()
        assert "epic_link" in field_ids
        assert field_ids["epic_link"] == "customfield_10014"
        assert "epic_name" in field_ids
        assert field_ids["epic_name"] == "customfield_10011"

    def test_get_jira_field_ids_discovers_epic_link(self, epics_mixin):
        """Test get_jira_field_ids identifies Epic Link field."""
        # Setup mock field data
        epics_mixin.jira.get_all_fields.return_value = [
            {
                "id": "customfield_10014",
                "name": "Epic Link",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-link"},
            }
        ]

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the field was identified
        assert "epic_link" in field_ids
        assert field_ids["epic_link"] == "customfield_10014"

    def test_get_jira_field_ids_discovers_epic_name(self, epics_mixin):
        """Test get_jira_field_ids identifies Epic Name field."""
        # Setup mock field data
        epics_mixin.jira.get_all_fields.return_value = [
            {
                "id": "customfield_10011",
                "name": "Epic Name",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-label"},
            }
        ]

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the field was identified
        assert "epic_name" in field_ids
        assert field_ids["epic_name"] == "customfield_10011"

    def test_get_jira_field_ids_discovers_parent(self, epics_mixin):
        """Test get_jira_field_ids identifies Parent field."""
        # Setup mock field data
        epics_mixin.jira.get_all_fields.return_value = [
            {"id": "parent", "name": "Parent", "schema": {"type": "issuelink"}}
        ]

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the field was identified
        assert "parent" in field_ids
        assert field_ids["parent"] == "parent"

    def test_get_jira_field_ids_discovers_epic_color(self, epics_mixin):
        """Test get_jira_field_ids identifies Epic Color field."""
        # Setup mock field data
        epics_mixin.jira.get_all_fields.return_value = [
            {
                "id": "customfield_10010",
                "name": "Epic Color",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-color"},
            }
        ]

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the field was identified
        assert "epic_color" in field_ids
        assert field_ids["epic_color"] == "customfield_10010"

    def test_get_jira_field_ids_discovers_other_epic_fields(self, epics_mixin):
        """Test get_jira_field_ids identifies other Epic-related fields."""
        # Setup mock field data
        epics_mixin.jira.get_all_fields.return_value = [
            {
                "id": "customfield_10012",
                "name": "Epic Team",
                "schema": {"type": "string"},
            }
        ]

        # Call the method
        field_ids = epics_mixin.get_jira_field_ids()

        # Verify the field was identified
        assert "epic_epic_team" in field_ids
        assert field_ids["epic_epic_team"] == "customfield_10012"

    def test_try_discover_fields_from_existing_epic(self, epics_mixin):
        """Test _try_discover_fields_from_existing_epic with a successful discovery."""
        # Skip if we already have both required fields
        field_ids = {"epic_link": "customfield_10014"}  # Missing epic_name

        # Mock Epic search response
        mock_epic = {
            "key": "EPIC-123",
            "fields": {
                "issuetype": {"name": "Epic"},
                "summary": "Test Epic",
                "customfield_10011": "Epic Name Value",  # This should be discovered as epic_name
            },
        }

        mock_results = {"issues": [mock_epic]}
        epics_mixin.jira.jql.return_value = mock_results

        # Call the method
        epics_mixin._try_discover_fields_from_existing_epic(field_ids)

        # Verify the epic_name field was discovered
        assert "epic_name" in field_ids
        assert field_ids["epic_name"] == "customfield_10011"

    def test_try_discover_fields_from_existing_epic_no_epics(self, epics_mixin):
        """Test _try_discover_fields_from_existing_epic when no epics exist."""
        field_ids = {}

        # Mock empty search response
        mock_results = {"issues": []}
        epics_mixin.jira.jql.return_value = mock_results

        # Call the method
        epics_mixin._try_discover_fields_from_existing_epic(field_ids)

        # Verify no fields were discovered
        assert not field_ids

    def test_try_discover_fields_from_existing_epic_with_both_fields(self, epics_mixin):
        """Test _try_discover_fields_from_existing_epic when both fields already exist."""
        field_ids = {"epic_link": "customfield_10014", "epic_name": "customfield_10011"}

        # Call the method - no JQL should be executed
        epics_mixin._try_discover_fields_from_existing_epic(field_ids)

        # Verify jql was not called
        epics_mixin.jira.jql.assert_not_called()

    def test_prepare_epic_fields_basic(self, epics_mixin):
        """Test prepare_epic_fields with basic epic name and color."""
        # Mock get_jira_field_ids
        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={
                "epic_name": "customfield_10011",
                "epic_color": "customfield_10010",
            }
        )

        # Prepare test data
        fields = {}
        summary = "Test Epic"
        kwargs = {}

        # Call the method
        epics_mixin.prepare_epic_fields(fields, summary, kwargs)

        # Verify the epic fields are stored in kwargs with __epic_ prefix
        # instead of directly in fields (for two-step creation)
        assert kwargs["__epic_name_value"] == "Test Epic"
        assert kwargs["__epic_name_field"] == "customfield_10011"
        assert kwargs["__epic_color_value"] == "green"
        assert kwargs["__epic_color_field"] == "customfield_10010"
        # Verify fields dict remains empty
        assert fields == {}

    def test_prepare_epic_fields_with_user_values(self, epics_mixin):
        """Test prepare_epic_fields with user-provided values."""
        # Mock get_jira_field_ids
        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={
                "epic_name": "customfield_10011",
                "epic_color": "customfield_10010",
            }
        )

        # Prepare test data
        fields = {}
        summary = "Test Epic"
        kwargs = {"epic_name": "Custom Epic Name", "epic_color": "blue"}

        # Call the method
        epics_mixin.prepare_epic_fields(fields, summary, kwargs)

        # Verify the epic fields are stored in kwargs with __epic_ prefix
        assert kwargs["__epic_name_value"] == "Custom Epic Name"
        assert kwargs["__epic_name_field"] == "customfield_10011"
        assert kwargs["__epic_color_value"] == "blue"
        assert kwargs["__epic_color_field"] == "customfield_10010"

        # Original values should be removed from kwargs
        assert "epic_name" not in kwargs
        assert "epic_color" not in kwargs

        # Verify fields dict remains empty
        assert fields == {}

    def test_prepare_epic_fields_missing_epic_name(self, epics_mixin):
        """Test prepare_epic_fields with missing epic_name field."""
        # Mock get_jira_field_ids
        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_color": "customfield_10010"}
        )

        # Prepare test data
        fields = {}
        summary = "Test Epic"
        kwargs = {}

        # Call the method
        epics_mixin.prepare_epic_fields(fields, summary, kwargs)

        # Verify only the color was stored in kwargs
        assert "__epic_name_value" not in kwargs
        assert "__epic_name_field" not in kwargs
        assert kwargs["__epic_color_value"] == "green"
        assert kwargs["__epic_color_field"] == "customfield_10010"

        # Verify fields dict remains empty
        assert fields == {}

    def test_prepare_epic_fields_with_error(self, epics_mixin):
        """Test prepare_epic_fields catches and logs errors."""
        # Mock get_jira_field_ids to raise an exception
        epics_mixin.get_jira_field_ids = MagicMock(side_effect=Exception("Field error"))

        # Create the fields dict and call the method
        fields = {}
        epics_mixin.prepare_epic_fields(fields, "Test Epic", {})

        # Verify that fields didn't get updated
        assert fields == {}
        # Verify the error was logged
        epics_mixin.get_jira_field_ids.assert_called_once()

    def test_prepare_epic_fields_with_non_standard_ids(self, epics_mixin):
        """Test that prepare_epic_fields correctly handles non-standard field IDs."""
        # Mock field IDs with non-standard custom field IDs
        mock_field_ids = {
            "epic_name": "customfield_54321",
            "epic_color": "customfield_98765",
        }

        # Mock the get_jira_field_ids method to return our custom field IDs
        epics_mixin.get_jira_field_ids = MagicMock(return_value=mock_field_ids)

        # Create the fields dict and call the method with basic values
        fields = {}
        kwargs = {}
        epics_mixin.prepare_epic_fields(fields, "Test Epic", kwargs)

        # Verify fields were stored in kwargs with the non-standard IDs
        assert kwargs["__epic_name_value"] == "Test Epic"
        assert kwargs["__epic_name_field"] == "customfield_54321"
        assert kwargs["__epic_color_value"] == "green"
        assert kwargs["__epic_color_field"] == "customfield_98765"

        # Verify fields dict remains empty
        assert fields == {}

        # Test with custom values
        fields = {}
        kwargs = {"epic_name": "Custom Name", "epic_color": "blue"}
        epics_mixin.prepare_epic_fields(fields, "Test Epic", kwargs)

        # Verify custom values were stored in kwargs
        assert kwargs["__epic_name_value"] == "Custom Name"
        assert kwargs["__epic_name_field"] == "customfield_54321"
        assert kwargs["__epic_color_value"] == "blue"
        assert kwargs["__epic_color_field"] == "customfield_98765"

        # Original values should be removed from kwargs
        assert "epic_name" not in kwargs
        assert "epic_color" not in kwargs

        # Verify fields dict remains empty
        assert fields == {}

    def test_dynamic_epic_field_discovery(self, epics_mixin):
        """Test the dynamic discovery of Epic fields with pattern matching."""
        # Mock get_jira_field_ids with no epic-related fields
        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={
                "random_field": "customfield_12345",
                "some_other_field": "customfield_67890",
                "Epic-FieldName": "customfield_11111",  # Should be found by pattern matching
                "epic_colour_field": "customfield_22222",  # Should be found by pattern matching
            }
        )

        # Create a fields dict and call prepare_epic_fields
        fields = {}
        kwargs = {}

        # The _get_epic_name_field_id and _get_epic_color_field_id methods should discover
        # the fields by pattern matching, even though they're not in the standard format

        # We need to patch these methods to return the expected values
        original_get_name = epics_mixin._get_epic_name_field_id
        original_get_color = epics_mixin._get_epic_color_field_id

        epics_mixin._get_epic_name_field_id = MagicMock(
            return_value="customfield_11111"
        )
        epics_mixin._get_epic_color_field_id = MagicMock(
            return_value="customfield_22222"
        )

        # Now call prepare_epic_fields
        epics_mixin.prepare_epic_fields(fields, "Test Epic Name", kwargs)

        # Verify the fields were stored in kwargs
        assert kwargs["__epic_name_value"] == "Test Epic Name"
        assert kwargs["__epic_name_field"] == "customfield_11111"
        assert kwargs["__epic_color_value"] == "green"
        assert kwargs["__epic_color_field"] == "customfield_22222"

        # Verify fields dict remains empty
        assert fields == {}

        # Restore the original methods
        epics_mixin._get_epic_name_field_id = original_get_name
        epics_mixin._get_epic_color_field_id = original_get_color

    def test_link_issue_to_epic_success(self, epics_mixin):
        """Test link_issue_to_epic with successful linking."""
        # Setup mocks
        # - issue exists
        epics_mixin.jira.get_issue.side_effect = [
            {"key": "TEST-123"},  # issue
            {  # epic
                "key": "EPIC-456",
                "fields": {"issuetype": {"name": "Epic"}},
            },
        ]

        # Mock get_issue to return a valid JiraIssue
        epics_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", id="123456")
        )

        # - epic link field discovered
        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014"}
        )

        # - Parent field fails, then epic_link succeeds
        epics_mixin.jira.update_issue.side_effect = [
            Exception("Parent field error"),  # First attempt fails
            None,  # Second attempt succeeds
        ]

        # Call the method
        result = epics_mixin.link_issue_to_epic("TEST-123", "EPIC-456")

        # Verify API calls - should have two calls, one for parent and one for epic_link
        assert epics_mixin.jira.update_issue.call_count == 2
        # First call should be with parent
        assert epics_mixin.jira.update_issue.call_args_list[0] == call(
            issue_key="TEST-123", update={"fields": {"parent": {"key": "EPIC-456"}}}
        )
        # Second call should be with epic_link field
        assert epics_mixin.jira.update_issue.call_args_list[1] == call(
            issue_key="TEST-123", update={"fields": {"customfield_10014": "EPIC-456"}}
        )

        # Verify get_issue was called to return the result
        epics_mixin.get_issue.assert_called_once_with("TEST-123")

        # Verify result
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"

    def test_link_issue_to_epic_parent_field_success(self, epics_mixin):
        """Test link_issue_to_epic succeeding with parent field."""
        # Setup mocks
        epics_mixin.jira.get_issue.side_effect = [
            {"key": "TEST-123"},  # issue
            {  # epic
                "key": "EPIC-456",
                "fields": {"issuetype": {"name": "Epic"}},
            },
        ]

        # Mock get_issue to return a valid JiraIssue
        epics_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", id="123456")
        )

        # - No epic_link field (forces parent usage)
        epics_mixin.get_jira_field_ids = MagicMock(return_value={})

        # Parent field update succeeds
        epics_mixin.jira.update_issue.return_value = None

        # Call the method
        result = epics_mixin.link_issue_to_epic("TEST-123", "EPIC-456")

        # Verify only one API call with parent field
        epics_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"parent": {"key": "EPIC-456"}}}
        )

        # Verify result
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"

    def test_link_issue_to_epic_not_epic(self, epics_mixin):
        """Test link_issue_to_epic when the target is not an epic."""
        # Setup mocks
        epics_mixin.jira.get_issue.side_effect = [
            {"key": "TEST-123"},  # issue
            {  # not an epic
                "key": "TEST-456",
                "fields": {"issuetype": {"name": "Task"}},
            },
        ]

        # Call the method and expect an error
        with pytest.raises(
            ValueError, match="Error linking issue to epic: TEST-456 is not an Epic"
        ):
            epics_mixin.link_issue_to_epic("TEST-123", "TEST-456")

    def test_link_issue_to_epic_all_methods_fail(self, epics_mixin):
        """Test link_issue_to_epic when all linking methods fail."""
        # Setup mocks
        epics_mixin.jira.get_issue.side_effect = [
            {"key": "TEST-123"},  # issue
            {  # epic
                "key": "EPIC-456",
                "fields": {"issuetype": {"name": "Epic"}},
            },
        ]

        # No epic link fields found
        epics_mixin.get_jira_field_ids = MagicMock(return_value={})

        # All update attempts fail
        epics_mixin.jira.update_issue.side_effect = Exception("Update failed")
        epics_mixin.jira.create_issue_link.side_effect = Exception("Link failed")

        # Call the method and expect a ValueError
        with pytest.raises(
            ValueError,
            match="Could not link issue TEST-123 to epic EPIC-456.",
        ):
            epics_mixin.link_issue_to_epic("TEST-123", "EPIC-456")

    def test_link_issue_to_epic_api_error(self, epics_mixin):
        """Test link_issue_to_epic with API error in the epic retrieval."""
        # Setup mocks to fail at epic retrieval
        epics_mixin.jira.get_issue.side_effect = [
            {"key": "TEST-123"},  # issue
            Exception("API error"),  # epic retrieval fails
        ]

        # Call the method and expect the API error to be propagated
        with pytest.raises(Exception, match="Error linking issue to epic: API error"):
            epics_mixin.link_issue_to_epic("TEST-123", "EPIC-456")

    def test_get_epic_issues_success(self, epics_mixin):
        """Test get_epic_issues with successful retrieval."""
        # Setup mocks
        epics_mixin.jira.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {"issuetype": {"name": "Epic"}},
        }

        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014"}
        )

        # Mock search_issues to return test data
        epics_mixin.search_issues = MagicMock(
            return_value=[
                JiraIssue(key="TEST-456", summary="Issue 1"),
                JiraIssue(key="TEST-789", summary="Issue 2"),
            ]
        )

        # Call the method
        result = epics_mixin.get_epic_issues("EPIC-123", limit=10)

        # Verify search_issues was called with the right JQL
        epics_mixin.search_issues.assert_called_once()
        call_args = epics_mixin.search_issues.call_args[0]
        assert 'issueFunction in issuesScopedToEpic("EPIC-123")' in call_args[0]

        # Verify keyword arguments for limit
        call_kwargs = epics_mixin.search_issues.call_args[1]
        assert call_kwargs.get("limit") == 10

        # Verify result
        assert len(result) == 2
        assert result[0].key == "TEST-456"
        assert result[1].key == "TEST-789"

    def test_get_epic_issues_not_epic(self, epics_mixin):
        """Test get_epic_issues when the issue is not an epic."""
        # Setup mocks - issue is not an epic
        epics_mixin.jira.get_issue.return_value = {
            "key": "TEST-123",
            "fields": {"issuetype": {"name": "Task"}},
        }

        # Call the method and expect an error
        with pytest.raises(
            ValueError, match="Issue TEST-123 is not an Epic, it is a Task"
        ):
            epics_mixin.get_epic_issues("TEST-123")

    def test_get_epic_issues_no_results(self, epics_mixin):
        """Test get_epic_issues when no results are found."""
        # Setup mocks
        epics_mixin.jira.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {"issuetype": {"name": "Epic"}},
        }

        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014"}
        )

        # Make search_issues return empty results
        epics_mixin.search_issues = MagicMock(return_value=[])

        # Call the method
        result = epics_mixin.get_epic_issues("EPIC-123")

        # Verify the result is an empty list
        assert isinstance(result, list)
        assert not result

    def test_get_epic_issues_fallback_jql(self, epics_mixin):
        """Test get_epic_issues with fallback JQL queries."""
        # Setup mocks
        epics_mixin.jira.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {"issuetype": {"name": "Epic"}},
        }

        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014", "parent": "parent"}
        )

        # Mock search_issues to return empty results for issueFunction but results for epic_link
        def search_side_effect(jql, **kwargs):
            if "issueFunction" in jql:
                return []  # No results for issueFunction
            elif "customfield_10014" in jql:
                # Return results for customfield query
                return [
                    JiraIssue(key="CHILD-1", summary="Child 1"),
                    JiraIssue(key="CHILD-2", summary="Child 2"),
                ]
            return []

        epics_mixin.search_issues = MagicMock(side_effect=search_side_effect)

        # Call the method
        result = epics_mixin.get_epic_issues("EPIC-123")

        # Verify we got results from the second query
        assert len(result) == 2
        assert result[0].key == "CHILD-1"
        assert result[1].key == "CHILD-2"

    def test_get_epic_issues_no_search_issues(self, epics_mixin):
        """Test get_epic_issues when search_issues method is not available."""
        # Setup mocks
        epics_mixin.jira.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {"issuetype": {"name": "Epic"}},
        }

        epics_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014"}
        )

        # Remove search_issues method
        delattr(epics_mixin, "search_issues")

        # Mock jql response
        mock_issues = [
            {"key": "TEST-456", "fields": {"summary": "Issue 1"}},
            {"key": "TEST-789", "fields": {"summary": "Issue 2"}},
        ]
        epics_mixin.jira.jql.return_value = {"issues": mock_issues}

        # Call the method
        result = epics_mixin.get_epic_issues("EPIC-123")

        # Verify the result contains documents created from jql results
        assert len(result) == 2
        assert result[0].key == "TEST-456"
        assert result[0].summary == "Issue 1"
        assert result[1].key == "TEST-789"
        assert result[1].summary == "Issue 2"

    def test_get_epic_issues_api_error(self, epics_mixin):
        """Test get_epic_issues with API error."""
        # Setup mocks - simulate API error
        epics_mixin.jira.get_issue.side_effect = Exception("API error")

        # Call the method and expect an error
        with pytest.raises(Exception, match="Error getting epic issues: API error"):
            epics_mixin.get_epic_issues("EPIC-123")
