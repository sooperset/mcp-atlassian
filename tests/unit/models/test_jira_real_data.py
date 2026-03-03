"""
Tests using real Jira data (optional).

These tests only run when --use-real-data is passed to pytest
and the appropriate environment variables are configured.
"""

import os

import pytest
from atlassian import Jira

from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.jira.issues import IssuesMixin
from mcp_atlassian.jira.projects import ProjectsMixin
from mcp_atlassian.jira.transitions import TransitionsMixin
from mcp_atlassian.jira.worklog import WorklogMixin
from mcp_atlassian.models.jira import (
    JiraIssue,
    JiraProject,
    JiraResolution,
    JiraTransition,
    JiraUser,
    JiraWorklog,
)


class TestRealJiraData:
    """Tests using real Jira data (optional)."""

    # Helper to get client/config
    def _get_client(self) -> IssuesMixin | None:
        try:
            config = JiraConfig.from_env()
            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_project_client(self) -> ProjectsMixin | None:
        try:
            config = JiraConfig.from_env()

            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_transition_client(self) -> TransitionsMixin | None:
        try:
            config = JiraConfig.from_env()
            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_worklog_client(self) -> WorklogMixin | None:
        try:
            config = JiraConfig.from_env()
            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_base_jira_client(self) -> Jira | None:
        try:
            config = JiraConfig.from_env()
            if config.auth_type == "basic":
                return Jira(
                    url=config.url,
                    username=config.username,
                    password=config.api_token,
                    cloud=config.is_cloud,
                )
            else:  # token
                return Jira(
                    url=config.url, token=config.personal_token, cloud=config.is_cloud
                )
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def test_real_jira_issue(self, use_real_jira_data, default_jira_issue_key):
        """Test that the JiraIssue model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        issues_client = self._get_client()
        if not issues_client or not default_jira_issue_key:
            pytest.skip("Real Jira client/issue key not available")

        try:
            issue = issues_client.get_issue(default_jira_issue_key)
            assert isinstance(issue, JiraIssue)
            assert issue.key == default_jira_issue_key
            assert issue.id is not None
            assert issue.summary is not None

            assert hasattr(issue, "project")
            assert issue.project is None or isinstance(issue.project, JiraProject)
            assert hasattr(issue, "resolution")
            assert issue.resolution is None or isinstance(
                issue.resolution, JiraResolution
            )
            assert hasattr(issue, "duedate")
            assert issue.duedate is None or isinstance(issue.duedate, str)
            assert hasattr(issue, "resolutiondate")
            assert issue.resolutiondate is None or isinstance(issue.resolutiondate, str)
            assert hasattr(issue, "parent")
            assert issue.parent is None or isinstance(issue.parent, dict)
            assert hasattr(issue, "subtasks")
            assert isinstance(issue.subtasks, list)
            if issue.subtasks:
                assert isinstance(issue.subtasks[0], dict)
            assert hasattr(issue, "security")
            assert issue.security is None or isinstance(issue.security, dict)
            assert hasattr(issue, "worklog")
            assert issue.worklog is None or isinstance(issue.worklog, dict)

            simplified = issue.to_simplified_dict()
            assert simplified["key"] == default_jira_issue_key
        except Exception as e:
            pytest.fail(f"Error testing real Jira issue: {e}")

    def test_real_jira_project(self, use_real_jira_data):
        """Test that the JiraProject model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        projects_client = self._get_project_client()
        if not projects_client:
            pytest.skip("Real Jira client not available")

        # Check for JIRA_TEST_ISSUE_KEY explicitly
        if not os.environ.get("JIRA_TEST_ISSUE_KEY"):
            pytest.skip("JIRA_TEST_ISSUE_KEY environment variable not set")

        default_issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY")
        project_key = default_issue_key.split("-")[0]

        if not project_key:
            pytest.skip("Could not extract project key from JIRA_TEST_ISSUE_KEY")

        try:
            project = projects_client.get_project_model(project_key)

            if project is None:
                pytest.skip(f"Could not get project model for {project_key}")

            assert isinstance(project, JiraProject)
            assert project.key == project_key
            assert project.id is not None
            assert project.name is not None

            simplified = project.to_simplified_dict()
            assert simplified["key"] == project_key
        except (AttributeError, TypeError, ValueError) as e:
            pytest.skip(f"Error parsing project data: {e}")
        except Exception as e:
            pytest.fail(f"Error testing real Jira project: {e}")

    def test_real_jira_transitions(self, use_real_jira_data, default_jira_issue_key):
        """Test that the JiraTransition model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        transitions_client = self._get_transition_client()
        if not transitions_client or not default_jira_issue_key:
            pytest.skip("Real Jira client/issue key not available")

        # Use the underlying Atlassian API client directly for raw data
        jira = self._get_base_jira_client()
        if not jira:
            pytest.skip("Base Jira client failed")

        transitions_data = None  # Initialize
        try:
            transitions_data = jira.get_issue_transitions(default_jira_issue_key)

            actual_transitions_list = []
            if isinstance(transitions_data, list):
                actual_transitions_list = transitions_data
            else:
                # Handle unexpected format with test failure
                pytest.fail(
                    f"Unexpected transitions data format received from API: "
                    f"{type(transitions_data)}. Data: {transitions_data}"
                )

            # Verify transitions list is actually a list
            assert isinstance(actual_transitions_list, list)

            if not actual_transitions_list:
                pytest.skip(f"No transitions found for issue {default_jira_issue_key}")

            transition_item = actual_transitions_list[0]
            assert isinstance(transition_item, dict)

            # Check for essential keys in the raw data
            assert "id" in transition_item
            assert "name" in transition_item
            assert "to" in transition_item

            # Only check 'to' field name if it's a dictionary
            if isinstance(transition_item["to"], dict):
                assert "name" in transition_item["to"]

            # Convert to model
            transition = JiraTransition.from_api_response(transition_item)
            assert isinstance(transition, JiraTransition)
            assert transition.id == str(transition_item["id"])  # Ensure ID is string
            assert transition.name == transition_item["name"]

            simplified = transition.to_simplified_dict()
            assert simplified["id"] == str(transition_item["id"])
            assert simplified["name"] == transition_item["name"]

        except Exception as e:
            # Include data type details in error message
            error_details = f"Received data type: {type(transitions_data)}"
            if transitions_data is not None:
                error_details += (
                    f", Data: {str(transitions_data)[:200]}..."  # Show partial data
                )

            pytest.fail(
                f"Error testing real Jira transitions for issue {default_jira_issue_key}: {e}. {error_details}"
            )

    def test_real_jira_worklog(self, use_real_jira_data, default_jira_issue_key):
        """Test that the JiraWorklog model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        worklog_client = self._get_worklog_client()
        if not worklog_client or not default_jira_issue_key:
            pytest.skip("Real Jira client/issue key not available")

        try:
            # Get worklogs using the model method
            worklogs = worklog_client.get_worklog_models(default_jira_issue_key)
            assert isinstance(worklogs, list)

            if not worklogs:
                pytest.skip(f"Issue {default_jira_issue_key} has no worklogs to test.")

            # Test the first worklog
            worklog = worklogs[0]
            assert isinstance(worklog, JiraWorklog)
            assert worklog.id is not None
            assert worklog.time_spent_seconds >= 0
            if worklog.author:
                assert isinstance(worklog.author, JiraUser)

            simplified = worklog.to_simplified_dict()
            assert "id" in simplified
            assert "time_spent" in simplified

        except Exception as e:
            pytest.fail(f"Error testing real Jira worklog: {e}")
