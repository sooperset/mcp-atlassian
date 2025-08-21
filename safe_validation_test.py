#!/usr/bin/env python3
"""
Safe read-only validation test to verify PAT token functionality
without any write operations to production systems.
"""

import asyncio
import os
import sys
from typing import Optional

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add the src directory to Python path
sys.path.insert(0, 'src')

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig


async def test_jira_read_operations() -> bool:
    """Test basic Jira read operations."""
    print("🔍 Testing Jira read operations...")
    
    try:
        # Initialize Jira client
        jira_config = JiraConfig.from_env()
        jira = JiraFetcher(config=jira_config)
        
        # Test 1: Get all projects (should work with any valid token)
        print("  ✓ Testing project access...")
        projects = jira.get_all_projects()
        print(f"    Found {len(projects)} accessible projects")
        
        # Test 2: Get specific issue using discovered test data
        issue_key = os.getenv('JIRA_TEST_ISSUE_KEY', 'MDR-197')
        print(f"  ✓ Testing issue access: {issue_key}")
        issue = jira.get_issue(issue_key)
        print(f"    Successfully retrieved issue: {issue.key} - {issue.summary}")
        
        # Test 3: Search functionality
        project_key = os.getenv('JIRA_TEST_PROJECT_KEY', 'MDR')
        print(f"  ✓ Testing search in project: {project_key}")
        search_result = jira.search_issues(f'project = "{project_key}"', limit=3)
        print(f"    Search returned {len(search_result.issues)} issues")
        
        # Test 4: Get issue fields
        print("  ✓ Testing field discovery...")
        fields = jira.get_fields()
        print(f"    Retrieved {len(fields)} field definitions")
        
        # Close not needed for this client type
        print("✅ All Jira read operations successful!")
        return True
        
    except Exception as e:
        print(f"❌ Jira test failed: {e}")
        return False


async def test_confluence_read_operations() -> bool:
    """Test basic Confluence read operations."""
    print("\n🔍 Testing Confluence read operations...")
    
    try:
        # Initialize Confluence client
        confluence_config = ConfluenceConfig.from_env()
        confluence = ConfluenceFetcher(config=confluence_config)
        
        # Test 1: Search content (using proper CQL)
        print("  ✓ Testing content search...")
        search_results = confluence.search('type = "page" AND space = "TEST"', limit=3)
        print(f"    Search returned {len(search_results)} results")
        
        # Test 2: Get specific page using discovered test data
        page_id = os.getenv('CONFLUENCE_TEST_PAGE_ID', '1062553061')
        print(f"  ✓ Testing page access: {page_id}")
        page = confluence.get_page_content(page_id)
        print(f"    Successfully retrieved page: {page.title}")
        
        # Test 3: Get page children (if any)
        print("  ✓ Testing page hierarchy access...")
        children = confluence.get_page_children(page_id, limit=5)
        print(f"    Page has {len(children)} child pages")
        
        # Test 4: Get page comments (if any)
        print("  ✓ Testing comment access...")
        comments = confluence.get_page_comments(page_id)
        print(f"    Page has {len(comments)} comments")
        
        # Close not needed for this client type
        print("✅ All Confluence read operations successful!")
        return True
        
    except Exception as e:
        print(f"❌ Confluence test failed: {e}")
        return False


async def main():
    """Run all safe validation tests."""
    print("🚀 Starting safe read-only validation tests...")
    print("📝 Using environment variables for test data:")
    print(f"    JIRA_TEST_PROJECT_KEY: {os.getenv('JIRA_TEST_PROJECT_KEY', 'MDR')}")
    print(f"    JIRA_TEST_ISSUE_KEY: {os.getenv('JIRA_TEST_ISSUE_KEY', 'MDR-197')}")
    print(f"    CONFLUENCE_TEST_SPACE_KEY: {os.getenv('CONFLUENCE_TEST_SPACE_KEY', 'TEST')}")
    print(f"    CONFLUENCE_TEST_PAGE_ID: {os.getenv('CONFLUENCE_TEST_PAGE_ID', '1062553061')}")
    print()
    
    # Run tests
    jira_success = await test_jira_read_operations()
    confluence_success = await test_confluence_read_operations()
    
    # Summary
    print("\n📊 Validation Summary:")
    print(f"  Jira Operations: {'✅ PASSED' if jira_success else '❌ FAILED'}")
    print(f"  Confluence Operations: {'✅ PASSED' if confluence_success else '❌ FAILED'}")
    
    if jira_success and confluence_success:
        print("\n🎉 All validation tests passed! PAT token is working correctly.")
        return 0
    else:
        print("\n⚠️  Some validation tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)