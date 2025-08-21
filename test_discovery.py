#!/usr/bin/env python3
"""
Script to discover available test data in the configured Jira and Confluence instances.
This will help us set up proper test environment variables.
"""

import asyncio
import os
from dotenv import load_dotenv

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig

async def discover_jira_data():
    """Discover available Jira projects and issues."""
    try:
        print("🔍 Discovering Jira data...")
        config = JiraConfig.from_env()
        jira = JiraFetcher(config=config)
        
        # Get all projects
        projects = jira.get_all_projects()
        print(f"📋 Found {len(projects)} Jira projects:")
        
        test_projects = []
        for project in projects[:10]:  # Limit to first 10
            key = project.get('key', 'UNKNOWN')
            name = project.get('name', 'Unknown Project')
            print(f"  - {key}: {name}")
            test_projects.append(key)
        
        # Try to find issues in the first project
        if test_projects:
            first_project = test_projects[0]
            print(f"\n🎫 Looking for issues in project {first_project}...")
            
            search_result = jira.search_issues(
                jql=f'project = "{first_project}" ORDER BY created DESC',
                limit=5
            )
            
            if search_result.issues:
                print(f"📝 Found {len(search_result.issues)} recent issues:")
                for issue in search_result.issues:
                    print(f"  - {issue.key}: {issue.summary}")
                
                return {
                    'projects': test_projects,
                    'first_project': first_project,
                    'test_issue': search_result.issues[0].key,
                    'issues': [issue.key for issue in search_result.issues]
                }
            else:
                print("❌ No issues found in first project")
                return {'projects': test_projects, 'first_project': first_project}
        
        return {'projects': test_projects}
        
    except Exception as e:
        print(f"❌ Error discovering Jira data: {e}")
        return None

async def discover_confluence_data():
    """Discover available Confluence spaces and pages."""
    try:
        print("\n🔍 Discovering Confluence data...")
        config = ConfluenceConfig.from_env()
        confluence = ConfluenceFetcher(config=config)
        
        # Search for pages to find spaces
        search_result = confluence.search(
            cql='type = "page" ORDER BY created DESC',
            limit=10
        )
        
        spaces = set()
        pages = []
        
        print(f"📄 Found {len(search_result)} recent pages:")
        for page in search_result:
            if hasattr(page, 'space') and page.space:
                spaces.add(page.space.key)
                pages.append({'id': page.id, 'title': page.title, 'space': page.space.key})
                print(f"  - {page.id}: {page.title} (Space: {page.space.key})")
        
        return {
            'spaces': list(spaces),
            'pages': pages,
            'first_space': list(spaces)[0] if spaces else None,
            'test_page': pages[0]['id'] if pages else None
        }
        
    except Exception as e:
        print(f"❌ Error discovering Confluence data: {e}")
        return None

async def main():
    """Main discovery function."""
    load_dotenv()
    
    print("🚀 Starting data discovery for integration tests...")
    
    jira_data = await discover_jira_data()
    confluence_data = await discover_confluence_data()
    
    print("\n" + "="*60)
    print("📋 RECOMMENDED TEST ENVIRONMENT VARIABLES:")
    print("="*60)
    
    if jira_data:
        if 'first_project' in jira_data:
            print(f"JIRA_TEST_PROJECT_KEY={jira_data['first_project']}")
        if 'test_issue' in jira_data:
            print(f"JIRA_TEST_ISSUE_KEY={jira_data['test_issue']}")
        if len(jira_data.get('issues', [])) > 1:
            # Look for an Epic if possible
            print(f"JIRA_TEST_EPIC_KEY={jira_data['issues'][1]}")  # Use second issue as epic for now
    
    if confluence_data:
        if 'first_space' in confluence_data and confluence_data['first_space']:
            print(f"CONFLUENCE_TEST_SPACE_KEY={confluence_data['first_space']}")
        if 'test_page' in confluence_data and confluence_data['test_page']:
            print(f"CONFLUENCE_TEST_PAGE_ID={confluence_data['test_page']}")
    
    print("\n💡 Add these to your .env file to enable full integration testing")
    
    return jira_data, confluence_data

if __name__ == "__main__":
    asyncio.run(main())