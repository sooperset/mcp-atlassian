"""Audit logging middleware for MCP tool calls.

Provides structured per-tool-call audit logging via the FastMCP
middleware system. Each log entry follows the format:

    <source_ip> <tool_name> <username> <request_body_json>

The middleware is registered on the server instance via
``create_audit_middleware()`` and gated by the
``MCP_AUDIT_LOG_ENABLED`` environment variable (enabled by default).
"""

import base64
import json
import logging
import os
from typing import Any

import mcp.types as mt
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from mcp_atlassian.utils.logging import mask_sensitive

# Dedicated audit logger, separate from application logs
audit_logger = logging.getLogger("mcp-atlassian.audit")
# The application logger defaults to WARNING. Keep audit records at INFO so
# the dedicated logger is not filtered by the parent logger's level.
audit_logger.setLevel(logging.INFO)

# Default sensitive field patterns (case-insensitive substring match)
DEFAULT_SENSITIVE_PATTERNS: list[str] = [
    "token",
    "password",
    "secret",
    "key",
    "credential",
    "auth",
]


class ToolCallLoggingMiddleware(Middleware):
    """Audit logging middleware for MCP tool calls.

    Intercepts tool invocations via the ``on_call_tool`` hook and emits
    structured audit log entries after the downstream handler completes.

    Args:
        sensitive_patterns: Additional field name substrings to treat as
            sensitive (merged with defaults). Pass ``None`` to use only
            the default patterns.
        max_body_length: Maximum character length for the serialized
            request body before truncation. Must be >= 64.
    """

    def __init__(
        self,
        sensitive_patterns: list[str] | None = None,
        max_body_length: int = 2048,
    ) -> None:
        """Initialize the audit logging middleware.

        Args:
            sensitive_patterns: Additional field name substrings to
                treat as sensitive. Merged with the default patterns.
            max_body_length: Maximum character length for serialized
                request body before truncation (default: 2048).
        """
        super().__init__()
        self._sensitive_patterns: list[str] = list(DEFAULT_SENSITIVE_PATTERNS)
        if sensitive_patterns:
            self._sensitive_patterns.extend(sensitive_patterns)
        self._max_body_length = max_body_length

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key matches any sensitive pattern.

        Args:
            key: The field name to check.

        Returns:
            True if the key contains a sensitive pattern substring
            (case-insensitive).
        """
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in self._sensitive_patterns)

    def _extract_source_ip(
        self, context: MiddlewareContext[mt.CallToolRequestParams]
    ) -> str:
        """Extract the client source IP from the ASGI scope.

        Checks for the ``X-Forwarded-For`` header first (uses the first
        comma-separated IP), then falls back to the ASGI scope ``client``
        tuple, and finally returns ``"unknown"`` if neither is available.

        Args:
            context: The middleware context for the current tool call.

        Returns:
            The extracted source IP address with whitespace stripped.
        """
        try:
            request = get_http_request()
            scope = request.scope
        except (RuntimeError, AttributeError):
            return "unknown"

        # Check X-Forwarded-For header in ASGI scope headers
        # Headers are stored as list of (name, value) byte tuples
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for header_name, header_value in headers:
            if header_name.lower() == b"x-forwarded-for":
                # Use the first comma-separated IP
                forwarded_ips = header_value.decode("latin-1")
                first_ip = forwarded_ips.split(",")[0]
                first_ip = first_ip.strip()
                if first_ip:
                    return first_ip

        # Fall back to scope client tuple
        client = scope.get("client")
        if client and len(client) >= 1:
            return str(client[0]).strip()

        return "unknown"

    @staticmethod
    def _sanitize_log_field(value: str) -> str:
        """Keep a structured log field on one line.

        Source and identity values come from request-controlled data. Replace
        whitespace and control characters so they can't create additional log
        lines or shift the space-delimited fields.

        Args:
            value: The field value to sanitize.

        Returns:
            A single-line field value.
        """
        return "".join(
            character if character.isprintable() and not character.isspace() else "_"
            for character in value
        )

    def _extract_username(
        self, context: MiddlewareContext[mt.CallToolRequestParams]
    ) -> str:
        """Extract the username from the request authentication state.

        Resolves the username based on the authentication type set by
        the upstream ``UserTokenMiddleware``. No network calls are made.

        Args:
            context: The middleware context for the current tool call.

        Returns:
            The resolved username string.
        """
        try:
            request = get_http_request()
        except (RuntimeError, AttributeError):
            return "anonymous"

        auth_type = getattr(request.state, "user_atlassian_auth_type", None)

        if auth_type == "basic":
            return self._extract_basic_username(request)
        elif auth_type == "pat":
            email = getattr(request.state, "user_atlassian_email", None)
            return email if email else "pat-user"
        elif auth_type == "oauth":
            email = getattr(request.state, "user_atlassian_email", None)
            return email if email else "oauth-user"

        return "anonymous"

    def _extract_basic_username(self, request: Any) -> str:
        """Extract email from Basic auth Authorization header.

        Decodes the Base64-encoded Authorization header and returns
        the portion before the first ``:`` as the username.

        Args:
            request: The Starlette request object.

        Returns:
            The email from the Authorization header, or
            ``"anonymous"`` if the header is missing or invalid.
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("basic "):
            return "anonymous"

        encoded = auth_header.split(" ", 1)[1]
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except ValueError:
            return "anonymous"

        if ":" not in decoded:
            return "anonymous"

        email = decoded.split(":", 1)[0]
        return email if email else "anonymous"

    def _mask_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Mask sensitive fields in tool call arguments.

        Performs case-insensitive substring matching of field names
        against configured sensitive patterns. For top-level values
        that are dictionaries and whose key does NOT match a sensitive
        pattern, inspects nested keys one level deep.

        Args:
            arguments: The tool call arguments dictionary.

        Returns:
            A new dictionary with sensitive values masked.
        """
        masked: dict[str, Any] = {}
        for key, value in arguments.items():
            if self._is_sensitive_key(key):
                masked[key] = mask_sensitive(str(value))
            elif isinstance(value, dict):
                # Inspect nested dict keys (1 level deep only)
                nested: dict[str, Any] = {}
                for nested_key, nested_value in value.items():
                    if self._is_sensitive_key(nested_key):
                        nested[nested_key] = mask_sensitive(str(nested_value))
                    else:
                        nested[nested_key] = nested_value
                masked[key] = nested
            else:
                masked[key] = value
        return masked

    def _serialize_body(
        self,
        arguments: dict[str, Any] | None,
        *,
        original_length: int | None = None,
    ) -> str:
        """JSON-serialize arguments as a single-line string.

        Serializes the masked arguments dictionary to JSON. If the
        original content length exceeds the configured threshold, the
        output is truncated and ``...truncated`` is appended.

        Args:
            arguments: The tool call arguments to serialize, or None.
            original_length: Optional length of the unmasked arguments before
                serialization. When omitted, the length of ``arguments`` is
                used.

        Returns:
            A single-line JSON string, or ``{}`` for empty/None args.
        """
        if not arguments:
            return "{}"

        # Measure the unmasked content when the caller provides it. This keeps
        # truncation based on the request body rather than its masked copy.
        if original_length is None:
            original_length = len(str(arguments))

        # JSON-serialize with repr fallback for non-serializable values
        serialized = json.dumps(arguments, default=repr, ensure_ascii=False)

        # Remove newlines and control characters for single-line output
        serialized = "".join(ch for ch in serialized if ch >= " " and ch != "\x7f")

        # Truncate if original content length exceeds threshold
        if original_length > self._max_body_length:
            serialized = serialized[: self._max_body_length] + "...truncated"

        return serialized

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls to emit audit log entries.

        Extracts source IP, tool name, and masked request body before
        delegating to the downstream handler. After the tool executes
        (triggering dependency injection / email backfill), extracts
        the username and emits the audit log entry. If ``call_next``
        raises, the audit entry is still emitted before the exception
        propagates.

        Args:
            context: The middleware context containing the tool call
                request parameters.
            call_next: Callable to delegate to the next handler in the
                middleware chain.

        Returns:
            The result from the downstream tool handler.
        """
        # Extract data that doesn't depend on dependency injection
        source_ip: str | None = None
        tool_name: str | None = None
        body: str | None = None
        try:
            source_ip = self._extract_source_ip(context)
            tool_name = context.message.name
            arguments = context.message.arguments or {}
            original_length = len(str(arguments))
            masked_arguments = self._mask_arguments(arguments)
            body = self._serialize_body(
                masked_arguments,
                original_length=original_length,
            )
        except Exception:  # noqa: BLE001
            app_logger = logging.getLogger("mcp-atlassian")
            app_logger.warning(
                "Audit logging failed for tool call",
                exc_info=True,
            )
            for handler in app_logger.handlers:
                handler.flush()

        # Execute the tool (triggers DI / email backfill). Keep audit emission
        # in a finally block so cancellation and all other exceptions are
        # still recorded before the original outcome propagates.
        try:
            return await call_next(context)
        finally:
            # Extract username AFTER call_next (email now available).
            if source_ip is not None and tool_name is not None and body is not None:
                try:
                    username = self._extract_username(context)
                    log_entry = " ".join(
                        (
                            self._sanitize_log_field(source_ip),
                            self._sanitize_log_field(tool_name),
                            self._sanitize_log_field(username),
                            body,
                        )
                    )
                    audit_logger.info(log_entry)
                except Exception:  # noqa: BLE001
                    app_logger = logging.getLogger("mcp-atlassian")
                    app_logger.warning(
                        "Audit logging failed for tool call",
                        exc_info=True,
                    )
                    for handler in app_logger.handlers:
                        handler.flush()


# Values considered falsy for MCP_AUDIT_LOG_ENABLED (case-insensitive)
_FALSY_VALUES = {"false", "0", "no"}


def create_audit_middleware() -> ToolCallLoggingMiddleware | None:
    """Create audit middleware if enabled by configuration.

    Reads environment variables to determine whether audit logging is
    enabled and how it should be configured. Returns ``None`` when
    logging is explicitly disabled.

    Environment variables:
        MCP_AUDIT_LOG_ENABLED: Set to ``false``, ``0``, or ``no``
            (case-insensitive) to disable audit logging. Enabled by
            default when unset or set to a truthy value.
        MCP_AUDIT_SENSITIVE_FIELDS: Comma-separated list of additional
            field name substrings to treat as sensitive. Whitespace is
            trimmed from each entry and empty entries are discarded.
        MCP_AUDIT_MAX_BODY_LENGTH: Maximum character length for the
            serialized request body. Must be an integer >= 64;
            defaults to 2048 if invalid or unset.

    Returns:
        A configured ``ToolCallLoggingMiddleware`` instance, or
        ``None`` if audit logging is disabled.
    """
    # Check if audit logging is disabled
    enabled_raw = os.environ.get("MCP_AUDIT_LOG_ENABLED", "")
    if enabled_raw.strip().lower() in _FALSY_VALUES:
        return None

    # Parse additional sensitive field patterns
    sensitive_patterns: list[str] | None = None
    sensitive_raw = os.environ.get("MCP_AUDIT_SENSITIVE_FIELDS", "")
    if sensitive_raw:
        try:
            entries = sensitive_raw.split(",")
            parsed = [entry.strip() for entry in entries]
            parsed = [entry for entry in parsed if entry]
            if parsed:
                sensitive_patterns = parsed
        except Exception:  # noqa: BLE001
            # Malformed value — skip additional patterns, use defaults
            sensitive_patterns = None

    # Parse max body length
    max_body_length = 2048
    max_length_raw = os.environ.get("MCP_AUDIT_MAX_BODY_LENGTH", "")
    if max_length_raw:
        try:
            parsed_length = int(max_length_raw)
            if parsed_length >= 64:
                max_body_length = parsed_length
        except (ValueError, TypeError):
            pass

    return ToolCallLoggingMiddleware(
        sensitive_patterns=sensitive_patterns,
        max_body_length=max_body_length,
    )
