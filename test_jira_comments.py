#!/usr/bin/env python3
"""
Test script to verify the new jira_get_comments functionality.

Usage:
    python test_jira_comments.py <issue_key>

Requires environment variables:
    - JIRA_URL
    - JIRA_PERSONAL_TOKEN or (JIRA_USERNAME and JIRA_API_TOKEN)
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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_get_comments(issue_key: str):
    """Test the get_issue_comments functionality."""
    from mcp_atlassian.jira.config import JiraConfig
    from mcp_atlassian.jira.client import JiraClient
    from mcp_atlassian.jira.comments import CommentsMixin
    
    print(f"\n=== Testing jira_get_comments for {issue_key} ===")
    
    try:
        # Load config from environment
        config = JiraConfig.from_env()
        print(f"URL: {config.url}")
        print(f"Auth Type: {config.auth_type}")
        print(f"Is Cloud: {config.is_cloud}")
        
        # Create client (CommentsMixin inherits from JiraClient)
        client = CommentsMixin(config)
        
        # Test getting comments with different limits
        print(f"\n1. Getting first 5 comments for {issue_key}...")
        comments = client.get_issue_comments(issue_key=issue_key, limit=5)
        
        print(f"Found {len(comments)} comments (limited to 5)")
        
        if comments:
            print("\nComment details:")
            for i, comment in enumerate(comments, 1):
                print(f"\nComment {i}:")
                print(f"  ID: {comment.get('id')}")
                print(f"  Author: {comment.get('author')}")
                print(f"  Created: {comment.get('created')}")
                print(f"  Updated: {comment.get('updated')}")
                # Show first 200 chars of body
                body = comment.get('body', '')
                body_preview = body[:200] + "..." if len(body) > 200 else body
                print(f"  Body preview: {body_preview}")
        else:
            print("No comments found for this issue.")
        
        # Test with higher limit
        print(f"\n2. Getting all comments (up to 50) for {issue_key}...")
        all_comments = client.get_issue_comments(issue_key=issue_key, limit=50)
        print(f"Total comments found: {len(all_comments)}")
        
        # Test adding a comment (if not in read-only mode)
        if not os.getenv("ATLASSIAN_READ_ONLY", "").lower() in ["true", "1", "yes"]:
            print("\n3. Testing add_comment functionality...")
            test_comment = "Test comment from jira_get_comments test script.\n\n*This is a test comment with markdown*"
            
            try:
                new_comment = client.add_comment(issue_key, test_comment)
                print(f"✅ Successfully added comment with ID: {new_comment.get('id')}")
                print(f"   Author: {new_comment.get('author')}")
                print(f"   Created: {new_comment.get('created')}")
            except Exception as e:
                print(f"⚠️  Could not add test comment: {e}")
        else:
            print("\n3. Skipping add_comment test (read-only mode)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing comments: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_via_server_endpoint(issue_key: str):
    """Test the server endpoint directly."""
    print(f"\n=== Testing via Server Endpoint ===")
    
    try:
        # Import server components
        from mcp_atlassian.servers.jira import get_comments
        from mcp_atlassian.servers.context import MainAppContext
        from fastmcp import Context
        from mcp_atlassian.jira.config import JiraConfig
        
        # Create a mock context
        jira_config = JiraConfig.from_env()
        app_context = MainAppContext(
            full_jira_config=jira_config,
            full_confluence_config=None,
            read_only=False,
            enabled_tools=None
        )
        
        # Create FastMCP context
        class MockLifespanContext:
            def __init__(self):
                self.app_lifespan_context = app_context
        
        class MockRequestContext:
            def __init__(self):
                self.lifespan_context = {"app_lifespan_context": app_context}
        
        class MockContext(Context):
            def __init__(self):
                super().__init__(request_context=MockRequestContext())
        
        ctx = MockContext()
        
        # Test the endpoint
        print(f"Calling get_comments endpoint for {issue_key}...")
        
        # We need to make it async
        import asyncio
        result_json = asyncio.run(get_comments(ctx, issue_key=issue_key, limit=10))
        
        result = json.loads(result_json)
        print(f"Issue: {result.get('issue_key')}")
        print(f"Total comments: {result.get('total_comments')}")
        
        if result.get('comments'):
            print(f"\nFirst comment:")
            first = result['comments'][0]
            print(f"  Author: {first.get('author')}")
            print(f"  Created: {first.get('created')}")
            body_preview = first.get('body', '')[:100] + "..."
            print(f"  Body: {body_preview}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing server endpoint: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    if len(sys.argv) < 2:
        print("Usage: python test_jira_comments.py <issue_key>")
        print("Example: python test_jira_comments.py PROJ-123")
        sys.exit(1)
    
    issue_key = sys.argv[1]
    
    print("Jira Comments Functionality Test")
    print("=" * 50)
    
    # Check configuration
    has_jira = bool(os.getenv("JIRA_URL"))
    has_auth = bool(
        os.getenv("JIRA_PERSONAL_TOKEN") or 
        (os.getenv("JIRA_USERNAME") and os.getenv("JIRA_API_TOKEN"))
    )
    
    if not has_jira or not has_auth:
        print("\n❌ Missing configuration!")
        print("\nRequired environment variables:")
        print("  - JIRA_URL")
        print("  - JIRA_PERSONAL_TOKEN or (JIRA_USERNAME and JIRA_API_TOKEN)")
        sys.exit(1)
    
    success = True
    
    # Test direct client method
    success = test_get_comments(issue_key) and success
    
    # Test server endpoint
    success = test_via_server_endpoint(issue_key) and success
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
