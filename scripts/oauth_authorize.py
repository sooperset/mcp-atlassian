#!/usr/bin/env python
"""
OAuth 2.0 Authorization Flow Helper for MCP Atlassian

This script runs the same OAuth 2.0 (3LO) flow as ``mcp-atlassian --oauth-setup``
(``mcp_atlassian.utils.oauth_setup.run_oauth_flow``) without the interactive
prompts:
1. Opens a browser to the authorization URL
2. Starts a loopback-only server to receive the callback with the authorization code
3. Exchanges the authorization code for access and refresh tokens
4. Saves the tokens for later use by MCP Atlassian

Usage:
    python oauth_authorize.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
                             --redirect-uri http://localhost:8080/callback
                             --scope "read:jira-work write:jira-work read:confluence-space.summary offline_access"

IMPORTANT: The 'offline_access' scope is required for refresh tokens to work properly.
Without this scope, tokens will expire quickly and authentication will fail.

Environment variables can also be used:
- ATLASSIAN_OAUTH_CLIENT_ID
- ATLASSIAN_OAUTH_CLIENT_SECRET
- ATLASSIAN_OAUTH_REDIRECT_URI
- ATLASSIAN_OAUTH_SCOPE
"""

import argparse
import logging
import os
import sys

# Prefer the package from this checkout so the script runs without installing it.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)

from mcp_atlassian.utils.oauth_setup import (  # noqa: E402
    OAuthSetupArgs,
    run_oauth_flow,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    force=True,
)

logger = logging.getLogger("oauth-authorize")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OAuth 2.0 Authorization Flow Helper for MCP Atlassian"
    )
    parser.add_argument("--client-id", help="OAuth Client ID")
    parser.add_argument("--client-secret", help="OAuth Client Secret")
    parser.add_argument(
        "--redirect-uri",
        help="OAuth Redirect URI (e.g., http://localhost:8080/callback)",
    )
    parser.add_argument("--scope", help="OAuth Scope (space-separated)")

    args = parser.parse_args()

    # Check for environment variables if arguments are not provided
    if not args.client_id:
        args.client_id = os.getenv("ATLASSIAN_OAUTH_CLIENT_ID")
    if not args.client_secret:
        args.client_secret = os.getenv("ATLASSIAN_OAUTH_CLIENT_SECRET")
    if not args.redirect_uri:
        args.redirect_uri = os.getenv("ATLASSIAN_OAUTH_REDIRECT_URI")
    if not args.scope:
        args.scope = os.getenv("ATLASSIAN_OAUTH_SCOPE")

    # Validate required arguments
    missing = []
    if not args.client_id:
        missing.append("client-id")
    if not args.client_secret:
        missing.append("client-secret")
    if not args.redirect_uri:
        missing.append("redirect-uri")
    if not args.scope:
        missing.append("scope")

    if missing:
        logger.error(f"Missing required arguments: {', '.join(missing)}")
        parser.print_help()
        return 1

    # Check for offline_access scope
    if args.scope and "offline_access" not in args.scope.split():
        logger.warning("\n⚠️ WARNING: The 'offline_access' scope is missing!")
        logger.warning(
            "Without this scope, refresh tokens will not be issued and authentication will fail when tokens expire."
        )
        logger.warning("Consider adding 'offline_access' to your scope string.")
        proceed = input("Do you want to proceed anyway? (y/n): ")
        if proceed.lower() != "y":
            return 1

    success = run_oauth_flow(
        OAuthSetupArgs(
            client_id=args.client_id,
            client_secret=args.client_secret,
            redirect_uri=args.redirect_uri,
            scope=args.scope,
        )
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
