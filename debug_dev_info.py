#!/usr/bin/env python3
"""
Debug script to test Jira development information API endpoints directly.
"""

import os
import sys
import json
import logging
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_raw_dev_endpoint(issue_key):
    """Test the raw development information endpoint."""
    from mcp_atlassian.jira.config import JiraConfig
    
    print(f"\n=== Testing Raw Development API for {issue_key} ===")
    
    try:
        # Load config from environment
        config = JiraConfig.from_env()
        print(f"URL: {config.url}")
        print(f"Auth Type: {config.auth_type}")
        print(f"Is Cloud: {config.is_cloud}")
        
        # Setup session
        session = requests.Session()
        
        # Configure authentication
        if config.auth_type == "pat":
            # For Server/DC with PAT
            session.headers['Authorization'] = f'Bearer {config.personal_token}'
        elif config.auth_type == "basic":
            # For basic auth
            session.auth = HTTPBasicAuth(config.username, config.api_token)
        
        # Test different endpoints
        endpoints_to_test = []
        
        if config.is_cloud:
            # Cloud endpoints
            print("\n[Cloud Instance Detected]")
            # First need to get issue ID for cloud
            issue_url = f"{config.url}/rest/api/3/issue/{issue_key}?fields=id"
            print(f"Getting issue ID from: {issue_url}")
            response = session.get(issue_url, verify=config.ssl_verify)
            if response.status_code == 200:
                issue_data = response.json()
                issue_id = issue_data.get('id')
                print(f"Issue ID: {issue_id}")
                endpoints_to_test.append(
                    (f"/rest/api/3/issue/{issue_id}/development", "Cloud Development API")
                )
            else:
                print(f"Failed to get issue ID: {response.status_code}")
        else:
            # Server/DC endpoints
            print("\n[Server/DC Instance Detected]")
            endpoints_to_test.extend([
                (f"/rest/dev-status/latest/issue/detail?issueId={issue_key}&applicationType=&dataType=pullrequest,branch,commit,repository", 
                 "Server/DC Dev Status API"),
                (f"/rest/dev-status/1.0/issue/detail?issueId={issue_key}&applicationType=&dataType=pullrequest,branch,commit,repository",
                 "Server/DC Dev Status API v1.0"),
            ])
        
        # Also try some alternative endpoints
        endpoints_to_test.extend([
            (f"/rest/api/2/issue/{issue_key}?expand=versionedRepresentations,names,schema,operations,editmeta,changelog,renderedFields",
             "Issue with expansions"),
            (f"/rest/devinfo/latest/issue/{issue_key}/detail",
             "Alternative DevInfo API"),
        ])
        
        # Test each endpoint
        for endpoint, description in endpoints_to_test:
            full_url = f"{config.url}{endpoint}"
            print(f"\n--- Testing: {description} ---")
            print(f"URL: {full_url}")
            
            try:
                response = session.get(full_url, verify=config.ssl_verify, timeout=10)
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    # Save to file for inspection
                    filename = f"debug_{issue_key}_{description.replace(' ', '_').replace('/', '_')}.json"
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=2)
                    print(f"✅ Success! Response saved to: {filename}")
                    
                    # Check if there's actual dev info
                    if isinstance(data, dict):
                        if 'detail' in data:
                            detail_count = len(data.get('detail', []))
                            print(f"   Found {detail_count} detail entries")
                            for detail in data.get('detail', []):
                                instances = detail.get('instances', [])
                                print(f"   - {len(instances)} instances")
                                for instance in instances:
                                    print(f"     * Type: {instance.get('type', 'Unknown')}")
                                    print(f"     * PRs: {len(instance.get('pullRequests', []))}")
                                    print(f"     * Branches: {len(instance.get('branches', []))}")
                                    print(f"     * Commits: {len(instance.get('commits', []))}")
                        elif '_links' in data:
                            print("   Cloud-style response detected")
                        else:
                            print(f"   Response has {len(data)} keys: {list(data.keys())[:5]}")
                elif response.status_code == 404:
                    print("❌ Not Found - endpoint may not be available")
                elif response.status_code == 401:
                    print("❌ Unauthorized - check authentication")
                elif response.status_code == 403:
                    print("❌ Forbidden - check permissions")
                else:
                    print(f"❌ Error: {response.text[:200]}")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Request failed: {e}")
            except json.JSONDecodeError:
                print(f"❌ Response is not JSON: {response.text[:200]}")
        
        # Try getting remote links as another source of dev info
        print(f"\n--- Testing: Remote Links ---")
        remote_links_url = f"{config.url}/rest/api/2/issue/{issue_key}/remotelink"
        response = session.get(remote_links_url, verify=config.ssl_verify)
        if response.status_code == 200:
            links = response.json()
            print(f"✅ Found {len(links)} remote links")
            for link in links[:3]:  # Show first 3
                print(f"   - {link.get('object', {}).get('title', 'No title')}")
                print(f"     URL: {link.get('object', {}).get('url', 'No URL')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    if len(sys.argv) < 2:
        print("Usage: python debug_dev_info.py ISSUE-KEY")
        print("Example: python debug_dev_info.py LQC-25567")
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
        print("    export JIRA_URL=https://jira.example.com")
        print("    export JIRA_PERSONAL_TOKEN=your_token_here")
        print("  For Cloud with API Token:")
        print("    export JIRA_URL=https://example.atlassian.net")
        print("    export JIRA_USERNAME=your_email@example.com")
        print("    export JIRA_API_TOKEN=your_api_token_here")
        sys.exit(1)
    
    success = test_raw_dev_endpoint(issue_key)
    
    if success:
        print("\n✅ Debug completed! Check the generated JSON files for details.")
    else:
        print("\n❌ Debug failed. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
