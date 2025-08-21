#!/usr/bin/env python3
"""
Simple test to check what the Jira dev-status endpoint returns.
This will help debug why the MCP tool is returning empty results.
"""

import os
import json
import requests
from requests.auth import HTTPBasicAuth

def test_simple():
    """Simple test of the dev-status endpoint."""
    
    # Get environment variables
    jira_url = os.getenv("JIRA_URL")
    pat = os.getenv("JIRA_PERSONAL_TOKEN")
    username = os.getenv("JIRA_USERNAME")
    api_token = os.getenv("JIRA_API_TOKEN")
    
    if not jira_url:
        print("JIRA_URL not set")
        return
    
    # Setup session
    session = requests.Session()
    
    # Configure auth
    if pat:
        print(f"Using PAT authentication")
        session.headers['Authorization'] = f'Bearer {pat}'
    elif username and api_token:
        print(f"Using basic auth with username: {username}")
        session.auth = HTTPBasicAuth(username, api_token)
    else:
        print("No authentication configured")
        return
    
    issue_key = "LQC-25567"
    
    # Test the dev-status endpoint
    endpoint = f"/rest/dev-status/latest/issue/detail"
    params = {
        "issueId": issue_key,
        "applicationType": "",
        "dataType": "pullrequest,branch,commit,repository"
    }
    
    full_url = f"{jira_url}{endpoint}"
    print(f"\nTesting: {full_url}")
    print(f"Params: {params}")
    
    try:
        response = session.get(full_url, params=params, verify=True, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response type: {type(data)}")
            
            # Save full response
            with open(f"raw_response_{issue_key}.json", 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Full response saved to: raw_response_{issue_key}.json")
            
            # Analyze response
            if isinstance(data, dict):
                print(f"\nResponse keys: {list(data.keys())}")
                
                if 'detail' in data:
                    detail = data['detail']
                    print(f"Detail entries: {len(detail)}")
                    
                    for i, item in enumerate(detail):
                        print(f"\nDetail [{i}]:")
                        print(f"  Keys: {list(item.keys())}")
                        
                        if 'instances' in item:
                            instances = item['instances']
                            print(f"  Instances: {len(instances)}")
                            
                            for j, instance in enumerate(instances):
                                print(f"  Instance [{j}]:")
                                print(f"    Type: {instance.get('type', 'Unknown')}")
                                print(f"    ID: {instance.get('id', 'Unknown')}")
                                print(f"    Name: {instance.get('name', 'Unknown')}")
                                
                                # Check for development data
                                prs = instance.get('pullRequests', [])
                                branches = instance.get('branches', [])
                                commits = instance.get('commits', [])
                                
                                print(f"    Pull Requests: {len(prs)}")
                                print(f"    Branches: {len(branches)}")
                                print(f"    Commits: {len(commits)}")
                                
                                # Show some PR details if present
                                for pr in prs[:2]:
                                    print(f"      PR: {pr.get('name', 'Unknown')} - {pr.get('status', 'Unknown')}")
                
                if 'errors' in data:
                    print(f"\nErrors: {data['errors']}")
        else:
            print(f"Error response: {response.text[:500]}")
            
    except Exception as e:
        print(f"Request failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple()
