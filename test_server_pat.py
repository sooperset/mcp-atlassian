#!/usr/bin/env python3
"""
Test script to verify Atlassian Server/DC PAT authentication.

Usage:
    python test_server_pat.py

Requires environment variables:
    - JIRA_URL or CONFLUENCE_URL
    - JIRA_PERSONAL_TOKEN or CONFLUENCE_PERSONAL_TOKEN
"""

import os
import sys
import logging
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_jira_pat():
    """Test Jira Server/DC PAT authentication."""
    from mcp_atlassian.jira.config import JiraConfig
    from mcp_atlassian.jira.client import JiraClient
    
    print("\n=== Testing Jira PAT Authentication ===")
    
    try:
        # Load config from environment
        config = JiraConfig.from_env()
        print(f"URL: {config.url}")
        print(f"Auth Type: {config.auth_type}")
        print(f"Is Cloud: {config.is_cloud}")
        
        # Create client
        client = JiraClient(config)
        
        # Test authentication
        print("\nTesting authentication...")
        user_info = client.jira.myself()
        
        print(f"✅ Authentication successful!")
        print(f"User: {user_info.get('displayName', 'Unknown')}")
        print(f"Email: {user_info.get('emailAddress', 'No email')}")
        
        # Test fetching projects
        print("\nFetching projects...")
        projects = client.jira.projects()
        print(f"Found {len(projects)} projects")
        if projects:
            print(f"First project: {projects[0].get('key')} - {projects[0].get('name')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_confluence_pat():
    """Test Confluence Server/DC PAT authentication."""
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.confluence.client import ConfluenceClient
    
    print("\n=== Testing Confluence PAT Authentication ===")
    
    try:
        # Load config from environment
        config = ConfluenceConfig.from_env()
        print(f"URL: {config.url}")
        print(f"Auth Type: {config.auth_type}")
        print(f"Is Cloud: {config.is_cloud}")
        
        # Create client
        client = ConfluenceClient(config)
        
        # Test authentication
        print("\nTesting authentication...")
        spaces = client.confluence.get_all_spaces(start=0, limit=1)
        
        print(f"✅ Authentication successful!")
        print(f"API call returned {len(spaces.get('results', []))} spaces")
        
        if spaces.get('results'):
            first_space = spaces['results'][0]
            print(f"First space: {first_space.get('key')} - {first_space.get('name')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    print("Atlassian Server/DC PAT Authentication Test")
    print("=" * 50)
    
    # Check which service to test
    has_jira = bool(os.getenv("JIRA_URL") and os.getenv("JIRA_PERSONAL_TOKEN"))
    has_confluence = bool(os.getenv("CONFLUENCE_URL") and os.getenv("CONFLUENCE_PERSONAL_TOKEN"))
    
    if not has_jira and not has_confluence:
        print("\n❌ No configuration found!")
        print("\nPlease set environment variables:")
        print("  For Jira:")
        print("    - JIRA_URL")
        print("    - JIRA_PERSONAL_TOKEN")
        print("  For Confluence:")
        print("    - CONFLUENCE_URL")
        print("    - CONFLUENCE_PERSONAL_TOKEN")
        sys.exit(1)
    
    success = True
    
    if has_jira:
        success = test_jira_pat() and success
    
    if has_confluence:
        success = test_confluence_pat() and success
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
