#!/usr/bin/env python3
"""
Generate VS Code MCP Server Configuration for Atlassian

This script generates a JSON configuration snippet for VS Code settings.json
that can be used to set up the MCP Atlassian server in VS Code.

Usage:
  python generate_vscode_config.py

The script will use OAuth credentials from environment variables or prompt for them.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any


def get_env_or_prompt(var_name: str, prompt: str, is_secret: bool = False) -> str:
    """Get value from environment variable or prompt the user."""
    value = os.environ.get(var_name)
    if value:
        return value

    if is_secret and sys.stdin.isatty():
        from getpass import getpass

        return getpass(f"{prompt}: ")
    else:
        return input(f"{prompt}: ")


def get_token_path(client_id: str) -> Path:
    """Get the path to the token file."""
    return Path.home() / ".mcp-atlassian" / f"oauth-{client_id}.json"


def load_tokens(client_id: str) -> dict[str, Any]:
    """Load tokens from the token file."""
    token_path = get_token_path(client_id)
    if not token_path.exists():
        return {}

    try:
        with open(token_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading tokens: {e}")
        return {}


def generate_vscode_config() -> None:
    """Generate VS Code configuration for MCP Atlassian server."""
    print("\n=== Generate VS Code Configuration for MCP Atlassian ===")
    print("This will create a JSON snippet to add to your VS Code settings.json file.")
    print("You need to have completed the OAuth setup process first.\n")

    # Get OAuth credentials
    client_id = get_env_or_prompt("ATLASSIAN_OAUTH_CLIENT_ID", "OAuth Client ID")
    client_secret = get_env_or_prompt(
        "ATLASSIAN_OAUTH_CLIENT_SECRET", "OAuth Client Secret", is_secret=True
    )
    redirect_uri = (
        get_env_or_prompt("ATLASSIAN_OAUTH_REDIRECT_URI", "OAuth Redirect URI")
        or "http://localhost:8080/callback"
    )
    scope = (
        get_env_or_prompt("ATLASSIAN_OAUTH_SCOPE", "OAuth Scopes (space-separated)")
        or "read:jira-work write:jira-work read:confluence-space.summary offline_access"
    )
    cloud_id = get_env_or_prompt("ATLASSIAN_OAUTH_CLOUD_ID", "Atlassian Cloud ID")

    # Check token file existence
    token_path = get_token_path(client_id)
    if not token_path.exists():
        print(f"\nWarning: Token file not found at {token_path}")
        print("Have you completed the OAuth setup process? If not, run:")
        print("  mcp-atlassian --oauth-setup --verbose")
        proceed = input("\nProceed anyway? (y/n): ")
        if proceed.lower() != "y":
            return
    else:
        tokens = load_tokens(client_id)
        if not tokens:
            print(f"\nWarning: No tokens found in {token_path}")
            proceed = input("Proceed anyway? (y/n): ")
            if proceed.lower() != "y":
                return

    # Generate configuration
    config = {
        "mcp": {
            "servers": {
                "atlassian": {
                    "command": "mcp-atlassian",
                    "args": [],
                    "env": {
                        "ATLASSIAN_OAUTH_CLIENT_ID": client_id,
                        "ATLASSIAN_OAUTH_CLIENT_SECRET": client_secret,
                        "ATLASSIAN_OAUTH_REDIRECT_URI": redirect_uri,
                        "ATLASSIAN_OAUTH_SCOPE": scope,
                        "ATLASSIAN_OAUTH_CLOUD_ID": cloud_id,
                    },
                }
            }
        }
    }

    # Pretty print the configuration
    config_json = json.dumps(config, indent=4)

    print("\n=== VS Code Configuration ===")
    print("Add this to your VS Code settings.json file:")
    print("-" * 60)
    print(config_json)
    print("-" * 60)
    print(
        "\nNote: If you already have an 'mcp' configuration, merge this with your existing configuration."
    )
    print(
        "The tokens will be loaded automatically from your system keyring or the backup file at:"
    )
    print(f"  {token_path}")


if __name__ == "__main__":
    generate_vscode_config()
