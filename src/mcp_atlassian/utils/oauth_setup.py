"""
OAuth 2.0 Authorization Flow Helper for MCP Atlassian

This module helps with the OAuth 2.0 authorization flow for Atlassian Cloud and Data Center:
1. Opens a browser to the authorization URL
2. Starts a local server to receive the callback with the authorization code
3. Exchanges the authorization code for access and refresh tokens
4. Saves the tokens securely for later use by MCP Atlassian
"""

import http.server
import logging
import os
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Literal, Sequence

from ..utils.oauth import OAuthConfig

# Configure logging
logger = logging.getLogger("mcp-atlassian.oauth-setup")

# Global variables for callback handling
authorization_code = None
authorization_state = None
callback_received = False
callback_error = None

OAuthPrefix = Literal["CONFLUENCE_OAUTH_", "JIRA_OAUTH_", "ATLASSIAN_OAUTH_"]
OAUTH_PREFIXES: tuple[OAuthPrefix, ...] = ("CONFLUENCE_OAUTH_", "JIRA_OAUTH_", "ATLASSIAN_OAUTH_")

def _detect_oauth_prefix() -> OAuthPrefix:
    """Pick the most relevant OAuth env prefix based on what is set."""
    keys = (
        "CLIENT_ID",
        "CLIENT_SECRET",
        "REDIRECT_URI",
        "SCOPE",
        "INSTANCE_TYPE",
        "INSTANCE_URL",
        "CLOUD_ID",
        "ENABLE",
    )
    for prefix in OAUTH_PREFIXES:
        for k in keys:
            v = os.getenv(f"{prefix}{k}")
            if v and v.strip():
                return prefix
    return "ATLASSIAN_OAUTH_"

def _get_first_env(var_names: Sequence[str]) -> str | None:
    for name in var_names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip()
    return None

def _sanitize_input(user_input: str) -> str:
    """Sanitize user input by removing trailing/leading whitespace and Windows line endings.
    Args:
        user_input: Raw input string from user
    Returns:
        Sanitized string with whitespace and line endings removed
    """
    if not user_input:
        return user_input
    # Remove leading/trailing whitespace and various line endings
    # Handle Windows (\r\n), Unix (\n), and Mac (\r) line endings
    sanitized = user_input.strip().rstrip("\r\n").strip()
    return sanitized


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    def do_GET(self) -> None:  # noqa: N802
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
                .countdown {{
                    font-weight: bold;
                    font-size: 1.2em;
                }}
            </style>
        </head>
        <body>
            <h1>Atlassian OAuth Authorization</h1>
            <div class="message {"success" if status == 200 else "error"}">
                <p>{message}</p>
            </div>
            <p>This window will automatically close in <span class="countdown">5</span> seconds...</p>
            <button onclick="window.close()">Close Window Now</button>
            <script>
                // Countdown timer
                var seconds = 5;
                var countdown = document.querySelector('.countdown');
                var timer = setInterval(function() {{
                    seconds--;
                    countdown.textContent = seconds;
                    if (seconds <= 0) {{
                        clearInterval(timer);
                        // Try multiple methods to close the window
                        window.close();
                        // If the above doesn't work (which is often the case with modern browsers)
                        try {{ window.open('', '_self').close(); }} catch (e) {{}}
                    }}
                }}, 1000);

                // Force close on success after 5.5 seconds as a fallback
                setTimeout(function() {{
                    // If status is 200 (success), really try hard to close
                    if ({status} === 200) {{
                        window.open('about:blank', '_self');
                        window.close();
                    }}
                }}, 5500);
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
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid redirect URI (missing hostname): {redirect_uri!r}")
    return hostname, port


@dataclass
class OAuthSetupArgs:
    """Arguments for the OAuth setup flow."""

    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str
    env_prefix: OAuthPrefix = "ATLASSIAN_OAUTH_"


def run_oauth_flow(args: OAuthSetupArgs) -> bool:
    """Run the OAuth 2.0 authorization flow."""
    # Reset global state (important for multiple runs)
    global authorization_code, authorization_state, callback_received, callback_error
    authorization_code = None
    authorization_state = None
    callback_received = False
    callback_error = None

    # Create OAuth configuration
    oauth_config = OAuthConfig(
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
        scope=args.scope,
    )

    # Apply instance-specific settings from environment (.env should already be loaded by the CLI entrypoint)
    # Prefer the selected env_prefix, but fall back to other known prefixes for robustness.
    prefixes = list(OAUTH_PREFIXES)
    if args.env_prefix in prefixes:
        prefixes.remove(args.env_prefix)
    prefixes.insert(0, args.env_prefix)

    env_instance_type = _get_first_env([f"{p}INSTANCE_TYPE" for p in prefixes])
    if env_instance_type:
        normalized = env_instance_type.strip().lower()
        normalized = normalized.replace("-", "_").replace(" ", "_")
        if normalized == "cloud":
            oauth_config.instance_type = "cloud"
        elif normalized in {"datacenter", "data_center", "dc", "server"}:
            oauth_config.instance_type = "datacenter"
        else:
            logger.warning(
                "Ignoring invalid OAuth INSTANCE_TYPE=%r (expected 'cloud' or 'datacenter')",
                env_instance_type,
            )

    # Determine instance type robustly (OAuthConfig may be mocked in unit tests)
    raw_instance_type = getattr(oauth_config, "instance_type", "cloud")
    instance_type = (
        raw_instance_type.strip().lower()
        if isinstance(raw_instance_type, str) and raw_instance_type.strip()
        else "cloud"
    )
    is_datacenter = instance_type == "datacenter"

    # Data Center requires instance_url to build authorize/token URLs
    if is_datacenter:
        env_instance_url = _get_first_env([f"{p}INSTANCE_URL" for p in prefixes])
        # Convenience fallback: if CONFLUENCE_URL/JIRA_URL are set and look non-cloud,
        # allow using them as instance_url when INSTANCE_URL wasn't provided.
        if not env_instance_url and args.env_prefix == "CONFLUENCE_OAUTH_":
            env_instance_url = os.getenv("CONFLUENCE_URL")
            if env_instance_url and env_instance_url.rstrip("/").endswith("/wiki"):
                env_instance_url = env_instance_url.rstrip("/")[:-4]
        if not env_instance_url and args.env_prefix == "JIRA_OAUTH_":
            env_instance_url = os.getenv("JIRA_URL")

        if env_instance_url and env_instance_url.strip():
            oauth_config.instance_url = env_instance_url.strip()
        else:
            logger.error(
                f"Data Center OAuth requires {args.env_prefix}INSTANCE_URL (or CONFLUENCE_URL/JIRA_URL) to be set (e.g. https://your.confluence.com)"
            )
            return False
    else:
        # Optional: allow pre-setting cloud_id from env (not required for the auth URL)
        env_cloud_id = _get_first_env([f"{p}CLOUD_ID" for p in prefixes])
        if env_cloud_id and env_cloud_id.strip():
            oauth_config.cloud_id = env_cloud_id.strip()
            
    # Generate a random state for CSRF protection
    import secrets

    state = secrets.token_urlsafe(16)

    # Start local callback server if using localhost
    try:
        hostname, port = parse_redirect_uri(args.redirect_uri)
    except ValueError as e:
        logger.error(str(e))
        return False
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
    try:
        opened = webbrowser.open(auth_url)
        if not opened:
            logger.info("Browser did not open automatically (webbrowser.open returned False).")
    except Exception as e:
        logger.warning("Failed to open browser automatically: %s", e)
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
    if not authorization_code:
        logger.error("Authorization code missing in callback.")
        if httpd:
            httpd.shutdown()
        return False
    logger.info("Exchanging authorization code for tokens...")
    if oauth_config.exchange_code_for_tokens(authorization_code):
        logger.info("OAuth authorization successful!")
        access_token = getattr(oauth_config, "access_token", None)
        refresh_token = getattr(oauth_config, "refresh_token", None)
        if isinstance(access_token, str) and access_token:
            logger.info(f"Access token: {access_token[:10]}...{access_token[-5:]}")
        if isinstance(refresh_token, str) and refresh_token:
            logger.info(f"Refresh token saved: {refresh_token[:5]}...{refresh_token[-3:]}")

        if oauth_config.is_cloud and oauth_config.cloud_id:
            logger.info(f"Cloud ID: {oauth_config.cloud_id}")

            # Print environment variable information more clearly
            logger.info("\n=== IMPORTANT: ENVIRONMENT VARIABLES ===")
            logger.info(
                "Your tokens have been securely stored in your system keyring and backup file."
            )
            logger.info(
                "However, to use them in your application, you need these environment variables:"
            )
            logger.info("")
            logger.info(
                "Add the following to your .env file or set as environment variables:"
            )
            logger.info("------------------------------------------------------------")
            logger.info(f"ATLASSIAN_OAUTH_CLIENT_ID={oauth_config.client_id}")
            logger.info(f"ATLASSIAN_OAUTH_CLIENT_SECRET={oauth_config.client_secret}")
            logger.info(f"ATLASSIAN_OAUTH_REDIRECT_URI={oauth_config.redirect_uri}")
            logger.info(f"ATLASSIAN_OAUTH_SCOPE={oauth_config.scope}")
            logger.info(f"ATLASSIAN_OAUTH_CLOUD_ID={oauth_config.cloud_id}")
            logger.info("------------------------------------------------------------")
            logger.info("")
            logger.info(
                "Note: The tokens themselves are not set as environment variables for security reasons."
            )
            logger.info(
                "They are stored securely in your system keyring when available and will be loaded automatically."
            )
            logger.info(
                f"Token storage location (backup): ~/.mcp-atlassian/{oauth_config._get_keyring_username()}.json"
            )

            # Generate VS Code configuration JSON snippet
            import json

            vscode_config = {
                "mcpServers": {
                    "mcp-atlassian": {
                        "command": "docker",
                        "args": [
                            "run",
                            "--rm",
                            "-i",
                            "-p",
                            "8080:8080",
                            "-e",
                            "CONFLUENCE_URL",
                            "-e",
                            "JIRA_URL",
                            "-e",
                            "ATLASSIAN_OAUTH_CLIENT_ID",
                            "-e",
                            "ATLASSIAN_OAUTH_CLIENT_SECRET",
                            "-e",
                            "ATLASSIAN_OAUTH_REDIRECT_URI",
                            "-e",
                            "ATLASSIAN_OAUTH_SCOPE",
                            "-e",
                            "ATLASSIAN_OAUTH_CLOUD_ID",
                            "ghcr.io/sooperset/mcp-atlassian:latest",
                        ],
                        "env": {
                            "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
                            "JIRA_URL": "https://your-company.atlassian.net",
                            "ATLASSIAN_OAUTH_CLIENT_ID": oauth_config.client_id,
                            "ATLASSIAN_OAUTH_CLIENT_SECRET": oauth_config.client_secret,
                            "ATLASSIAN_OAUTH_REDIRECT_URI": oauth_config.redirect_uri,
                            "ATLASSIAN_OAUTH_SCOPE": oauth_config.scope,
                            "ATLASSIAN_OAUTH_CLOUD_ID": oauth_config.cloud_id,
                        },
                    }
                }
            }

            # Pretty print the VS Code configuration JSON
            vscode_json = json.dumps(vscode_config, indent=4)

            logger.info("\n=== VS CODE CONFIGURATION ===")
            logger.info("Add the following to your VS Code settings.json file:")
            logger.info("------------------------------------------------------------")
            logger.info(vscode_json)
            logger.info("------------------------------------------------------------")
            logger.info(
                "\nNote: If you already have an 'mcp' configuration in settings.json, merge this with your existing configuration."
            )
        elif oauth_config.is_datacenter:
            logger.info(f"Data Center instance: {oauth_config.instance_url}")

            # Print environment variable information for Data Center
            logger.info("\n=== IMPORTANT: ENVIRONMENT VARIABLES ===")
            logger.info(
                "Your tokens have been securely stored in your system keyring and backup file."
            )
            logger.info(
                "However, to use them in your application, you need these environment variables:"
            )
            logger.info("")
            logger.info(
                "Add the following to your .env file or set as environment variables:"
            )
            logger.info("------------------------------------------------------------")
            logger.info(f"ATLASSIAN_OAUTH_CLIENT_ID={oauth_config.client_id}")
            logger.info(f"ATLASSIAN_OAUTH_CLIENT_SECRET={oauth_config.client_secret}")
            logger.info(f"ATLASSIAN_OAUTH_REDIRECT_URI={oauth_config.redirect_uri}")
            logger.info(f"ATLASSIAN_OAUTH_SCOPE={oauth_config.scope}")
            logger.info("ATLASSIAN_OAUTH_INSTANCE_TYPE=datacenter")
            logger.info(f"ATLASSIAN_OAUTH_INSTANCE_URL={oauth_config.instance_url}")
            logger.info("------------------------------------------------------------")
            logger.info("")
            logger.info(
                "Note: The tokens themselves are not set as environment variables for security reasons."
            )
            logger.info(
                "They are stored securely in your system keyring when available and will be loaded automatically."
            )
            logger.info(
                f"Token storage location (backup): ~/.mcp-atlassian/{oauth_config._get_keyring_username()}.json"
            )
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


def _prompt_for_input(prompt: str, env_var: str | Sequence[str] | None = None, is_secret: bool = False) -> str:
    """Prompt the user for input with sanitization for Windows line endings and whitespace."""
    env_vars = [env_var] if isinstance(env_var, str) else (env_var or [])
    value = _get_first_env([v for v in env_vars if v]) or ""
    if value:
        if is_secret:
            masked = (
                value[:3] + "*" * (len(value) - 6) + value[-3:]
                if len(value) > 6
                else "****"
            )
            print(f"{prompt} [{masked}]: ", end="")
        else:
            print(f"{prompt} [{value}]: ", end="")
        user_input = _sanitize_input(input())
        return user_input if user_input else value
    else:
        print(f"{prompt}: ", end="")
        return _sanitize_input(input())


def run_oauth_setup() -> int:
    """Run the OAuth 2.0 setup wizard interactively."""
    print("\n=== Atlassian OAuth 2.0 Setup Wizard ===")
    print(
        "This wizard will guide you through setting up OAuth 2.0 authentication for MCP Atlassian."
    )
    print("\nYou need to have created an OAuth 2.0 app in your Atlassian account.")
    print("You can create one at: https://developer.atlassian.com/console/myapps/")
    print("\nPlease provide the following information:\n")

    prefix = _detect_oauth_prefix()
 
    # Check for environment variables first
    client_id = _prompt_for_input("OAuth Client ID", [f"{prefix}CLIENT_ID", "ATLASSIAN_OAUTH_CLIENT_ID"])

    client_secret = _prompt_for_input(
        "OAuth Client Secret", [f"{prefix}CLIENT_SECRET", "ATLASSIAN_OAUTH_CLIENT_SECRET"], is_secret=True
    )

    default_redirect = os.getenv(
        f"{prefix}REDIRECT_URI", os.getenv("ATLASSIAN_OAUTH_REDIRECT_URI", "http://localhost:8080/callback")
    )
    redirect_uri = (
        _prompt_for_input("OAuth Redirect URI", [f"{prefix}REDIRECT_URI", "ATLASSIAN_OAUTH_REDIRECT_URI"])
        or default_redirect
    )

    default_scope = os.getenv(
        f"{prefix}SCOPE",
        os.getenv(
            "ATLASSIAN_OAUTH_SCOPE",
            "read:jira-work write:jira-work read:confluence-space.summary offline_access",
        ),
    )
    scope = (
        _prompt_for_input(
            "OAuth Scopes (space-separated)",
            [f"{prefix}SCOPE", "ATLASSIAN_OAUTH_SCOPE"],
        )
        or default_scope
    )

    # Validate required arguments
    if not client_id:
        logger.error("OAuth Client ID is required")
        return 1
    if not client_secret:
        logger.error("OAuth Client Secret is required")
        return 1

    # Run the OAuth flow
    args = OAuthSetupArgs(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        env_prefix=prefix,
    )

    success = run_oauth_flow(args)
    return 0 if success else 1
