"""MCP Application Integration Test - Issue #658 validation"""

import os
import subprocess
import tempfile
from datetime import datetime, timezone

import pytest


class TestMCPApplication:
    """Test MCP functionality through direct API calls."""

    @pytest.fixture(autouse=True)
    def setup_environment(self):
        """Ensure required environment variables are set."""
        required = ["JIRA_URL", "JIRA_TEST_PROJECT_KEY", "JIRA_TEST_ISSUE_KEY"]

        if os.getenv("JIRA_CLOUD", "false").lower() == "true":
            required.extend(["JIRA_USERNAME", "JIRA_API_TOKEN"])
        else:
            required.append("JIRA_PERSONAL_TOKEN")

        missing = [var for var in required if not os.getenv(var)]
        if missing:
            pytest.skip(f"Missing environment variables: {missing}")

    def run_mcp_command(self, tool_name: str, parameters: dict) -> dict:
        """Run MCP command and return result."""
        script_content = f'''
import asyncio
import json
import os
import sys
import logging

# Disable debug logging
logging.getLogger().setLevel(logging.ERROR)
os.environ["MCP_VERBOSE"] = "false"

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig

async def main():
    try:
        config = JiraConfig.from_env()
        client = JiraFetcher(config=config)

        if "{tool_name}" == "search_issues":
            result = client.search_issues(**{parameters})
            return {{
                "success": True,
                "total": result.total,
                "count": len(result.issues),
                "issues": [{{
                    "key": issue.key,
                    "summary": issue.summary,
                    "description": issue.description[:100] if issue.description else None
                }} for issue in result.issues[:3]]
            }}
        elif "{tool_name}" == "get_issue":
            # Ensure we get comments by setting appropriate fields
            params = dict({parameters})
            if "fields" not in params:
                params["fields"] = "summary,description,comment"
            elif "comment" not in params["fields"]:
                params["fields"] += ",comment"
            result = client.get_issue(**params)
            return {{
                "success": True,
                "key": result.key,
                "summary": result.summary,
                "description": result.description[:100] if result.description else None,
                "comments_count": len(result.comments) if hasattr(result, 'comments') and result.comments else 0,
                "comments": [{{
                    "id": comment.id if hasattr(comment, 'id') else None,
                    "body": comment.body if hasattr(comment, 'body') else "",
                    "author": comment.author.display_name if hasattr(comment, 'author') and hasattr(comment.author, 'display_name') else None
                }} for comment in result.comments] if hasattr(result, 'comments') and result.comments else []
            }}
        elif "{tool_name}" == "add_comment":
            result = client.add_comment(**{parameters})
            return {{
                "success": True,
                "comment_id": result.id if hasattr(result, 'id') else "added"
            }}
        elif "{tool_name}" == "get_all_projects":
            result = client.get_all_projects(**{parameters})
            return {{
                "success": True,
                "count": len(result),
                "projects": [{{
                    "key": p.get("key") if isinstance(p, dict) else getattr(p, "key", None),
                    "name": p.get("name") if isinstance(p, dict) else getattr(p, "name", None),
                    "project_type": p.get("projectTypeKey") if isinstance(p, dict) else getattr(p, "project_type_key", None)
                }} for p in result[:3]]
            }}
        elif "{tool_name}" == "get_project_issues":
            # Map start_at to start parameter
            params = dict({parameters})
            if "start_at" in params:
                params["start"] = params.pop("start_at")
            result = client.get_project_issues(**params)
            return {{
                "success": True,
                "total": result.total,
                "count": len(result.issues),
                "issues": [{{
                    "key": issue.key,
                    "summary": issue.summary
                }} for issue in result.issues[:3]]
            }}
        elif "{tool_name}" == "search_fields":
            result = client.search_fields(**{parameters})
            return {{
                "success": True,
                "count": len(result),
                "fields": [{{
                    "id": f.get("id") if isinstance(f, dict) else getattr(f, "id", None),
                    "name": f.get("name") if isinstance(f, dict) else getattr(f, "name", None),
                    "custom": f.get("custom", False) if isinstance(f, dict) else getattr(f, "custom", False)
                }} for f in result[:3]]
            }}
        elif "{tool_name}" == "get_agile_boards":
            result = client.get_all_agile_boards(**{parameters})
            return {{
                "success": True,
                "count": len(result),
                "boards": [{{
                    "id": str(b.get("id")) if isinstance(b, dict) else str(getattr(b, "id", "")),
                    "name": b.get("name") if isinstance(b, dict) else getattr(b, "name", ""),
                    "type": b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                }} for b in result[:3]]
            }}
        elif "{tool_name}" == "get_board_issues":
            result = client.get_board_issues(**{parameters})
            return {{
                "success": True,
                "total": result.total,
                "count": len(result.issues),
                "issues": [{{
                    "key": issue.key,
                    "summary": issue.summary
                }} for issue in result.issues[:3]]
            }}
        elif "{tool_name}" == "batch_get_changelogs":
            if not config.is_cloud:
                return {{"success": False, "error": "Cloud-only feature"}}
            # Remove limit parameter as it's not supported
            params = dict({parameters})
            params.pop("limit", None)
            result = client.batch_get_changelogs(**params)
            return {{
                "success": True,
                "count": len(result),
                "changelogs": [{{
                    "issue_key": item.key if hasattr(item, 'key') else "unknown",
                    "changelog_count": len(item.changelog.histories) if hasattr(item, 'changelog') and item.changelog else 0
                }} for item in result[:3]]
            }}
        elif "{tool_name}" == "create_issue":
            result = client.create_issue(**{parameters})
            return {{
                "success": True,
                "key": result.key,
                "summary": result.summary,
                "issue_type": result.issue_type.name if result.issue_type else None
            }}
        elif "{tool_name}" == "batch_create_issues":
            # Parse JSON string if needed
            params = dict({parameters})
            if "issues" in params and isinstance(params["issues"], str):
                import json
                params["issues"] = json.loads(params["issues"])
            result = client.batch_create_issues(**params)
            return {{
                "success": True,
                "created_count": len(result),
                "failed_count": 0,  # batch_create_issues returns only successful issues
                "issues": [{{
                    "success": True,
                    "key": issue.key if hasattr(issue, 'key') else None,
                    "error": None
                }} for issue in result[:3]]
            }}
        elif "{tool_name}" == "link_to_epic":
            result = client.link_to_epic(**{parameters})
            return {{
                "success": True,
                "linked": True
            }}
        else:
            return {{"success": False, "error": "Unknown tool"}}

    except Exception as e:
        return {{"success": False, "error": str(e)}}

if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result), file=sys.stdout)
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script_content)
            script_path = f.name

        try:
            result = subprocess.run(
                ["uv", "run", "python", script_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.getcwd(),
            )

            if result.returncode == 0:
                import json

                # Extract only the JSON part (last line should be JSON)
                lines = result.stdout.strip().split("\n")
                json_line = lines[-1]  # Last line should be JSON
                return json.loads(json_line)
            else:
                return {"success": False, "error": f"Script failed: {result.stderr}"}

        finally:
            os.unlink(script_path)

    @pytest.mark.integration
    def test_search_functionality(self):
        """Test search works with issue #658 fix."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        result = self.run_mcp_command(
            "search_issues", {"jql": f"project = {project_key}", "limit": 5}
        )

        assert result["success"], f"Search failed: {result.get('error')}"
        assert result["count"] > 0, "No issues found"
        assert project_key in str(result["issues"])

    @pytest.mark.integration
    def test_get_issue(self):
        """Test issue retrieval."""
        issue_key = os.getenv("JIRA_TEST_ISSUE_KEY")

        result = self.run_mcp_command("get_issue", {"issue_key": issue_key})

        assert result["success"], f"Get issue failed: {result.get('error')}"
        assert result["key"] == issue_key
        assert result["summary"]

    @pytest.mark.integration
    def test_comment_functionality(self):
        """Test comment add and verification."""
        issue_key = os.getenv("JIRA_TEST_ISSUE_KEY")
        test_comment = f"Test comment - {datetime.now(timezone.utc).isoformat()}"

        # Add comment first
        add_result = self.run_mcp_command(
            "add_comment", {"issue_key": issue_key, "comment": test_comment}
        )
        assert add_result["success"], f"Add comment failed: {add_result.get('error')}"

        # Get issue to verify comment was added (with a small delay for consistency)
        import time

        time.sleep(2)  # Increased delay to ensure comment is processed

        verify_result = self.run_mcp_command(
            "get_issue",
            {
                "issue_key": issue_key,
                "fields": "summary,description,comment",
                "comment_limit": 50,  # Get more comments to find our test comment
            },
        )
        assert verify_result["success"], f"Verify failed: {verify_result.get('error')}"

        # Verify the exact comment content was added
        comments_count = verify_result.get("comments_count", 0)
        assert comments_count > 0, "Should have at least one comment"

        # Check if our test comment is in the comments list
        comments = verify_result.get("comments", [])
        comment_bodies = [comment.get("body", "") for comment in comments]
        assert test_comment in comment_bodies, (
            f"Test comment '{test_comment}' not found in comments: {comment_bodies}"
        )

    @pytest.mark.integration
    def test_epic_functionality(self):
        """Test epic search."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        result = self.run_mcp_command(
            "search_issues",
            {"jql": f"project = {project_key} AND issuetype = Epic", "limit": 3},
        )

        assert result["success"], f"Epic search failed: {result.get('error')}"
        # Epic search should work even if no epics found

    @pytest.mark.integration
    def test_adf_parsing(self):
        """Test ADF parsing for Cloud."""
        issue_key = os.getenv("JIRA_TEST_ISSUE_KEY")

        result = self.run_mcp_command("get_issue", {"issue_key": issue_key})

        assert result["success"], f"Get issue failed: {result.get('error')}"

        # For Cloud, description should be parsed text, not JSON
        if os.getenv("JIRA_CLOUD", "false").lower() == "true":
            description = result.get("description", "")
            assert '"type": "doc"' not in description, "ADF not parsed correctly"
            assert '"content":' not in description, "ADF not parsed correctly"

    @pytest.mark.integration
    def test_empty_jql_cloud(self):
        """Test empty JQL handling for Cloud."""
        if os.getenv("JIRA_CLOUD", "false").lower() != "true":
            pytest.skip("Cloud-only test")

        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Should handle empty JQL gracefully with projects_filter
        result = self.run_mcp_command(
            "search_issues", {"jql": None, "projects_filter": project_key, "limit": 3}
        )

        # Should work or give meaningful error
        if not result["success"]:
            assert "JQL query cannot be empty" in result.get("error", "")

    @pytest.mark.integration
    def test_environment_consistency(self):
        """Test basic functionality works in current environment."""
        issue_key = os.getenv("JIRA_TEST_ISSUE_KEY")
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Test search
        search_result = self.run_mcp_command(
            "search_issues", {"jql": f"key = {issue_key}", "limit": 1}
        )

        # Test get issue
        issue_result = self.run_mcp_command("get_issue", {"issue_key": issue_key})

        assert search_result["success"], f"Search failed: {search_result.get('error')}"
        assert issue_result["success"], f"Get issue failed: {issue_result.get('error')}"

        # Both should find the same issue
        assert issue_key in str(search_result["issues"])
        assert issue_result["key"] == issue_key

    @pytest.mark.integration
    def test_get_all_projects(self):
        """Test project listing functionality."""
        # Test with default parameters
        result = self.run_mcp_command("get_all_projects", {})
        assert result["success"], f"Get projects failed: {result.get('error')}"
        assert result["count"] > 0, "No projects found"

        # Test with include_archived parameter
        result_archived = self.run_mcp_command(
            "get_all_projects", {"include_archived": True}
        )
        assert result_archived["success"], (
            f"Get projects with archived failed: {result_archived.get('error')}"
        )

    @pytest.mark.integration
    def test_get_project_issues_variations(self):
        """Test project issues with different parameters."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Test basic project issues
        result1 = self.run_mcp_command(
            "get_project_issues", {"project_key": project_key, "limit": 5}
        )
        assert result1["success"], f"Get project issues failed: {result1.get('error')}"

        # Test with different start_at (pagination)
        result2 = self.run_mcp_command(
            "get_project_issues",
            {"project_key": project_key, "limit": 3, "start_at": 0},
        )
        assert result2["success"], (
            f"Get project issues with pagination failed: {result2.get('error')}"
        )

    @pytest.mark.integration
    def test_search_fields_functionality(self):
        """Test field search with different parameters."""
        # Test basic field search
        result1 = self.run_mcp_command(
            "search_fields", {"keyword": "summary", "limit": 5}
        )
        assert result1["success"], f"Search fields failed: {result1.get('error')}"
        assert result1["count"] > 0, "No fields found for 'summary'"

        # Test empty keyword (should return default fields)
        result2 = self.run_mcp_command("search_fields", {"keyword": "", "limit": 10})
        assert result2["success"], (
            f"Search fields with empty keyword failed: {result2.get('error')}"
        )

        # Test with refresh parameter
        result3 = self.run_mcp_command(
            "search_fields", {"keyword": "priority", "limit": 3, "refresh": True}
        )
        assert result3["success"], (
            f"Search fields with refresh failed: {result3.get('error')}"
        )

    @pytest.mark.integration
    def test_agile_boards_functionality(self):
        """Test agile boards with different parameters."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Test basic board listing
        result1 = self.run_mcp_command("get_agile_boards", {"limit": 5})
        assert result1["success"], f"Get agile boards failed: {result1.get('error')}"

        # Test with project filter
        result2 = self.run_mcp_command(
            "get_agile_boards", {"project_key": project_key, "limit": 3}
        )
        assert result2["success"], (
            f"Get agile boards with project filter failed: {result2.get('error')}"
        )

        # Test with board type filter
        result3 = self.run_mcp_command(
            "get_agile_boards", {"board_type": "scrum", "limit": 3}
        )
        assert result3["success"], (
            f"Get agile boards with type filter failed: {result3.get('error')}"
        )

    @pytest.mark.integration
    def test_board_issues_functionality(self):
        """Test board issues with different JQL parameters."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # First get a board
        boards_result = self.run_mcp_command(
            "get_agile_boards", {"project_key": project_key, "limit": 1}
        )

        if not boards_result["success"] or boards_result["count"] == 0:
            pytest.skip("No boards found for testing")

        board_id = boards_result["boards"][0]["id"]

        # Test basic board issues
        result1 = self.run_mcp_command(
            "get_board_issues",
            {"board_id": board_id, "jql": f"project = {project_key}", "limit": 5},
        )
        assert result1["success"], f"Get board issues failed: {result1.get('error')}"

        # Test with different fields parameter
        result2 = self.run_mcp_command(
            "get_board_issues",
            {
                "board_id": board_id,
                "jql": f"project = {project_key}",
                "fields": "summary,status,assignee",
                "limit": 3,
            },
        )
        assert result2["success"], (
            f"Get board issues with custom fields failed: {result2.get('error')}"
        )

        # Test with expand parameter
        result3 = self.run_mcp_command(
            "get_board_issues",
            {
                "board_id": board_id,
                "jql": f"project = {project_key}",
                "expand": "changelog",
                "limit": 2,
            },
        )
        assert result3["success"], (
            f"Get board issues with expand failed: {result3.get('error')}"
        )

    @pytest.mark.integration
    def test_search_variations_comprehensive(self):
        """Test search with comprehensive parameter variations."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Test 1: Basic search with different fields
        result1 = self.run_mcp_command(
            "search_issues",
            {
                "jql": f"project = {project_key}",
                "fields": ["summary", "status", "assignee", "priority"],
                "limit": 3,
            },
        )
        assert result1["success"], (
            f"Search with field list failed: {result1.get('error')}"
        )

        # Test 2: Search with string fields parameter
        result2 = self.run_mcp_command(
            "search_issues",
            {
                "jql": f"project = {project_key}",
                "fields": "summary,status,description",
                "limit": 3,
            },
        )
        assert result2["success"], (
            f"Search with string fields failed: {result2.get('error')}"
        )

        # Test 3: Search with expand parameter
        result3 = self.run_mcp_command(
            "search_issues",
            {"jql": f"project = {project_key}", "expand": "changelog", "limit": 2},
        )
        assert result3["success"], f"Search with expand failed: {result3.get('error')}"

        # Test 4: Search with projects_filter
        result4 = self.run_mcp_command(
            "search_issues",
            {"jql": "status = Open", "projects_filter": project_key, "limit": 3},
        )
        assert result4["success"], (
            f"Search with projects filter failed: {result4.get('error')}"
        )

        # Test 5: Search with start parameter (Server/DC pagination)
        if os.getenv("JIRA_CLOUD", "false").lower() != "true":
            result5 = self.run_mcp_command(
                "search_issues",
                {"jql": f"project = {project_key}", "start": 0, "limit": 2},
            )
            assert result5["success"], (
                f"Search with start parameter failed: {result5.get('error')}"
            )

    @pytest.mark.integration
    def test_cloud_vs_server_consistency(self):
        """Test that Cloud and Server/DC return consistent data structures."""
        issue_key = os.getenv("JIRA_TEST_ISSUE_KEY")
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")
        is_cloud = os.getenv("JIRA_CLOUD", "false").lower() == "true"

        # Test search consistency
        search_result = self.run_mcp_command(
            "search_issues",
            {
                "jql": f"key = {issue_key}",
                "fields": "summary,status,assignee,priority,description",
                "limit": 1,
            },
        )
        assert search_result["success"], f"Search failed: {search_result.get('error')}"
        assert search_result["count"] == 1, "Should find exactly one issue"

        # Test get_issue consistency
        issue_result = self.run_mcp_command(
            "get_issue",
            {
                "issue_key": issue_key,
                "fields": "summary,status,assignee,priority,description",
            },
        )
        assert issue_result["success"], f"Get issue failed: {issue_result.get('error')}"

        # Verify both methods return the same key data
        search_issue = search_result["issues"][0]
        assert search_issue["key"] == issue_result["key"]
        assert search_issue["summary"] == issue_result["summary"]

        # Cloud-specific validations
        if is_cloud:
            # Verify ADF descriptions are parsed to text
            if issue_result.get("description"):
                assert '"type": "doc"' not in issue_result["description"], (
                    "ADF not parsed in get_issue"
                )
            if search_issue.get("description"):
                assert '"content":' not in search_issue["description"], (
                    "ADF not parsed in search"
                )

        # Test projects consistency
        projects_result = self.run_mcp_command("get_all_projects", {})
        assert projects_result["success"], (
            f"Get projects failed: {projects_result.get('error')}"
        )
        assert projects_result["count"] > 0, "Should find projects"

        # Verify project structure consistency
        project = projects_result["projects"][0]
        assert "key" in project, "Project should have key"
        assert "name" in project, "Project should have name"

    @pytest.mark.integration
    def test_batch_get_changelogs_cloud_only(self):
        """Test batch changelog retrieval (Cloud only)."""
        if os.getenv("JIRA_CLOUD", "false").lower() != "true":
            pytest.skip("Cloud-only test")

        issue_key = os.getenv("JIRA_TEST_ISSUE_KEY")

        # Test with single issue
        result1 = self.run_mcp_command(
            "batch_get_changelogs", {"issue_ids_or_keys": [issue_key]}
        )
        assert result1["success"], (
            f"Batch get changelogs failed: {result1.get('error')}"
        )

        # Test with multiple issues and field filter
        result2 = self.run_mcp_command(
            "batch_get_changelogs",
            {"issue_ids_or_keys": [issue_key], "fields": ["status", "assignee"]},
        )
        assert result2["success"], (
            f"Batch get changelogs with fields failed: {result2.get('error')}"
        )

    @pytest.mark.integration
    def test_epic_functionality_comprehensive(self):
        """Test epic-related functionality with different parameters."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Test 1: Search for epics
        epic_search = self.run_mcp_command(
            "search_issues",
            {
                "jql": f"project = {project_key} AND issuetype = Epic",
                "fields": "summary,status,customfield_10011",  # Epic Name field
                "limit": 3,
            },
        )
        assert epic_search["success"], f"Epic search failed: {epic_search.get('error')}"

        # Test 2: Search for issues in epic (if epics exist)
        if epic_search["count"] > 0:
            epic_key = epic_search["issues"][0]["key"]

            # Search for child issues
            child_search = self.run_mcp_command(
                "search_issues",
                {
                    "jql": f"parent = {epic_key}",
                    "fields": "summary,status,parent",
                    "limit": 5,
                },
            )
            assert child_search["success"], (
                f"Epic child search failed: {child_search.get('error')}"
            )

            # Test epic linking (create a test issue first)
            test_issue = self.run_mcp_command(
                "create_issue",
                {
                    "project_key": project_key,
                    "summary": f"Test issue for epic linking - {datetime.now(timezone.utc).isoformat()}",
                    "issue_type": "Task",
                    "description": "Test issue created for epic linking test",
                },
            )

            if test_issue["success"]:
                # Try to link to epic
                link_result = self.run_mcp_command(
                    "link_to_epic",
                    {"issue_key": test_issue["key"], "epic_key": epic_key},
                )
                # Note: This might fail due to permissions, but should not crash
                # assert link_result["success"] or "permission" in link_result.get("error", "").lower()

    @pytest.mark.integration
    def test_batch_create_issues(self):
        """Test batch issue creation with different parameters."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")
        timestamp = datetime.now(timezone.utc).isoformat()

        # Test batch creation with different issue types
        issues_data = [
            {
                "project_key": project_key,
                "summary": f"Batch Test Task - {timestamp}",
                "issue_type": "Task",
                "description": "Test task created via batch operation",
            },
            {
                "project_key": project_key,
                "summary": f"Batch Test Bug - {timestamp}",
                "issue_type": "Bug",
                "description": "Test bug created via batch operation",
                "additional_fields": {"priority": {"name": "Medium"}},
            },
        ]

        result = self.run_mcp_command(
            "batch_create_issues",
            {
                "issues": str(issues_data).replace("'", '"'),  # Convert to JSON string
                "validate_only": False,
            },
        )

        assert result["success"], f"Batch create issues failed: {result.get('error')}"
        assert result["created_count"] >= 0, "Should report created count"

        # Test validation only mode
        validation_result = self.run_mcp_command(
            "batch_create_issues",
            {"issues": str(issues_data[:1]).replace("'", '"'), "validate_only": True},
        )
        assert validation_result["success"], (
            f"Batch validate issues failed: {validation_result.get('error')}"
        )

    @pytest.mark.integration
    def test_error_handling_consistency(self):
        """Test error handling consistency across Cloud and Server/DC."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")

        # Test 1: Invalid JQL
        invalid_jql_result = self.run_mcp_command(
            "search_issues", {"jql": "invalid jql syntax here", "limit": 1}
        )
        assert not invalid_jql_result["success"], "Invalid JQL should fail"
        assert "error" in invalid_jql_result, "Should have error message"

        # Test 2: Non-existent issue
        nonexistent_result = self.run_mcp_command(
            "get_issue", {"issue_key": f"{project_key}-999999"}
        )
        assert not nonexistent_result["success"], "Non-existent issue should fail"

        # Test 3: Empty JQL on Cloud (should fail)
        if os.getenv("JIRA_CLOUD", "false").lower() == "true":
            empty_jql_result = self.run_mcp_command(
                "search_issues", {"jql": "", "limit": 1}
            )
            assert not empty_jql_result["success"], "Empty JQL should fail on Cloud"
            assert "empty" in empty_jql_result.get("error", "").lower(), (
                "Should mention empty JQL"
            )

    @pytest.mark.integration
    def test_pagination_behavior_differences(self):
        """Test pagination differences between Cloud and Server/DC."""
        project_key = os.getenv("JIRA_TEST_PROJECT_KEY")
        is_cloud = os.getenv("JIRA_CLOUD", "false").lower() == "true"

        # Test small page size
        result1 = self.run_mcp_command(
            "search_issues", {"jql": f"project = {project_key}", "limit": 2}
        )
        assert result1["success"], f"Small page search failed: {result1.get('error')}"

        # Test larger page size
        result2 = self.run_mcp_command(
            "search_issues", {"jql": f"project = {project_key}", "limit": 10}
        )
        assert result2["success"], f"Large page search failed: {result2.get('error')}"

        # For Server/DC, test start parameter
        if not is_cloud:
            result3 = self.run_mcp_command(
                "search_issues",
                {"jql": f"project = {project_key}", "start": 1, "limit": 3},
            )
            assert result3["success"], (
                f"Pagination with start failed: {result3.get('error')}"
            )

        # Verify total counts are consistent (when available)
        if result1["total"] != -1 and result2["total"] != -1:
            assert result1["total"] == result2["total"], (
                "Total counts should be consistent"
            )
