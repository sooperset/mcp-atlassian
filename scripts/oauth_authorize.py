#!/usr/bin/env python
"""
OAuth 2.0 Authorization Flow Helper for MCP Atlassian

This script helps with the OAuth 2.0 (3LO) authorization flow for Atlassian Cloud:
1. Opens a browser to the authorization URL
2. Starts a local server to receive the callback with the authorization code
3. Exchanges the authorization code for access and refresh tokens
4. Saves the tokens for later use by MCP Atlassian

Usage:
    python oauth_authorize.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
                             --redirect-uri http://localhost:8080/callback
                             --scope "read:jira-work write:jira-work read:confluence-space.summary"

Environment variables can also be used:
- ATLASSIAN_OAUTH_CLIENT_ID
- ATLASSIAN_OAUTH_CLIENT_SECRET
- ATLASSIAN_OAUTH_REDIRECT_URI
- ATLASSIAN_OAUTH_SCOPE
"""

import argparse
import http.server
import logging
import os
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser

# Add the parent directory to the path so we can import the package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mcp_atlassian.utils.oauth import OAuthConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("oauth-authorize")

# Global variables for callback handling
authorization_code = None
authorization_state = None
callback_received = False
callback_error = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    def do_get(self) -> None:
        """Handle GET requests (OAuth callback)."""
        global \
            authorization_code, \
            callback_received, \
            callback_error, \
            authorization_state

        # Parse the query parameters from the URL
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "error" in params:
            callback_error = params["error"][0]
            callback_received = True
            self._send_response(f"Authorization failed: {callback_error}")
            return

        if "code" in params:
            authorization_code = params["code"][0]
            if "state" in params:
                authorization_state = params["state"][0]
            callback_received = True
            self._send_response(
                "Authorization successful! You can close this window now."
            )
        else:
            self._send_response(
                "Invalid callback: Authorization code missing", status=400
            )

    def _send_response(self, message: str, status: int = 200) -> None:
        """Send response to the browser."""
        self.send_response(status)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Atlassian OAuth Authorization</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 40px;
                    max-width: 600px;
                    margin: 0 auto;
                }}
                .message {{
                    padding: 20px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }}
                .success {{
                    background-color: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                }}
                .error {{
                    background-color: #f8d7da;
                    color: #721c24;
                    border: 1px solid #f5c6cb;
                }}
            </style>
        </head>
        <body>
            <h1>Atlassian OAuth Authorization</h1>
            <div class="message {"success" if status == 200 else "error"}">
                <p>{message}</p>
            </div>
            <p>This window will automatically close in 5 seconds...</p>
            <script>
                setTimeout(function() {{
                    window.close();
                }}, 5000);
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    # Make the server quiet
    def log_message(self, format: str, *args: str) -> None:
        return


def start_callback_server(port: int) -> socketserver.TCPServer:
    """Start a local server to receive the OAuth callback."""
    handler = CallbackHandler
    httpd = socketserver.TCPServer(("", port), handler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return httpd


def wait_for_callback(timeout: int = 300) -> bool:
    """Wait for the callback to be received."""
    start_time = time.time()
    while not callback_received and (time.time() - start_time) < timeout:
        time.sleep(1)

    if not callback_received:
        logger.error(
            f"Timed out waiting for authorization callback after {timeout} seconds"
        )
        return False

    if callback_error:
        logger.error(f"Authorization error: {callback_error}")
        return False

    return True


def parse_redirect_uri(redirect_uri: str) -> tuple[str, int]:
    """Parse the redirect URI to extract host and port."""
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, port


def run_oauth_flow(args: argparse.Namespace) -> bool:
    """Run the OAuth 2.0 authorization flow."""
    # Create OAuth configuration
    oauth_config = OAuthConfig(
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
        scope=args.scope,
    )

    # Generate a random state for CSRF protection
    import secrets

    state = secrets.token_urlsafe(16)

    # Start local callback server if using localhost
    hostname, port = parse_redirect_uri(args.redirect_uri)
    httpd = None

    if hostname in ["localhost", "127.0.0.1"]:
        logger.info(f"Starting local callback server on port {port}")
        try:
            httpd = start_callback_server(port)
        except OSError as e:
            logger.error(f"Failed to start callback server: {e}")
            logger.error(f"Make sure port {port} is available and not in use")
            return False

    # Get the authorization URL
    auth_url = oauth_config.get_authorization_url(state=state)

    # Open the browser for authorization
    logger.info(f"Opening browser for authorization at {auth_url}")
    webbrowser.open(auth_url)
    logger.info(
        "If the browser doesn't open automatically, please visit this URL manually."
    )

    # Wait for the callback
    if not wait_for_callback():
        if httpd:
            httpd.shutdown()
        return False

    # Verify state to prevent CSRF attacks
    if authorization_state != state:
        logger.error("State mismatch! Possible CSRF attack.")
        if httpd:
            httpd.shutdown()
        return False

    # Exchange the code for tokens
    logger.info("Exchanging authorization code for tokens...")
    if oauth_config.exchange_code_for_tokens(authorization_code):
        logger.info("OAuth authorization successful!")
        logger.info(
            f"Access token: {oauth_config.access_token[:10]}...{oauth_config.access_token[-5:]}"
        )
        logger.info(
            f"Refresh token saved: {oauth_config.refresh_token[:5]}...{oauth_config.refresh_token[-3:]}"
        )

        if oauth_config.cloud_id:
            logger.info(f"Cloud ID: {oauth_config.cloud_id}")
            logger.info("\nAdd the following to your .env file:")
            logger.info(f"ATLASSIAN_OAUTH_CLIENT_ID={oauth_config.client_id}")
            logger.info(f"ATLASSIAN_OAUTH_CLIENT_SECRET={oauth_config.client_secret}")
            logger.info(f"ATLASSIAN_OAUTH_REDIRECT_URI={oauth_config.redirect_uri}")
            logger.info(f"ATLASSIAN_OAUTH_SCOPE={oauth_config.scope}")
            logger.info(f"ATLASSIAN_OAUTH_CLOUD_ID={oauth_config.cloud_id}")
        else:
            logger.error("Failed to obtain cloud ID!")

        if httpd:
            httpd.shutdown()
        return True
    else:
        logger.error("Failed to exchange authorization code for tokens")
        if httpd:
            httpd.shutdown()
        return False


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

    success = run_oauth_flow(args)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
