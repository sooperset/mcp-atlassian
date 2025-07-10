"""Authentication utilities for MCP Atlassian.

This module provides utilities for handling authentication-related operations,
including decoding Basic Authentication tokens and other authentication helpers.
"""

import base64
import binascii
import logging

# Get logger for this module
logger = logging.getLogger("mcp-atlassian.utils.auth")


class AuthUtils:
    """Utility class for authentication-related operations.

    This class provides static methods for common authentication tasks
    such as decoding Basic Authentication tokens.
    """

    @staticmethod
    def decode_basic_token(token: str) -> tuple[str, str] | None:
        """Decode a Basic Authentication token into username and password.

        This method safely decodes a Basic Authentication token, which is typically
        found in the Authorization header of HTTP requests in the format:
        "Basic <base64-encoded-credentials>". The credentials are in the format
        "username:password".

        Args:
            token: The Basic Authentication token to decode. This can be the full
                  "Basic <token>" string or just the base64-encoded part.

        Returns:
            A tuple containing (username, password) if decoding is successful,
            or None if the token is invalid or cannot be decoded.

        Example:
            >>> credentials = AuthUtils.decode_basic_token("Basic dXNlcjpwYXNz")
            >>> if credentials:
            >>>     username, password = credentials
        """
        if not token:
            logger.warning("Attempted to decode empty Basic token")
            return None

        # Extract the base64 part if the token includes "Basic " prefix
        if token.startswith("Basic "):
            token = token[6:]

        try:
            # Decode the base64 token
            decoded_bytes = base64.b64decode(token)
            decoded_str = decoded_bytes.decode("utf-8")

            # Split into username and password
            if ":" in decoded_str:
                username, password = decoded_str.split(":", 1)
                logger.debug(f"Successfully decoded Basic token for user: {username}")
                return username, password
            else:
                logger.warning(
                    "Decoded Basic token does not contain username:password format"
                )
                return None

        except (binascii.Error, UnicodeDecodeError) as e:
            logger.error(f"Failed to decode Basic token: {str(e)}")
            return None
