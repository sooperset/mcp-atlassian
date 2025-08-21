#!/usr/bin/env python3
"""Test script to verify issue ID retrieval."""

import os
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.client import JiraClient

def test_issue_id():
    """Test getting issue ID."""
    print("Testing issue ID retrieval...")
    
    # Load config from environment
    config = JiraConfig.from_env()
    print(f"URL: {config.url}")
    print(f"Is Cloud: {config.is_cloud}")
    
    # Create client
    client = JiraClient(config)
    
    # Test issue method
    issue_key = "LQC-25567"
    print(f"\nTesting with issue key: {issue_key}")
    
    # This is what the development.py code does
    issue = client.jira.issue(issue_key, fields="id")
    print(f"Type of issue: {type(issue)}")
    print(f"Issue keys: {issue.keys() if isinstance(issue, dict) else 'Not a dict'}")
    
    if isinstance(issue, dict):
        issue_id = issue.get("id")
        print(f"Issue ID: {issue_id}")
        
        # Now test the dev-status endpoint with the ID
        print(f"\nTesting dev-status endpoint with ID: {issue_id}")
        response = client.jira.get(
            "/rest/dev-status/latest/issue/detail",
            params={
                "issueId": issue_id,
                "applicationType": "",
                "dataType": "pullrequest,branch,commit,repository"
            }
        )
        print(f"Response keys: {response.keys()}")
        print(f"Detail count: {len(response.get('detail', []))}")
        print(f"Errors: {response.get('errors', [])}")
        
        # Also test summary
        print(f"\nTesting dev-status summary endpoint...")
        summary_response = client.jira.get(
            "/rest/dev-status/latest/issue/summary",
            params={"issueId": issue_id}
        )
        summary = summary_response.get('summary', {})
        pr_data = summary.get('pullrequest', {}).get('overall', {})
        repo_data = summary.get('repository', {}).get('overall', {})
        print(f"PRs: {pr_data.get('count', 0)} (Merged: {pr_data.get('details', {}).get('mergedCount', 0)}, Open: {pr_data.get('details', {}).get('openCount', 0)})")
        print(f"Commits: {repo_data.get('count', 0)}")
    else:
        print("ERROR: issue is not a dict!")
        print(f"Issue content: {issue}")

if __name__ == "__main__":
    test_issue_id()
