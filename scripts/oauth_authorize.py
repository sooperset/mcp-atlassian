#!/usr/bin/env python
"""
OAuth 2.0 Authorization Flow Helper for MCP Atlassian

This script helps with the OAuth 2.0 (3LO) authorization flow for Atlassian Cloud
and Server/Data Center:
1. Opens a browser to the authorization URL
2. Starts a local server to receive the callback with the authorization code
3. Exchanges the authorization code for access and refresh tokens
4. Saves the tokens for later use by MCP Atlassian

Usage (Cloud):
    python oauth_authorize.py \\
        --client-id YOUR_CLIENT_ID \\
        --client-secret YOUR_CLIENT_SECRET \\
        --redirect-uri http://localhost:8080/callback \\
        --scope "read:jira-work offline_access"

Usage (Server/Data Center):
    python oauth_authorize.py \\
        --base-url https://jira.local.example.com \\
        --client-id YOUR_CLIENT_ID \\
        --client-secret YOUR_CLIENT_SECRET \\
        --redirect-uri http://localhost:8080/callback \\
        --scope WRITE

Environment variables can also be used:
- ATLASSIAN_OAUTH_CLIENT_ID / JIRA_OAUTH_CLIENT_ID
- ATLASSIAN_OAUTH_CLIENT_SECRET / JIRA_OAUTH_CLIENT_SECRET
- ATLASSIAN_OAUTH_REDIRECT_URI
- ATLASSIAN_OAUTH_SCOPE
- JIRA_URL (for --base-url)
"""

import argparse
import logging
import os
import sys

# Add the parent directory to the path so we can import the package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp_atlassian.utils.oauth_setup import OAuthSetupArgs, run_oauth_flow
from src.mcp_atlassian.utils.urls import is_atlassian_cloud_url

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(lineno)d - %(message)s",
    force=True,
)

logger = logging.getLogger("oauth-authorize")
logger.setLevel(logging.DEBUG)
logging.getLogger("mcp-atlassian.oauth").setLevel(logging.DEBUG)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OAuth 2.0 Authorization Flow Helper for MCP Atlassian "
        "(Cloud and Server/Data Center)"
    )
    parser.add_argument(
        "--base-url",
        help="Jira Server/DC instance URL (e.g., https://jira.local.example.com). "
        "Omit for Atlassian Cloud.",
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
    if not args.base_url:
        args.base_url = os.getenv("JIRA_URL")
    if not args.client_id:
        args.client_id = os.getenv("JIRA_OAUTH_CLIENT_ID") or os.getenv(
            "ATLASSIAN_OAUTH_CLIENT_ID"
        )
    if not args.client_secret:
        args.client_secret = os.getenv("JIRA_OAUTH_CLIENT_SECRET") or os.getenv(
            "ATLASSIAN_OAUTH_CLIENT_SECRET"
        )
    if not args.redirect_uri:
        args.redirect_uri = os.getenv("ATLASSIAN_OAUTH_REDIRECT_URI")
    if not args.scope:
        args.scope = os.getenv("ATLASSIAN_OAUTH_SCOPE")

    is_dc = bool(args.base_url) and not is_atlassian_cloud_url(args.base_url)

    # Clear base_url for Cloud URLs so OAuthConfig treats it as Cloud
    base_url: str | None = args.base_url if is_dc else None

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

    # Check for offline_access scope (Cloud only — DC doesn't use it)
    if not is_dc and args.scope and "offline_access" not in args.scope.split():
        logger.warning(
            "The 'offline_access' scope is missing! Without it, refresh "
            "tokens will not be issued and authentication will fail when "
            "tokens expire. Consider adding 'offline_access' to your scope."
        )

    setup_args = OAuthSetupArgs(
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
        scope=args.scope,
        base_url=base_url,
    )
    success = run_oauth_flow(setup_args)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
