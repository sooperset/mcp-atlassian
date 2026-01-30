#!/usr/bin/env python3
"""Simple test script to verify Bitbucket implementation."""

import sys


def test_imports():
    """Test that all Bitbucket modules can be imported."""
    print("Testing imports...")

    try:
        from mcp_atlassian.bitbucket import BitbucketFetcher, BitbucketConfig
        print("✓ BitbucketFetcher and BitbucketConfig imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import BitbucketFetcher or BitbucketConfig: {e}")
        return False

    try:
        from mcp_atlassian.models.bitbucket import BitbucketProject, BitbucketPullRequest
        print("✓ BitbucketProject and BitbucketPullRequest imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import Bitbucket models: {e}")
        return False

    try:
        from mcp_atlassian.servers.bitbucket import bitbucket_mcp
        print("✓ bitbucket_mcp server imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import bitbucket_mcp: {e}")
        return False

    try:
        from mcp_atlassian.servers.dependencies import get_bitbucket_fetcher
        print("✓ get_bitbucket_fetcher imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import get_bitbucket_fetcher: {e}")
        return False

    return True


def test_model_creation():
    """Test that Bitbucket models can be created."""
    print("\nTesting model creation...")

    try:
        from mcp_atlassian.models.bitbucket import BitbucketProject, BitbucketPullRequest

        # Test project model
        project_data = {
            "key": "TEST",
            "name": "Test Project",
            "description": "A test project",
            "is_private": False,
        }
        project = BitbucketProject.from_api_response(project_data, is_cloud=True)
        assert project.key == "TEST"
        assert project.name == "Test Project"
        print("✓ BitbucketProject created successfully")

        # Test PR model
        pr_data = {
            "id": 123,
            "title": "Test PR",
            "state": "OPEN",
            "source": {"branch": {"name": "feature"}},
            "destination": {"branch": {"name": "main"}},
        }
        pr = BitbucketPullRequest.from_api_response(pr_data, is_cloud=True)
        assert pr.id == 123
        assert pr.title == "Test PR"
        assert pr.source_branch == "feature"
        assert pr.destination_branch == "main"
        print("✓ BitbucketPullRequest created successfully")

        return True
    except Exception as e:
        print(f"✗ Failed to create models: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Bitbucket Integration Test")
    print("=" * 60)

    tests_passed = 0
    tests_total = 2

    if test_imports():
        tests_passed += 1

    if test_model_creation():
        tests_passed += 1

    print("\n" + "=" * 60)
    print(f"Results: {tests_passed}/{tests_total} tests passed")
    print("=" * 60)

    return 0 if tests_passed == tests_total else 1


if __name__ == "__main__":
    sys.exit(main())
