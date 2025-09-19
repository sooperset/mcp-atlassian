#!/usr/bin/env python3
"""Test script for page versions functionality."""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig


def load_credentials() -> dict[str, str | None]:
    """Load credentials from .test-credentials.json or environment."""
    creds_file = Path(".test-credentials.json")

    if creds_file.exists():
        with open(creds_file) as f:
            return json.load(f)

    # Fallback to environment variables
    return {
        "confluence_url": os.getenv("CONFLUENCE_URL"),
        "username": os.getenv("CONFLUENCE_USERNAME"),
        "api_token": os.getenv("CONFLUENCE_API_TOKEN"),
    }


def test_page_versions(page_id: str) -> bool:
    """Test getting page versions for a specific page ID."""
    print(f"Testing page versions for page ID: {page_id}")

    # Load credentials
    creds = load_credentials()

    if not all(
        [creds.get("confluence_url"), creds.get("username"), creds.get("api_token")]
    ):
        print(
            "❌ Missing credentials. Please provide .test-credentials.json or set environment variables."
        )
        return False

    try:
        # Create config
        config = ConfluenceConfig(
            url=creds["confluence_url"],
            username=creds["username"],
            api_token=creds["api_token"],
            auth_type="basic",
        )

        # Create fetcher
        fetcher = ConfluenceFetcher(config)

        print(f"✅ Connected to: {config.url}")
        print(f"🔧 Auth type: {config.auth_type}")
        print(f"🌐 Is Cloud: {config.is_cloud}")
        print(f"🔌 Using v2 adapter: {fetcher._v2_adapter is not None}")

        # Test 1: Get all versions
        print("\n📋 Getting all versions...")
        versions = fetcher.get_page_versions(page_id)
        print(f"Found {len(versions)} versions:")

        for version in versions:
            print(f"  - Version {version.number}: {version.when}")
            if version.message:
                print(f"    Message: {version.message}")
            if version.by:
                print(f"    By: {version.by.display_name}")

        # Test 2: Get specific version (latest)
        if versions:
            latest_version = versions[0].number
            print(f"\n🔍 Getting specific version {latest_version}...")
            specific_version = fetcher.get_page_version(page_id, latest_version)
            print(f"Version {specific_version.number}: {specific_version.when}")
            if specific_version.message:
                print(f"Message: {specific_version.message}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    page_id = "1137248511"
    success = test_page_versions(page_id)
    sys.exit(0 if success else 1)
