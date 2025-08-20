#!/usr/bin/env python3
"""
Test script to verify Jira development information retrieval.

Usage:
    python test_dev_info.py ISSUE-KEY

Requires environment variables:
    - JIRA_URL
    - JIRA_PERSONAL_TOKEN or (JIRA_USERNAME + JIRA_API_TOKEN)
"""

import os
import sys
import json
import logging
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_dev_info(issue_key):
    """Test getting development information for a Jira issue."""
    from mcp_atlassian.jira.config import JiraConfig
    from mcp_atlassian.jira.client import JiraClient
    
    print(f"\n=== Testing Development Information for {issue_key} ===")
    
    try:
        # Load config from environment
        config = JiraConfig.from_env()
        print(f"URL: {config.url}")
        print(f"Auth Type: {config.auth_type}")
        print(f"Is Cloud: {config.is_cloud}")
        
        # Create client
        client = JiraClient(config)
        
        # Get development information
        print(f"\nFetching development information for {issue_key}...")
        dev_info = client.get_development_information(issue_key)
        
        # Display results
        print(f"\n✅ Development Information Retrieved!")
        print(f"Summary: {dev_info.summary}")
        print(f"Has development info: {dev_info.has_development_info}")
        
        if dev_info.pull_requests:
            print(f"\n📋 Pull Requests ({len(dev_info.pull_requests)}):")
            for pr in dev_info.pull_requests[:5]:  # Show first 5
                status_emoji = "✅" if pr.is_merged else "🔄" if pr.is_open else "❌"
                print(f"  {status_emoji} [{pr.status}] {pr.title}")
                print(f"     Author: {pr.author}")
                print(f"     URL: {pr.url}")
                print(f"     {pr.source_branch} → {pr.destination_branch}")
        
        if dev_info.branches:
            print(f"\n🌿 Branches ({len(dev_info.branches)}):")
            for branch in dev_info.branches[:5]:  # Show first 5
                print(f"  - {branch.name}")
                print(f"    Repository: {branch.repository}")
                print(f"    URL: {branch.url}")
        
        if dev_info.commits:
            print(f"\n💾 Commits ({len(dev_info.commits)}):")
            for commit in dev_info.commits[:5]:  # Show first 5
                print(f"  - [{commit.short_id}] {commit.first_line_message}")
                print(f"    Author: {commit.author}")
                print(f"    Files changed: {commit.files_changed}")
        
        if dev_info.builds:
            print(f"\n🏗️ Builds ({len(dev_info.builds)}):")
            for build in dev_info.builds[:5]:  # Show first 5
                status_emoji = "✅" if build.is_successful else "❌" if build.is_failed else "🔄"
                print(f"  {status_emoji} [{build.status}] {build.name}")
                print(f"     URL: {build.url}")
        
        if dev_info.errors:
            print(f"\n⚠️ Errors encountered:")
            for error in dev_info.errors:
                print(f"  - {error}")
        
        # Export to JSON
        output_file = f"dev_info_{issue_key.replace('-', '_')}.json"
        with open(output_file, 'w') as f:
            json.dump(dev_info.to_dict(), f, indent=2)
        print(f"\n📁 Full details exported to: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to get development information: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    if len(sys.argv) < 2:
        print("Usage: python test_dev_info.py ISSUE-KEY")
        print("Example: python test_dev_info.py PROJ-123")
        sys.exit(1)
    
    issue_key = sys.argv[1]
    
    # Check configuration
    has_config = bool(
        os.getenv("JIRA_URL") and 
        (os.getenv("JIRA_PERSONAL_TOKEN") or 
         (os.getenv("JIRA_USERNAME") and os.getenv("JIRA_API_TOKEN")))
    )
    
    if not has_config:
        print("\n❌ No configuration found!")
        print("\nPlease set environment variables:")
        print("  For Server/DC with PAT:")
        print("    - JIRA_URL")
        print("    - JIRA_PERSONAL_TOKEN")
        print("  For Cloud with API Token:")
        print("    - JIRA_URL")
        print("    - JIRA_USERNAME")
        print("    - JIRA_API_TOKEN")
        sys.exit(1)
    
    success = test_dev_info(issue_key)
    
    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
