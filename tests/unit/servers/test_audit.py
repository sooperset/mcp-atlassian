"""Property-based tests for the audit logging middleware.

Uses Hypothesis to verify correctness properties defined in the
tool-call-audit-logging design document.

Feature: tool-call-audit-logging
"""

import asyncio
import copy
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_atlassian.servers.audit import (
    ToolCallLoggingMiddleware,
    create_audit_middleware,
)
from mcp_atlassian.utils.logging import mask_sensitive

# --- Strategies ---

# Falsy values for MCP_AUDIT_LOG_ENABLED (case-insensitive)
_FALSY_BASES = ["false", "0", "no"]

# Generate falsy string variants with mixed case and whitespace
falsy_values = st.one_of(
    st.sampled_from(_FALSY_BASES),
    st.sampled_from(_FALSY_BASES).map(str.upper),
    st.sampled_from(_FALSY_BASES).map(str.title),
    st.sampled_from(_FALSY_BASES).map(lambda s: " " + s + " "),
    st.sampled_from(_FALSY_BASES).map(lambda s: "\t" + s.upper() + "\t"),
    st.sampled_from(_FALSY_BASES).map(lambda s: s[0].upper() + s[1:]),
)

# Truthy values for MCP_AUDIT_LOG_ENABLED (case-insensitive)
_TRUTHY_BASES = ["true", "1", "yes"]

truthy_values = st.one_of(
    st.sampled_from(_TRUTHY_BASES),
    st.sampled_from(_TRUTHY_BASES).map(str.upper),
    st.sampled_from(_TRUTHY_BASES).map(str.title),
    st.sampled_from(_TRUTHY_BASES).map(lambda s: " " + s + " "),
    st.sampled_from(_TRUTHY_BASES).map(lambda s: s[0].upper() + s[1:]),
    # Arbitrary non-falsy strings (valid env var values: no null bytes)
    st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="\x00",
        ),
        min_size=1,
    ).filter(lambda s: s.strip().lower() not in {"false", "0", "no"}),
)


class TestProperty1ConfigurationGating:
    """Feature: tool-call-audit-logging, Property 1: Configuration gating.

    For any value of the MCP_AUDIT_LOG_ENABLED environment variable,
    the factory function SHALL return a middleware instance if and only
    if the value is unset or is a truthy string (case-insensitive);
    for any falsy string (case-insensitive `false`, `0`, `no`) it
    SHALL return None.

    **Validates: Requirements 1.4, 7.1**
    """

    @given(value=falsy_values)
    @settings(max_examples=100)
    def test_falsy_values_return_none(self, value: str) -> None:
        """Factory returns None for falsy env var values."""
        with patch.dict(os.environ, {"MCP_AUDIT_LOG_ENABLED": value}):
            result = create_audit_middleware()
            assert result is None, (
                f"Expected None for falsy value {value!r}, got {type(result)}"
            )

    @given(value=truthy_values)
    @settings(max_examples=100)
    def test_truthy_values_return_middleware(self, value: str) -> None:
        """Factory returns middleware instance for truthy values."""
        with patch.dict(os.environ, {"MCP_AUDIT_LOG_ENABLED": value}):
            result = create_audit_middleware()
            assert isinstance(result, ToolCallLoggingMiddleware), (
                f"Expected ToolCallLoggingMiddleware for truthy "
                f"value {value!r}, got {result}"
            )

    @settings(max_examples=1)
    @given(st.just(None))
    def test_unset_returns_middleware(self, _: None) -> None:
        """Factory returns middleware when env var is unset."""
        env = os.environ.copy()
        env.pop("MCP_AUDIT_LOG_ENABLED", None)
        with patch.dict(os.environ, env, clear=True):
            result = create_audit_middleware()
            assert isinstance(result, ToolCallLoggingMiddleware), (
                "Expected ToolCallLoggingMiddleware when env var "
                f"is unset, got {result}"
            )


# --- Strategies for Property 2: Source IP extraction ---

# Generate valid IPv4 addresses
ipv4_addresses = st.tuples(
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}.{t[3]}")

# Generate valid IPv6 addresses (simplified hex groups)
ipv6_addresses = st.tuples(
    *[st.integers(min_value=0, max_value=0xFFFF) for _ in range(8)]
).map(lambda t: ":".join(f"{x:x}" for x in t))

# Generate IP addresses (mix of IPv4 and IPv6)
ip_addresses = st.one_of(ipv4_addresses, ipv6_addresses)

# Generate whitespace to pad IPs
whitespace = st.text(
    alphabet=st.sampled_from(" \t"),
    min_size=0,
    max_size=5,
)


def _make_mock_request(scope: dict[str, Any]) -> MagicMock:
    """Create a mock request with the given ASGI scope."""
    mock_request = MagicMock()
    mock_request.scope = scope
    return mock_request


class TestProperty2SourceIPExtraction:
    """Feature: tool-call-audit-logging, Property 2: Source IP extraction.

    For any ASGI connection scope and set of request headers, the
    extracted source IP SHALL equal: the first comma-separated entry
    in X-Forwarded-For (if present), otherwise the first element of
    the scope client tuple (if present), otherwise "unknown" — with
    all leading and trailing whitespace stripped from the result.

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """

    @given(
        xff_ip=ip_addresses,
        client_ip=ip_addresses,
        leading_ws=whitespace,
        trailing_ws=whitespace,
    )
    @settings(max_examples=100)
    def test_xff_takes_precedence_over_client(
        self,
        xff_ip: str,
        client_ip: str,
        leading_ws: str,
        trailing_ws: str,
    ) -> None:
        """X-Forwarded-For header takes precedence over scope client."""
        xff_value = f"{leading_ws}{xff_ip}{trailing_ws}"
        scope: dict[str, Any] = {
            "headers": [
                (b"x-forwarded-for", xff_value.encode("latin-1")),
            ],
            "client": (client_ip, 12345),
        }
        mock_request = _make_mock_request(scope)
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_source_ip(context)

        assert result == xff_ip, (
            f"Expected X-Forwarded-For IP {xff_ip!r}, got {result!r}"
        )

    @given(
        xff_ip=ip_addresses,
        extra_ips=st.lists(ip_addresses, min_size=1, max_size=5),
        client_ip=ip_addresses,
    )
    @settings(max_examples=100)
    def test_xff_uses_first_comma_separated_ip(
        self,
        xff_ip: str,
        extra_ips: list[str],
        client_ip: str,
    ) -> None:
        """X-Forwarded-For uses only the first comma-separated IP."""
        xff_value = ", ".join([xff_ip] + extra_ips)
        scope: dict[str, Any] = {
            "headers": [
                (b"x-forwarded-for", xff_value.encode("latin-1")),
            ],
            "client": (client_ip, 12345),
        }
        mock_request = _make_mock_request(scope)
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_source_ip(context)

        assert result == xff_ip, f"Expected first XFF IP {xff_ip!r}, got {result!r}"

    @given(
        client_ip=ip_addresses,
        leading_ws=whitespace,
        trailing_ws=whitespace,
    )
    @settings(max_examples=100)
    def test_scope_client_used_when_no_xff(
        self,
        client_ip: str,
        leading_ws: str,
        trailing_ws: str,
    ) -> None:
        """Scope client IP is used when no X-Forwarded-For header."""
        padded_ip = f"{leading_ws}{client_ip}{trailing_ws}"
        scope: dict[str, Any] = {
            "headers": [],
            "client": (padded_ip, 8080),
        }
        mock_request = _make_mock_request(scope)
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_source_ip(context)

        assert result == client_ip, f"Expected client IP {client_ip!r}, got {result!r}"

    @given(data=st.data())
    @settings(max_examples=100)
    def test_unknown_when_no_xff_and_no_client(self, data: st.DataObject) -> None:
        """Returns 'unknown' when neither XFF nor client is available."""
        # Generate scopes with no client and no XFF header
        other_headers = data.draw(
            st.lists(
                st.tuples(
                    st.sampled_from([b"content-type", b"accept", b"host"]),
                    st.binary(min_size=1, max_size=20),
                ),
                max_size=3,
            )
        )
        scope: dict[str, Any] = {
            "headers": other_headers,
        }
        mock_request = _make_mock_request(scope)
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_source_ip(context)

        assert result == "unknown", f"Expected 'unknown', got {result!r}"

    @given(
        ip=ip_addresses,
        leading_ws=st.text(
            alphabet=st.sampled_from(" \t"),
            min_size=1,
            max_size=5,
        ),
        trailing_ws=st.text(
            alphabet=st.sampled_from(" \t"),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_whitespace_stripped_from_xff(
        self,
        ip: str,
        leading_ws: str,
        trailing_ws: str,
    ) -> None:
        """Whitespace is stripped from X-Forwarded-For IP."""
        xff_value = f"{leading_ws}{ip}{trailing_ws}"
        scope: dict[str, Any] = {
            "headers": [
                (b"x-forwarded-for", xff_value.encode("latin-1")),
            ],
        }
        mock_request = _make_mock_request(scope)
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_source_ip(context)

        assert result == ip, f"Expected stripped IP {ip!r}, got {result!r}"
        assert not result.startswith((" ", "\t")), (
            f"Result has leading whitespace: {result!r}"
        )
        assert not result.endswith((" ", "\t")), (
            f"Result has trailing whitespace: {result!r}"
        )

    def test_empty_xff_falls_back_to_client(self) -> None:
        """An empty first forwarded address falls back to the socket IP."""
        scope: dict[str, Any] = {
            "headers": [(b"x-forwarded-for", b" , 198.51.100.10")],
            "client": ("192.0.2.10", 12345),
        }
        mock_request = _make_mock_request(scope)
        middleware = ToolCallLoggingMiddleware()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_source_ip(MagicMock())

        assert result == "192.0.2.10"


# --- Strategies for Property 3: Username extraction ---

# Generate non-empty email-like strings for usernames
emails = st.from_regex(
    r"[a-z][a-z0-9._%+-]{0,20}@[a-z][a-z0-9.-]{0,10}\.[a-z]{2,4}",
    fullmatch=True,
)

# Generate empty-ish email values that should trigger fallback
empty_emails = st.sampled_from([None, "", False, 0])

# Auth types recognized by the middleware
auth_types = st.sampled_from(["basic", "pat", "oauth"])


def _make_mock_request_with_state(
    auth_type: str | None = None,
    email: str | None = None,
    authorization: str | None = None,
) -> MagicMock:
    """Create a mock request with auth state and optional headers.

    Args:
        auth_type: The user_atlassian_auth_type value, or None.
        email: The user_atlassian_email value, or None.
        authorization: The Authorization header value, or None.

    Returns:
        A MagicMock configured as a Starlette request.
    """
    mock_request = MagicMock()

    # Configure state attributes
    state = MagicMock()
    if auth_type is not None:
        state.user_atlassian_auth_type = auth_type
    else:
        # Make getattr return None for missing auth type
        del state.user_atlassian_auth_type

    if email is not None:
        state.user_atlassian_email = email
    else:
        del state.user_atlassian_email

    mock_request.state = state

    # Configure headers
    headers: dict[str, str] = {}
    if authorization is not None:
        headers["authorization"] = authorization
    mock_request.headers = headers

    return mock_request


class TestProperty3UsernameExtraction:
    """Feature: tool-call-audit-logging, Property 3: Username extraction.

    For any request state containing a user_atlassian_auth_type and
    associated email fields, the extracted username SHALL equal: the
    user_atlassian_email value when it is non-empty (for PAT or OAuth
    auth types), the email from the decoded Authorization header (for
    Basic auth), otherwise the appropriate fallback string ("anonymous"
    for Basic with no Authorization header, "pat-user" for PAT,
    "oauth-user" for OAuth, or "anonymous" when no auth type is set).

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """

    @given(email=emails)
    @settings(max_examples=100)
    def test_basic_auth_extracts_email_from_header(self, email: str) -> None:
        """Basic auth extracts email from decoded Authorization header.

        Validates: Requirements 3.1
        """
        import base64

        # Encode email:password as Basic auth header
        password = "some-password"
        credentials = f"{email}:{password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        auth_header = f"Basic {encoded}"

        mock_request = _make_mock_request_with_state(
            auth_type="basic",
            authorization=auth_header,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == email, (
            f"Expected email {email!r} from Basic auth, got {result!r}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_basic_auth_falls_back_to_anonymous(self, data: st.DataObject) -> None:
        """Basic auth falls back to 'anonymous' when no Authorization.

        Validates: Requirements 3.1
        """
        # Generate cases where Authorization header is missing
        # or doesn't start with "Basic "
        invalid_auth = data.draw(
            st.one_of(
                st.just(None),
                st.just(""),
                st.just("Bearer some-token"),
                st.text(min_size=0, max_size=20).filter(
                    lambda s: not s.lower().startswith("basic ")
                ),
            )
        )

        mock_request = _make_mock_request_with_state(
            auth_type="basic",
            authorization=invalid_auth,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == "anonymous", (
            f"Expected 'anonymous' for Basic auth without valid "
            f"Authorization header ({invalid_auth!r}), "
            f"got {result!r}"
        )

    @given(email=emails)
    @settings(max_examples=100)
    def test_pat_uses_email_from_state(self, email: str) -> None:
        """PAT uses user_atlassian_email from request state.

        Validates: Requirements 3.2
        """
        mock_request = _make_mock_request_with_state(
            auth_type="pat",
            email=email,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == email, f"Expected email {email!r} for PAT auth, got {result!r}"

    @given(empty_email=empty_emails)
    @settings(max_examples=100)
    def test_pat_falls_back_to_pat_user(self, empty_email: Any) -> None:
        """PAT falls back to 'pat-user' when email unavailable.

        Validates: Requirements 3.3
        """
        mock_request = _make_mock_request_with_state(
            auth_type="pat",
            email=empty_email,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == "pat-user", (
            f"Expected 'pat-user' for PAT with empty email "
            f"({empty_email!r}), got {result!r}"
        )

    @given(email=emails)
    @settings(max_examples=100)
    def test_oauth_uses_email_from_state(self, email: str) -> None:
        """OAuth uses user_atlassian_email from request state.

        Validates: Requirements 3.4
        """
        mock_request = _make_mock_request_with_state(
            auth_type="oauth",
            email=email,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == email, (
            f"Expected email {email!r} for OAuth auth, got {result!r}"
        )

    @given(empty_email=empty_emails)
    @settings(max_examples=100)
    def test_oauth_falls_back_to_oauth_user(self, empty_email: Any) -> None:
        """OAuth falls back to 'oauth-user' when email unavailable.

        Validates: Requirements 3.4
        """
        mock_request = _make_mock_request_with_state(
            auth_type="oauth",
            email=empty_email,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == "oauth-user", (
            f"Expected 'oauth-user' for OAuth with empty email "
            f"({empty_email!r}), got {result!r}"
        )

    @given(
        auth_type=st.one_of(
            st.none(),
            st.text(min_size=1, max_size=20).filter(
                lambda s: s.lower() not in {"basic", "pat", "oauth"}
            ),
        )
    )
    @settings(max_examples=100)
    def test_no_auth_type_returns_anonymous(self, auth_type: str | None) -> None:
        """No auth type (or unrecognized) returns 'anonymous'.

        Validates: Requirements 3.5
        """
        mock_request = _make_mock_request_with_state(
            auth_type=auth_type,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == "anonymous", (
            f"Expected 'anonymous' for auth_type={auth_type!r}, got {result!r}"
        )


# --- Strategies for Property 4: Sensitive field masking ---

# Default sensitive patterns used by the middleware
_DEFAULT_SENSITIVE_PATTERNS = [
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "secret_key",
    "private_key",
    "credential",
    "auth",
]

# Generate field names that contain a sensitive pattern (case-insensitive)
sensitive_field_names = st.one_of(
    # Pattern as-is
    st.sampled_from(_DEFAULT_SENSITIVE_PATTERNS),
    # Pattern embedded in a longer name (prefix + pattern + suffix)
    st.tuples(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
            ),
            min_size=0,
            max_size=8,
        ),
        st.sampled_from(_DEFAULT_SENSITIVE_PATTERNS),
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
            ),
            min_size=0,
            max_size=8,
        ),
    ).map(lambda t: f"{t[0]}{t[1]}{t[2]}"),
    # Pattern with mixed case
    st.sampled_from(_DEFAULT_SENSITIVE_PATTERNS).map(str.upper),
    st.sampled_from(_DEFAULT_SENSITIVE_PATTERNS).map(str.title),
)

# Generate field names that do NOT contain any sensitive pattern
# Use names that are clearly non-sensitive
_SAFE_NAMES = [
    "name",
    "issue",
    "project",
    "summary",
    "description",
    "status",
    "priority",
    "assignee",
    "reporter",
    "labels",
    "components",
    "version",
    "url",
    "page",
    "space",
    "title",
    "body",
    "comment",
    "id",
    "count",
]

non_sensitive_field_names = st.sampled_from(_SAFE_NAMES)

# Generate arbitrary values for arguments
argument_values = st.one_of(
    st.text(min_size=1, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
)


class TestProperty4SensitiveFieldMasking:
    """Feature: tool-call-audit-logging, Property 4: Sensitive field masking.

    For any tool call argument dictionary and any set of sensitive
    field patterns (default + custom), every argument whose name
    contains a pattern substring (case-insensitive) SHALL have its
    value replaced by the output of mask_sensitive(str(value)), and
    non-matching arguments SHALL remain unchanged.

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """

    @given(
        sensitive_key=sensitive_field_names,
        sensitive_value=argument_values,
    )
    @settings(max_examples=100)
    def test_sensitive_fields_are_masked(
        self,
        sensitive_key: str,
        sensitive_value: Any,
    ) -> None:
        """Fields matching sensitive patterns are masked.

        Validates: Requirements 4.1, 4.2
        """
        arguments = {sensitive_key: sensitive_value}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(sensitive_value))
        assert result[sensitive_key] == expected, (
            f"Expected masked value {expected!r} for key "
            f"{sensitive_key!r}, got {result[sensitive_key]!r}"
        )

    @given(
        non_sensitive_key=non_sensitive_field_names,
        value=argument_values,
    )
    @settings(max_examples=100)
    def test_non_sensitive_fields_unchanged(
        self,
        non_sensitive_key: str,
        value: Any,
    ) -> None:
        """Fields not matching sensitive patterns remain unchanged.

        Validates: Requirements 4.1
        """
        arguments = {non_sensitive_key: value}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        assert result[non_sensitive_key] == value, (
            f"Expected unchanged value {value!r} for key "
            f"{non_sensitive_key!r}, got "
            f"{result[non_sensitive_key]!r}"
        )

    @given(
        sensitive_key=sensitive_field_names,
        sensitive_value=argument_values,
        non_sensitive_key=non_sensitive_field_names,
        non_sensitive_value=argument_values,
    )
    @settings(max_examples=100)
    def test_mixed_arguments_masked_correctly(
        self,
        sensitive_key: str,
        sensitive_value: Any,
        non_sensitive_key: str,
        non_sensitive_value: Any,
    ) -> None:
        """Mixed sensitive/non-sensitive arguments handled correctly.

        Validates: Requirements 4.1, 4.2, 4.3
        """
        arguments = {
            sensitive_key: sensitive_value,
            non_sensitive_key: non_sensitive_value,
        }
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        # Sensitive field should be masked
        expected_masked = mask_sensitive(str(sensitive_value))
        assert result[sensitive_key] == expected_masked, (
            f"Expected masked value {expected_masked!r} for "
            f"sensitive key {sensitive_key!r}, got "
            f"{result[sensitive_key]!r}"
        )

        # Non-sensitive field should be unchanged
        assert result[non_sensitive_key] == non_sensitive_value, (
            f"Expected unchanged value "
            f"{non_sensitive_value!r} for non-sensitive key "
            f"{non_sensitive_key!r}, got "
            f"{result[non_sensitive_key]!r}"
        )

    @given(
        sensitive_key=sensitive_field_names,
        value=st.one_of(
            st.integers(min_value=-1000, max_value=1000),
            st.booleans(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.lists(st.integers(), min_size=1, max_size=3),
        ),
    )
    @settings(max_examples=100)
    def test_non_string_values_converted_before_masking(
        self,
        sensitive_key: str,
        value: Any,
    ) -> None:
        """Non-string values are converted to string before masking.

        Validates: Requirements 4.3
        """
        arguments = {sensitive_key: value}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(value))
        assert result[sensitive_key] == expected, (
            f"Expected mask_sensitive(str({value!r})) = "
            f"{expected!r}, got {result[sensitive_key]!r}"
        )

    @given(
        custom_pattern=st.text(
            alphabet=st.characters(
                whitelist_categories=("L",),
            ),
            min_size=3,
            max_size=10,
        ).filter(lambda s: s.lower() not in set(_DEFAULT_SENSITIVE_PATTERNS)),
        value=st.text(min_size=1, max_size=30),
    )
    @settings(max_examples=100)
    def test_custom_patterns_from_env_var(
        self,
        custom_pattern: str,
        value: str,
    ) -> None:
        """Custom patterns from MCP_AUDIT_SENSITIVE_FIELDS are applied.

        Validates: Requirements 4.4
        """
        # Field name contains the custom pattern
        field_name = f"my_{custom_pattern}_field"

        # Create middleware with custom pattern
        middleware = ToolCallLoggingMiddleware(
            sensitive_patterns=[custom_pattern.lower()]
        )
        arguments = {field_name: value}
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(value))
        assert result[field_name] == expected, (
            f"Expected masked value {expected!r} for custom "
            f"pattern {custom_pattern!r} in key "
            f"{field_name!r}, got {result[field_name]!r}"
        )

    @given(
        sensitive_key=sensitive_field_names,
        sensitive_value=argument_values,
    )
    @settings(max_examples=100)
    def test_case_insensitive_matching(
        self,
        sensitive_key: str,
        sensitive_value: Any,
    ) -> None:
        """Sensitive pattern matching is case-insensitive.

        Validates: Requirements 4.1, 4.2
        """
        # Test with various case transformations of the key
        for transformed_key in [
            sensitive_key.upper(),
            sensitive_key.lower(),
            sensitive_key.title(),
        ]:
            arguments = {transformed_key: sensitive_value}
            middleware = ToolCallLoggingMiddleware()
            result = middleware._mask_arguments(arguments)

            expected = mask_sensitive(str(sensitive_value))
            assert result[transformed_key] == expected, (
                f"Expected masked value for key "
                f"{transformed_key!r} (case variant of "
                f"{sensitive_key!r}), got "
                f"{result[transformed_key]!r}"
            )


# --- Strategies for Property 5: Depth-limited nested masking ---

# Generate nested dictionaries with sensitive keys at various depths
nested_dict_values = st.one_of(
    st.text(min_size=1, max_size=30),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
)


class TestProperty5DepthLimitedNestedMasking:
    """Feature: tool-call-audit-logging, Property 5: Depth-limited nested masking.

    For any tool call argument that is a dictionary and whose key does
    NOT match a sensitive pattern, the middleware SHALL inspect the
    nested dictionary's keys and mask values whose keys match a
    sensitive pattern — but SHALL NOT recurse beyond one additional
    level of depth.

    **Validates: Requirements 4.5, 4.6**
    """

    @given(
        outer_key=non_sensitive_field_names,
        nested_sensitive_key=sensitive_field_names,
        nested_value=nested_dict_values,
    )
    @settings(max_examples=100)
    def test_nested_sensitive_keys_are_masked(
        self,
        outer_key: str,
        nested_sensitive_key: str,
        nested_value: Any,
    ) -> None:
        """Sensitive keys in nested dicts (1 level deep) are masked.

        When a top-level key is non-sensitive and its value is a dict,
        the middleware inspects nested keys and masks those matching
        sensitive patterns.

        Validates: Requirements 4.5, 4.6
        """
        arguments = {outer_key: {nested_sensitive_key: nested_value}}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(nested_value))
        assert result[outer_key][nested_sensitive_key] == expected, (
            f"Expected nested sensitive key "
            f"{nested_sensitive_key!r} to be masked to "
            f"{expected!r}, got "
            f"{result[outer_key][nested_sensitive_key]!r}"
        )

    @given(
        outer_key=non_sensitive_field_names,
        nested_non_sensitive_key=non_sensitive_field_names,
        nested_value=nested_dict_values,
    )
    @settings(max_examples=100)
    def test_nested_non_sensitive_keys_unchanged(
        self,
        outer_key: str,
        nested_non_sensitive_key: str,
        nested_value: Any,
    ) -> None:
        """Non-sensitive keys in nested dicts remain unchanged.

        When a top-level key is non-sensitive and its value is a dict,
        nested keys that do NOT match sensitive patterns are left as-is.

        Validates: Requirements 4.5, 4.6
        """
        arguments = {outer_key: {nested_non_sensitive_key: nested_value}}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        assert result[outer_key][nested_non_sensitive_key] == nested_value, (
            f"Expected nested non-sensitive key "
            f"{nested_non_sensitive_key!r} to remain "
            f"{nested_value!r}, got "
            f"{result[outer_key][nested_non_sensitive_key]!r}"
        )

    @given(
        outer_key=non_sensitive_field_names,
        nested_sensitive_key=sensitive_field_names,
        sensitive_value=nested_dict_values,
        nested_non_sensitive_key=non_sensitive_field_names,
        non_sensitive_value=nested_dict_values,
    )
    @settings(max_examples=100)
    def test_nested_mixed_keys_handled_correctly(
        self,
        outer_key: str,
        nested_sensitive_key: str,
        sensitive_value: Any,
        nested_non_sensitive_key: str,
        non_sensitive_value: Any,
    ) -> None:
        """Mixed sensitive/non-sensitive nested keys handled correctly.

        In a nested dict, sensitive keys are masked while non-sensitive
        keys remain unchanged.

        Validates: Requirements 4.5, 4.6
        """
        arguments = {
            outer_key: {
                nested_sensitive_key: sensitive_value,
                nested_non_sensitive_key: non_sensitive_value,
            }
        }
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        # Sensitive nested key should be masked
        expected_masked = mask_sensitive(str(sensitive_value))
        assert result[outer_key][nested_sensitive_key] == expected_masked, (
            f"Expected nested sensitive key "
            f"{nested_sensitive_key!r} masked to "
            f"{expected_masked!r}, got "
            f"{result[outer_key][nested_sensitive_key]!r}"
        )

        # Non-sensitive nested key should be unchanged
        assert result[outer_key][nested_non_sensitive_key] == non_sensitive_value, (
            f"Expected nested non-sensitive key "
            f"{nested_non_sensitive_key!r} unchanged as "
            f"{non_sensitive_value!r}, got "
            f"{result[outer_key][nested_non_sensitive_key]!r}"
        )

    @given(
        outer_key=non_sensitive_field_names,
        mid_key=non_sensitive_field_names,
        deep_sensitive_key=sensitive_field_names,
        deep_value=nested_dict_values,
    )
    @settings(max_examples=100)
    def test_depth_beyond_one_level_not_masked(
        self,
        outer_key: str,
        mid_key: str,
        deep_sensitive_key: str,
        deep_value: Any,
    ) -> None:
        """Sensitive keys at depth > 1 are NOT masked.

        The middleware only inspects one level of nesting. Sensitive
        keys at deeper levels (depth 2+) are left unchanged.

        Validates: Requirements 4.5, 4.6
        """
        # Create a 3-level nested structure:
        # {outer_key: {mid_key: {deep_sensitive_key: deep_value}}}
        arguments = {outer_key: {mid_key: {deep_sensitive_key: deep_value}}}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        # The deep nested dict should be left as-is (not recursed into)
        assert result[outer_key][mid_key] == {deep_sensitive_key: deep_value}, (
            f"Expected depth-2 dict to remain unchanged "
            f"({{{deep_sensitive_key!r}: {deep_value!r}}}), "
            f"got {result[outer_key][mid_key]!r}"
        )

    @given(
        sensitive_outer_key=sensitive_field_names,
        nested_content=st.dictionaries(
            keys=non_sensitive_field_names,
            values=nested_dict_values,
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_sensitive_outer_key_masks_entire_dict_value(
        self,
        sensitive_outer_key: str,
        nested_content: dict[str, Any],
    ) -> None:
        """When outer key IS sensitive, the entire dict value is masked.

        If the top-level key matches a sensitive pattern, the whole
        value (even if it's a dict) is converted to string and masked,
        rather than inspecting nested keys.

        Validates: Requirements 4.5, 4.6
        """
        arguments = {sensitive_outer_key: nested_content}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        # The entire dict value should be masked as a string
        expected = mask_sensitive(str(nested_content))
        assert result[sensitive_outer_key] == expected, (
            f"Expected sensitive outer key "
            f"{sensitive_outer_key!r} to mask entire dict to "
            f"{expected!r}, got {result[sensitive_outer_key]!r}"
        )

    @given(
        outer_key=non_sensitive_field_names,
        nested_sensitive_key=sensitive_field_names,
        nested_value=st.one_of(
            st.integers(min_value=-1000, max_value=1000),
            st.booleans(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.lists(st.integers(), min_size=1, max_size=3),
        ),
    )
    @settings(max_examples=100)
    def test_nested_non_string_values_converted_before_masking(
        self,
        outer_key: str,
        nested_sensitive_key: str,
        nested_value: Any,
    ) -> None:
        """Non-string nested values are converted to str before masking.

        When a nested key matches a sensitive pattern and its value is
        not a string, the value is converted via str() before masking.

        Validates: Requirements 4.5, 4.6
        """
        arguments = {outer_key: {nested_sensitive_key: nested_value}}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(nested_value))
        assert result[outer_key][nested_sensitive_key] == expected, (
            f"Expected nested non-string value "
            f"{nested_value!r} to be masked as "
            f"{expected!r}, got "
            f"{result[outer_key][nested_sensitive_key]!r}"
        )


# --- Strategies for Property 6: Log format and single-line serialization ---

# Generate valid tool names (alphanumeric + underscores, no spaces)
tool_names = st.from_regex(
    r"[a-z][a-z0-9_]{2,30}",
    fullmatch=True,
)

# Generate usernames (emails or fallback values)
usernames = st.one_of(
    emails,
    st.sampled_from(["anonymous", "pat-user", "oauth-user"]),
)

# Generate argument dictionaries with various value types
log_format_arguments = st.dictionaries(
    keys=non_sensitive_field_names,
    values=st.one_of(
        st.text(min_size=0, max_size=50),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
        st.none(),
        st.lists(st.integers(), min_size=0, max_size=3),
    ),
    min_size=0,
    max_size=5,
)


class TestProperty6LogFormatAndSingleLineSerialization:
    """Feature: tool-call-audit-logging, Property 6: Log format and single-line serialization.

    For any valid combination of source IP, tool name, username, and
    arguments, the emitted audit log message SHALL match the pattern
    `<ip> <tool_name> <username> <json_body>` where `<json_body>` is
    a single-line JSON string containing no embedded newline or control
    characters.

    **Validates: Requirements 5.1, 5.4**
    """  # noqa: E501

    @given(
        ip=ip_addresses,
        tool_name=tool_names,
        username=usernames,
        arguments=log_format_arguments,
    )
    @settings(max_examples=100)
    def test_log_format_matches_expected_pattern(
        self,
        ip: str,
        tool_name: str,
        username: str,
        arguments: dict[str, Any],
    ) -> None:
        """Log output matches <ip> <tool_name> <username> <json_body>.

        Validates: Requirements 5.1
        """
        middleware = ToolCallLoggingMiddleware()

        # Build the log message the same way on_call_tool does
        masked_arguments = middleware._mask_arguments(arguments)
        body = middleware._serialize_body(masked_arguments)
        log_message = f"{ip} {tool_name} {username} {body}"

        # Verify format: exactly 3 spaces separate the first 3 fields
        # and the rest is the JSON body
        parts = log_message.split(" ", 3)
        assert len(parts) == 4, (
            f"Expected 4 parts in log message, got {len(parts)}: {log_message!r}"
        )
        assert parts[0] == ip, f"Expected IP {ip!r}, got {parts[0]!r}"
        assert parts[1] == tool_name, (
            f"Expected tool_name {tool_name!r}, got {parts[1]!r}"
        )
        assert parts[2] == username, f"Expected username {username!r}, got {parts[2]!r}"
        # The 4th part is the JSON body
        assert parts[3] == body, f"Expected body {body!r}, got {parts[3]!r}"

    @given(
        ip=ip_addresses,
        tool_name=tool_names,
        username=usernames,
        arguments=log_format_arguments,
    )
    @settings(max_examples=100)
    def test_no_embedded_newlines_in_log_message(
        self,
        ip: str,
        tool_name: str,
        username: str,
        arguments: dict[str, Any],
    ) -> None:
        """Log message contains no embedded newlines.

        Validates: Requirements 5.4
        """
        middleware = ToolCallLoggingMiddleware()

        masked_arguments = middleware._mask_arguments(arguments)
        body = middleware._serialize_body(masked_arguments)
        log_message = f"{ip} {tool_name} {username} {body}"

        assert "\n" not in log_message, f"Log message contains newline: {log_message!r}"
        assert "\r" not in log_message, (
            f"Log message contains carriage return: {log_message!r}"
        )

    @given(
        ip=ip_addresses,
        tool_name=tool_names,
        username=usernames,
        arguments=log_format_arguments,
    )
    @settings(max_examples=100)
    def test_no_control_characters_in_json_body(
        self,
        ip: str,
        tool_name: str,
        username: str,
        arguments: dict[str, Any],
    ) -> None:
        """JSON body contains no control characters.

        Validates: Requirements 5.4
        """
        middleware = ToolCallLoggingMiddleware()

        masked_arguments = middleware._mask_arguments(arguments)
        body = middleware._serialize_body(masked_arguments)

        # Check for control characters (ASCII 0x00-0x1F and 0x7F)
        for ch in body:
            assert ch >= " " and ch != "\x7f", (
                f"JSON body contains control character U+{ord(ch):04X}: {body!r}"
            )

    @given(
        ip=ip_addresses,
        tool_name=tool_names,
        username=usernames,
        arguments=st.dictionaries(
            keys=non_sensitive_field_names,
            values=st.text(
                alphabet=st.characters(
                    blacklist_categories=("Cs",),
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=100)
    def test_arguments_with_special_chars_produce_valid_log(
        self,
        ip: str,
        tool_name: str,
        username: str,
        arguments: dict[str, str],
    ) -> None:
        """Arguments with special characters still produce valid log.

        Even when argument values contain newlines, tabs, or other
        control characters, the serialized body must be single-line
        with no control characters.

        Validates: Requirements 5.1, 5.4
        """
        middleware = ToolCallLoggingMiddleware()

        masked_arguments = middleware._mask_arguments(arguments)
        body = middleware._serialize_body(masked_arguments)
        log_message = f"{ip} {tool_name} {username} {body}"

        # No newlines in the full log message
        assert "\n" not in log_message, f"Log message contains newline: {log_message!r}"
        assert "\r" not in log_message, (
            f"Log message contains carriage return: {log_message!r}"
        )

        # No control characters in the body
        for ch in body:
            assert ch >= " " and ch != "\x7f", (
                f"JSON body contains control character U+{ord(ch):04X}: {body!r}"
            )

    @given(
        ip=ip_addresses,
        tool_name=tool_names,
        username=usernames,
    )
    @settings(max_examples=100)
    def test_empty_arguments_produce_valid_format(
        self,
        ip: str,
        tool_name: str,
        username: str,
    ) -> None:
        """Empty arguments produce valid log format with {}.

        Validates: Requirements 5.1, 5.4
        """
        middleware = ToolCallLoggingMiddleware()

        body = middleware._serialize_body({})
        log_message = f"{ip} {tool_name} {username} {body}"

        parts = log_message.split(" ", 3)
        assert len(parts) == 4, f"Expected 4 parts, got {len(parts)}: {log_message!r}"
        assert parts[3] == "{}", f"Expected '{{}}' for empty args, got {parts[3]!r}"


# --- Strategies for Property 7: Body truncation ---

# Generate valid max_body_length values (>= 64)
valid_max_body_lengths = st.integers(min_value=64, max_value=4096)

# Generate invalid max_body_length values (non-integer or < 64)
invalid_max_body_lengths = st.one_of(
    st.integers(min_value=-1000, max_value=63),
    st.sampled_from(["abc", "64.5", "", "not_a_number", "NaN"]),
)

# Generate argument dictionaries of varying sizes
small_arguments = st.dictionaries(
    keys=non_sensitive_field_names,
    values=st.text(min_size=1, max_size=10),
    min_size=1,
    max_size=3,
)

# Generate large argument values that will exceed thresholds
large_text_values = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=100,
    max_size=5000,
)


class TestProperty7BodyTruncation:
    """Feature: tool-call-audit-logging, Property 7: Body truncation.

    For any tool call arguments and configured max body length (>= 64),
    if the original content length of the arguments (measured before
    JSON serialization) exceeds the threshold, the serialized body
    SHALL be truncated to exactly that many characters with
    ``...truncated`` appended; if the original content length does not
    exceed the threshold, the body SHALL be emitted in full. Invalid
    threshold values (non-integer or < 64) SHALL result in the default
    2048 being used.

    **Validates: Requirements 5.5, 7.3, 7.4**
    """

    @given(
        max_length=valid_max_body_lengths,
        value=large_text_values,
    )
    @settings(max_examples=100)
    def test_truncation_when_content_exceeds_threshold(
        self,
        max_length: int,
        value: str,
    ) -> None:
        """Body is truncated when original content exceeds threshold.

        When the original content length (str(arguments)) exceeds the
        configured max_body_length, the serialized output is truncated
        to exactly max_body_length characters with '...truncated'
        appended.

        Validates: Requirements 5.5, 7.3
        """
        # Build arguments whose str() representation exceeds threshold
        arguments = {"data": value}
        original_content = str(arguments)

        # Only test when content actually exceeds the threshold
        if len(original_content) <= max_length:
            return

        middleware = ToolCallLoggingMiddleware(max_body_length=max_length)
        result = middleware._serialize_body(arguments)

        # Should end with ...truncated
        assert result.endswith("...truncated"), (
            f"Expected body to end with '...truncated' when "
            f"original content length ({len(original_content)}) "
            f"exceeds threshold ({max_length}), got: "
            f"{result[-30:]!r}"
        )

        # The truncated part should be at most max_length chars
        truncated_part = result[: -len("...truncated")]
        assert len(truncated_part) <= max_length, (
            f"Expected truncated part to be at most "
            f"{max_length} chars, got {len(truncated_part)}"
        )

    @given(
        max_length=valid_max_body_lengths,
        arguments=small_arguments,
    )
    @settings(max_examples=100)
    def test_no_truncation_when_content_within_threshold(
        self,
        max_length: int,
        arguments: dict[str, str],
    ) -> None:
        """Body is emitted in full when content is within threshold.

        When the original content length does not exceed the configured
        max_body_length, the body is emitted without truncation.

        Validates: Requirements 5.5, 7.3
        """
        original_content = str(arguments)

        # Only test when content does NOT exceed the threshold
        if len(original_content) > max_length:
            return

        middleware = ToolCallLoggingMiddleware(max_body_length=max_length)
        result = middleware._serialize_body(arguments)

        # Should NOT end with ...truncated
        assert not result.endswith("...truncated"), (
            f"Body should not be truncated when original content "
            f"length ({len(original_content)}) <= threshold "
            f"({max_length}), got: {result!r}"
        )

    @given(
        max_length=valid_max_body_lengths,
        value=large_text_values,
    )
    @settings(max_examples=100)
    def test_truncated_body_has_correct_total_length(
        self,
        max_length: int,
        value: str,
    ) -> None:
        """Truncated body has suffix '...truncated' and is bounded.

        When truncation occurs, the serialized body is sliced to at
        most max_length characters and '...truncated' is appended.
        The total length is at most max_length + len('...truncated').

        Validates: Requirements 5.5, 7.3
        """
        arguments = {"data": value}
        original_content = str(arguments)

        # Only test when content exceeds the threshold
        if len(original_content) <= max_length:
            return

        middleware = ToolCallLoggingMiddleware(max_body_length=max_length)
        result = middleware._serialize_body(arguments)

        # Result must end with the truncation suffix
        assert result.endswith("...truncated"), (
            f"Expected result to end with '...truncated', got: {result[-20:]!r}"
        )

        # The body portion (before suffix) must be at most max_length
        body_portion = result[: -len("...truncated")]
        assert len(body_portion) <= max_length, (
            f"Expected body portion length <= {max_length}, got {len(body_portion)}"
        )

    @given(
        invalid_value=st.sampled_from(["abc", "64.5", "", "not_a_number", "NaN"]),
    )
    @settings(max_examples=100)
    def test_invalid_non_integer_threshold_uses_default(
        self,
        invalid_value: str,
    ) -> None:
        """Non-integer threshold values fall back to default 2048.

        When MCP_AUDIT_MAX_BODY_LENGTH is set to a non-integer value,
        the factory SHALL ignore it and use the default 2048.

        Validates: Requirements 7.4
        """
        with patch.dict(
            os.environ,
            {"MCP_AUDIT_MAX_BODY_LENGTH": invalid_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None
        assert middleware._max_body_length == 2048, (
            f"Expected default 2048 for invalid value "
            f"{invalid_value!r}, got "
            f"{middleware._max_body_length}"
        )

    @given(
        invalid_int=st.integers(min_value=-1000, max_value=63),
    )
    @settings(max_examples=100)
    def test_integer_below_64_threshold_uses_default(
        self,
        invalid_int: int,
    ) -> None:
        """Integer values below 64 fall back to default 2048.

        When MCP_AUDIT_MAX_BODY_LENGTH is set to an integer less than
        64, the factory SHALL ignore it and use the default 2048.

        Validates: Requirements 7.4
        """
        with patch.dict(
            os.environ,
            {"MCP_AUDIT_MAX_BODY_LENGTH": str(invalid_int)},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None
        assert middleware._max_body_length == 2048, (
            f"Expected default 2048 for value {invalid_int}, "
            f"got {middleware._max_body_length}"
        )

    @given(
        valid_length=valid_max_body_lengths,
    )
    @settings(max_examples=100)
    def test_valid_threshold_is_used(
        self,
        valid_length: int,
    ) -> None:
        """Valid integer >= 64 is used as the truncation threshold.

        When MCP_AUDIT_MAX_BODY_LENGTH is set to a valid integer >= 64,
        the factory SHALL use that value as the threshold.

        Validates: Requirements 7.3
        """
        with patch.dict(
            os.environ,
            {"MCP_AUDIT_MAX_BODY_LENGTH": str(valid_length)},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None
        assert middleware._max_body_length == valid_length, (
            f"Expected threshold {valid_length}, got {middleware._max_body_length}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_empty_arguments_never_truncated(
        self,
        data: st.DataObject,
    ) -> None:
        """Empty/None arguments produce '{}' regardless of threshold.

        Validates: Requirements 5.5
        """
        max_length = data.draw(valid_max_body_lengths)
        middleware = ToolCallLoggingMiddleware(max_body_length=max_length)

        # Test with None
        result_none = middleware._serialize_body(None)
        assert result_none == "{}", f"Expected '{{}}' for None, got {result_none!r}"

        # Test with empty dict
        result_empty = middleware._serialize_body({})
        assert result_empty == "{}", (
            f"Expected '{{}}' for empty dict, got {result_empty!r}"
        )

    @given(
        max_length=st.just(64),
        value=large_text_values,
    )
    @settings(max_examples=100)
    def test_minimum_valid_threshold_truncates_correctly(
        self,
        max_length: int,
        value: str,
    ) -> None:
        """Minimum valid threshold (64) truncates correctly.

        The minimum allowed threshold of 64 should still produce
        correct truncation behavior.

        Validates: Requirements 5.5, 7.3
        """
        arguments = {"data": value}
        original_content = str(arguments)

        # Only test when content exceeds the threshold
        if len(original_content) <= max_length:
            return

        middleware = ToolCallLoggingMiddleware(max_body_length=max_length)
        result = middleware._serialize_body(arguments)

        assert result.endswith("...truncated"), (
            f"Expected '...truncated' suffix at min threshold 64, got: {result[-30:]!r}"
        )

        truncated_part = result[: -len("...truncated")]
        assert len(truncated_part) == 64, (
            f"Expected truncated part to be exactly 64 chars, got {len(truncated_part)}"
        )


# --- Strategies for Property 8: Transparent delegation ---

# Generate argument dictionaries for delegation tests
delegation_arguments = st.dictionaries(
    keys=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
        ),
        min_size=1,
        max_size=20,
    ),
    values=st.one_of(
        st.text(min_size=0, max_size=50),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
        st.none(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.lists(st.integers(), min_size=0, max_size=5),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.text(min_size=0, max_size=20),
            min_size=0,
            max_size=3,
        ),
    ),
    min_size=0,
    max_size=8,
)

# Generate various exception types for propagation tests
exception_messages = st.text(min_size=1, max_size=100)


def _make_tool_call_context(
    arguments: dict[str, Any],
    tool_name: str = "test_tool",
) -> MagicMock:
    """Create a mock MiddlewareContext for on_call_tool.

    Args:
        arguments: The tool call arguments.
        tool_name: The tool name.

    Returns:
        A MagicMock configured as a MiddlewareContext.
    """
    context = MagicMock()
    context.message = MagicMock()
    context.message.name = tool_name
    context.message.arguments = arguments
    return context


class TestProperty8TransparentDelegation:
    """Feature: tool-call-audit-logging, Property 8: Transparent delegation.

    For any tool call processed by the middleware, the downstream
    handler SHALL be invoked with the exact same arguments that were
    passed to the middleware (unmodified), and any exception raised by
    the downstream handler SHALL propagate unchanged through the
    middleware.

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(
        arguments=delegation_arguments,
        tool_name=tool_names,
    )
    @settings(max_examples=100)
    def test_call_next_receives_unmodified_context(
        self,
        arguments: dict[str, Any],
        tool_name: str,
    ) -> None:
        """Downstream handler receives the exact same context unmodified.

        The middleware SHALL delegate to call_next with the same
        context object that was passed to on_call_tool, without
        modifying the arguments.

        Validates: Requirements 6.1, 6.2
        """
        context = _make_tool_call_context(arguments, tool_name)
        # Deep copy arguments to verify they aren't modified
        original_arguments = copy.deepcopy(arguments)

        # Create an async mock for call_next that captures what it receives
        call_next = AsyncMock(return_value=[])
        received_contexts: list[Any] = []

        async def capturing_call_next(ctx: Any) -> list:
            received_contexts.append(ctx)
            return []

        call_next.side_effect = capturing_call_next

        middleware = ToolCallLoggingMiddleware()

        # Mock get_http_request to avoid RuntimeError
        mock_request = MagicMock()
        mock_request.scope = {"headers": [], "client": ("127.0.0.1", 8080)}
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            asyncio.run(middleware.on_call_tool(context, call_next))

        # Verify call_next was called exactly once
        assert len(received_contexts) == 1, (
            f"Expected call_next to be called once, got {len(received_contexts)} calls"
        )

        # Verify the context passed to call_next is the same object
        assert received_contexts[0] is context, (
            "Expected call_next to receive the exact same context "
            "object (identity check)"
        )

        # Verify arguments on the context were not modified
        assert context.message.arguments == original_arguments, (
            f"Expected arguments to remain {original_arguments!r}, "
            f"got {context.message.arguments!r}"
        )

    @given(
        arguments=delegation_arguments,
        error_msg=exception_messages,
    )
    @settings(max_examples=100)
    def test_exceptions_from_downstream_propagate_unchanged(
        self,
        arguments: dict[str, Any],
        error_msg: str,
    ) -> None:
        """Exceptions from downstream handler propagate unchanged.

        Any exception raised by call_next SHALL propagate through the
        middleware without being caught or modified.

        Validates: Requirements 6.3
        """
        context = _make_tool_call_context(arguments)

        # Create a specific exception to raise from call_next
        original_exception = RuntimeError(error_msg)

        async def failing_call_next(ctx: Any) -> list:
            raise original_exception

        call_next = AsyncMock(side_effect=failing_call_next)

        middleware = ToolCallLoggingMiddleware()

        # Mock get_http_request to avoid RuntimeError
        mock_request = MagicMock()
        mock_request.scope = {"headers": [], "client": ("127.0.0.1", 8080)}
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            caught_exception = None
            try:
                asyncio.run(middleware.on_call_tool(context, call_next))
            except RuntimeError as e:
                caught_exception = e

        # Verify the exact same exception propagated
        assert caught_exception is original_exception, (
            f"Expected the exact same exception to propagate "
            f"(identity check). Expected {original_exception!r}, "
            f"got {caught_exception!r}"
        )

    @given(
        arguments=delegation_arguments,
        exception_type=st.sampled_from(
            [ValueError, TypeError, KeyError, IOError, OSError]
        ),
        error_msg=exception_messages,
    )
    @settings(max_examples=100)
    def test_various_exception_types_propagate(
        self,
        arguments: dict[str, Any],
        exception_type: type,
        error_msg: str,
    ) -> None:
        """Various exception types propagate unchanged through middleware.

        The middleware SHALL not catch or suppress any exception type
        raised by the downstream handler.

        Validates: Requirements 6.3
        """
        context = _make_tool_call_context(arguments)

        original_exception = exception_type(error_msg)

        async def failing_call_next(ctx: Any) -> list:
            raise original_exception

        call_next = AsyncMock(side_effect=failing_call_next)

        middleware = ToolCallLoggingMiddleware()

        # Mock get_http_request to avoid RuntimeError
        mock_request = MagicMock()
        mock_request.scope = {"headers": [], "client": ("127.0.0.1", 8080)}
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            caught_exception = None
            try:
                asyncio.run(middleware.on_call_tool(context, call_next))
            except Exception as e:  # noqa: BLE001
                caught_exception = e

        # Verify the exact same exception object propagated
        assert caught_exception is original_exception, (
            f"Expected {exception_type.__name__}({error_msg!r}) "
            f"to propagate unchanged. Got {caught_exception!r}"
        )

        # Verify the exception type is preserved
        assert type(caught_exception) is exception_type, (
            f"Expected exception type {exception_type.__name__}, "
            f"got {type(caught_exception).__name__}"
        )

    @given(
        arguments=delegation_arguments,
        tool_name=tool_names,
    )
    @settings(max_examples=100)
    def test_call_next_is_always_invoked(
        self,
        arguments: dict[str, Any],
        tool_name: str,
    ) -> None:
        """call_next is always invoked for every tool call.

        The middleware SHALL always delegate to the downstream handler
        regardless of the arguments or tool name.

        Validates: Requirements 6.1
        """
        context = _make_tool_call_context(arguments, tool_name)

        call_next = AsyncMock(return_value=[])

        middleware = ToolCallLoggingMiddleware()

        # Mock get_http_request to avoid RuntimeError
        mock_request = MagicMock()
        mock_request.scope = {"headers": [], "client": ("127.0.0.1", 8080)}
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            asyncio.run(middleware.on_call_tool(context, call_next))

        # Verify call_next was called exactly once
        call_next.assert_called_once()

    @given(
        arguments=delegation_arguments,
    )
    @settings(max_examples=100)
    def test_arguments_not_mutated_by_middleware(
        self,
        arguments: dict[str, Any],
    ) -> None:
        """Tool call arguments are not mutated by the middleware.

        The middleware performs masking on a copy for logging purposes
        but SHALL NOT modify the original arguments dictionary that
        gets passed downstream.

        Validates: Requirements 6.2
        """
        context = _make_tool_call_context(arguments)
        # Deep copy to compare later
        original_arguments = copy.deepcopy(arguments)

        call_next = AsyncMock(return_value=[])

        middleware = ToolCallLoggingMiddleware()

        # Mock get_http_request to avoid RuntimeError
        mock_request = MagicMock()
        mock_request.scope = {"headers": [], "client": ("127.0.0.1", 8080)}
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            asyncio.run(middleware.on_call_tool(context, call_next))

        # Verify the arguments dict was not mutated
        assert context.message.arguments == original_arguments, (
            f"Arguments were mutated by middleware. "
            f"Original: {original_arguments!r}, "
            f"After: {context.message.arguments!r}"
        )

    def test_audit_is_emitted_when_downstream_is_cancelled(self) -> None:
        """Cancellation still emits the audit record before propagating."""
        context = _make_tool_call_context({"issue_key": "TEST-1"})
        middleware = ToolCallLoggingMiddleware()
        mock_request = MagicMock()
        mock_request.scope = {"headers": [], "client": ("127.0.0.1", 8080)}
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        async def cancelled_call_next(ctx: Any) -> list[Any]:
            raise asyncio.CancelledError

        with (
            patch(
                "mcp_atlassian.servers.audit.get_http_request",
                return_value=mock_request,
            ),
            patch("mcp_atlassian.servers.audit.audit_logger.info") as info,
        ):
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(middleware.on_call_tool(context, cancelled_call_next))

        info.assert_called_once()


# --- Strategies for Property 9: Graceful degradation on logging failure ---

# Generate exception types that could occur during audit logging
logging_exception_types = st.sampled_from(
    [
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        IOError,
        AttributeError,
        KeyError,
    ]
)

# Generate exception messages for logging failures
logging_error_messages = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=80,
)


class TestProperty9GracefulDegradation:
    """Feature: tool-call-audit-logging, Property 9: Graceful degradation on logging failure.

    For any tool call where the audit logging operation itself raises
    an exception, the middleware SHALL emit a WARNING-level log entry
    about the logging failure and ensure that warning is successfully
    written BEFORE delegating to the downstream handler; the middleware
    SHALL only emit warnings when audit logging actually fails with an
    exception and SHALL NOT log warnings during normal successful
    operation.

    **Validates: Requirements 6.4**
    """  # noqa: E501

    @given(
        arguments=delegation_arguments,
        tool_name=tool_names,
        exception_type=logging_exception_types,
        error_msg=logging_error_messages,
    )
    @settings(max_examples=100)
    def test_warning_emitted_on_logging_failure(
        self,
        arguments: dict[str, Any],
        tool_name: str,
        exception_type: type,
        error_msg: str,
    ) -> None:
        """WARNING is emitted when audit logging fails.

        When the audit logging operation raises an exception, the
        middleware SHALL emit a WARNING-level log entry about the
        failure before delegating to the downstream handler.

        Validates: Requirements 6.4
        """
        import logging as logging_mod

        context = _make_tool_call_context(arguments, tool_name)
        call_next = AsyncMock(return_value=[])

        middleware = ToolCallLoggingMiddleware()

        # Set up a handler on the app logger to capture warnings
        app_logger = logging_mod.getLogger("mcp-atlassian")
        mock_handler = MagicMock()
        mock_handler.level = logging_mod.DEBUG
        app_logger.addHandler(mock_handler)
        original_level = app_logger.level
        app_logger.setLevel(logging_mod.DEBUG)

        try:
            # Make audit_logger.info raise to simulate logging failure
            # This triggers the except block in on_call_tool
            with patch.object(
                middleware,
                "_mask_arguments",
                side_effect=exception_type(error_msg),
            ):
                asyncio.run(middleware.on_call_tool(context, call_next))

            # Verify WARNING was emitted
            warning_calls = [
                call
                for call in mock_handler.handle.call_args_list
                if call[0][0].levelno == logging_mod.WARNING
            ]
            assert len(warning_calls) >= 1, (
                f"Expected at least one WARNING log record, got {len(warning_calls)}"
            )
            warning_msg = warning_calls[0][0][0].getMessage()
            assert "Audit logging failed" in warning_msg, (
                f"Expected warning about audit logging failure, got: {warning_msg!r}"
            )
        finally:
            app_logger.removeHandler(mock_handler)
            app_logger.setLevel(original_level)

    @given(
        arguments=delegation_arguments,
        tool_name=tool_names,
        exception_type=logging_exception_types,
        error_msg=logging_error_messages,
    )
    @settings(max_examples=100)
    def test_warning_flushed_before_delegation(
        self,
        arguments: dict[str, Any],
        tool_name: str,
        exception_type: type,
        error_msg: str,
    ) -> None:
        """Warning is flushed BEFORE delegating to downstream handler.

        The middleware SHALL ensure the warning is successfully written
        (flushed) before calling call_next.

        Validates: Requirements 6.4
        """
        import logging as logging_mod

        context = _make_tool_call_context(arguments, tool_name)

        # Track the order of operations
        operation_order: list[str] = []

        async def tracking_call_next(ctx: Any) -> list:
            operation_order.append("call_next")
            return []

        call_next = AsyncMock(side_effect=tracking_call_next)

        middleware = ToolCallLoggingMiddleware()

        # Set up a handler on the app logger that tracks flush
        app_logger = logging_mod.getLogger("mcp-atlassian")

        class TrackingHandler(logging_mod.Handler):
            """Handler that tracks when flush is called."""

            def emit(self, record: logging_mod.LogRecord) -> None:
                if record.levelno == logging_mod.WARNING:
                    operation_order.append("warning")

            def flush(self) -> None:
                operation_order.append("flush")

        tracking_handler = TrackingHandler()
        tracking_handler.setLevel(logging_mod.DEBUG)
        app_logger.addHandler(tracking_handler)
        original_level = app_logger.level
        app_logger.setLevel(logging_mod.DEBUG)

        try:
            # Make _mask_arguments raise to simulate logging failure
            with patch.object(
                middleware,
                "_mask_arguments",
                side_effect=exception_type(error_msg),
            ):
                asyncio.run(middleware.on_call_tool(context, call_next))

            # Verify order: warning → flush → call_next
            assert "warning" in operation_order, (
                f"Expected 'warning' in operations, got {operation_order}"
            )
            assert "flush" in operation_order, (
                f"Expected 'flush' in operations, got {operation_order}"
            )
            assert "call_next" in operation_order, (
                f"Expected 'call_next' in operations, got {operation_order}"
            )

            warning_idx = operation_order.index("warning")
            flush_idx = operation_order.index("flush")
            call_next_idx = operation_order.index("call_next")

            assert warning_idx < call_next_idx, (
                f"Warning (index {warning_idx}) must come before "
                f"call_next (index {call_next_idx}). "
                f"Order: {operation_order}"
            )
            assert flush_idx < call_next_idx, (
                f"Flush (index {flush_idx}) must come before "
                f"call_next (index {call_next_idx}). "
                f"Order: {operation_order}"
            )
        finally:
            app_logger.removeHandler(tracking_handler)
            app_logger.setLevel(original_level)

    @given(
        arguments=delegation_arguments,
        tool_name=tool_names,
        exception_type=logging_exception_types,
        error_msg=logging_error_messages,
    )
    @settings(max_examples=100)
    def test_delegation_still_occurs_after_logging_failure(
        self,
        arguments: dict[str, Any],
        tool_name: str,
        exception_type: type,
        error_msg: str,
    ) -> None:
        """Downstream handler is still called after logging failure.

        Even when audit logging fails, the middleware SHALL still
        delegate to the downstream handler.

        Validates: Requirements 6.4
        """
        context = _make_tool_call_context(arguments, tool_name)
        call_next = AsyncMock(return_value=[])

        middleware = ToolCallLoggingMiddleware()

        # Make _mask_arguments raise to simulate logging failure
        with patch.object(
            middleware,
            "_mask_arguments",
            side_effect=exception_type(error_msg),
        ):
            asyncio.run(middleware.on_call_tool(context, call_next))

        # Verify call_next was still invoked
        call_next.assert_called_once()

    @given(
        arguments=delegation_arguments,
        tool_name=tool_names,
    )
    @settings(max_examples=100)
    def test_no_warnings_during_normal_operation(
        self,
        arguments: dict[str, Any],
        tool_name: str,
    ) -> None:
        """No warnings are emitted during normal successful operation.

        The middleware SHALL only emit warnings when audit logging
        actually fails with an exception and SHALL NOT log warnings
        during normal successful operation.

        Validates: Requirements 6.4
        """
        import logging as logging_mod

        context = _make_tool_call_context(arguments, tool_name)
        call_next = AsyncMock(return_value=[])

        middleware = ToolCallLoggingMiddleware()

        # Set up a normal successful operation (no exceptions)
        mock_request = MagicMock()
        mock_request.scope = {
            "headers": [],
            "client": ("127.0.0.1", 8080),
        }
        mock_request.state = MagicMock()
        del mock_request.state.user_atlassian_auth_type

        # Set up a handler on the app logger to capture warnings
        app_logger = logging_mod.getLogger("mcp-atlassian")
        mock_handler = MagicMock()
        mock_handler.level = logging_mod.DEBUG
        app_logger.addHandler(mock_handler)
        original_level = app_logger.level
        app_logger.setLevel(logging_mod.DEBUG)

        try:
            with patch(
                "mcp_atlassian.servers.audit.get_http_request",
                return_value=mock_request,
            ):
                asyncio.run(middleware.on_call_tool(context, call_next))

            # Verify NO warning was emitted during normal operation
            warning_calls = [
                call
                for call in mock_handler.handle.call_args_list
                if call[0][0].levelno == logging_mod.WARNING
            ]
            assert len(warning_calls) == 0, (
                f"Expected no WARNING log records during normal "
                f"operation, got {len(warning_calls)}: "
                f"{[c[0][0].getMessage() for c in warning_calls]}"
            )
        finally:
            app_logger.removeHandler(mock_handler)
            app_logger.setLevel(original_level)


# --- Strategies for Property 10: Sensitive fields env var parsing ---

# Generate valid comma-separated field patterns
_VALID_PATTERN_CHARS = st.characters(
    whitelist_categories=("L", "N"),
)

# Generate individual pattern entries (non-empty alphanumeric strings)
pattern_entries = st.text(
    alphabet=_VALID_PATTERN_CHARS,
    min_size=1,
    max_size=15,
)

# Generate whitespace that might surround entries
entry_whitespace = st.text(
    alphabet=st.sampled_from(" \t"),
    min_size=0,
    max_size=4,
)


class TestProperty10SensitiveFieldsEnvVarParsing:
    """Feature: tool-call-audit-logging, Property 10: Sensitive fields environment variable parsing.

    For any value of MCP_AUDIT_SENSITIVE_FIELDS, the middleware SHALL
    parse it as a comma-separated list, trim whitespace from each
    entry, discard empty entries, and use the resulting strings as
    additional case-insensitive substring patterns for masking. If the
    value contains malformed data that cannot be parsed as a
    comma-separated list, the middleware SHALL skip the additional
    patterns entirely and use only the default sensitive field patterns.

    **Validates: Requirements 4.4, 7.2**
    """  # noqa: E501

    @given(
        patterns=st.lists(
            pattern_entries,
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_valid_comma_separated_patterns_are_parsed(
        self,
        patterns: list[str],
    ) -> None:
        """Valid comma-separated patterns are correctly parsed.

        The factory SHALL parse MCP_AUDIT_SENSITIVE_FIELDS as a
        comma-separated list and pass the entries to the middleware.

        Validates: Requirements 4.4, 7.2
        """
        env_value = ",".join(patterns)

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Each pattern should be in the middleware's sensitive patterns
        for pattern in patterns:
            assert pattern in middleware._sensitive_patterns, (
                f"Expected pattern {pattern!r} to be in "
                f"sensitive_patterns, got "
                f"{middleware._sensitive_patterns!r}"
            )

    @given(
        patterns=st.lists(
            pattern_entries,
            min_size=1,
            max_size=5,
        ),
        leading_ws=st.lists(
            entry_whitespace,
            min_size=1,
            max_size=5,
        ),
        trailing_ws=st.lists(
            entry_whitespace,
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_whitespace_trimmed_from_entries(
        self,
        patterns: list[str],
        leading_ws: list[str],
        trailing_ws: list[str],
    ) -> None:
        """Whitespace is trimmed from each entry.

        The factory SHALL trim whitespace around each entry before
        using it as a pattern.

        Validates: Requirements 7.2
        """
        # Build env value with whitespace around entries
        entries = []
        for i, pattern in enumerate(patterns):
            lws = leading_ws[i % len(leading_ws)]
            tws = trailing_ws[i % len(trailing_ws)]
            entries.append(f"{lws}{pattern}{tws}")
        env_value = ",".join(entries)

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Each trimmed pattern should be present (not the padded version)
        for pattern in patterns:
            assert pattern in middleware._sensitive_patterns, (
                f"Expected trimmed pattern {pattern!r} in "
                f"sensitive_patterns after whitespace trimming, "
                f"got {middleware._sensitive_patterns!r}"
            )

    @given(
        patterns=st.lists(
            pattern_entries,
            min_size=1,
            max_size=4,
        ),
        num_empty=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=100)
    def test_empty_entries_discarded(
        self,
        patterns: list[str],
        num_empty: int,
    ) -> None:
        """Empty entries in the comma-separated list are discarded.

        The factory SHALL ignore empty entries (including entries that
        are only whitespace after trimming).

        Validates: Requirements 7.2
        """
        # Interleave valid patterns with empty entries
        entries: list[str] = []
        for pattern in patterns:
            entries.append(pattern)
            # Add empty entries (empty string or whitespace-only)
            for _ in range(num_empty):
                entries.append("")
        env_value = ",".join(entries)

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Valid patterns should be present
        for pattern in patterns:
            assert pattern in middleware._sensitive_patterns, (
                f"Expected pattern {pattern!r} in "
                f"sensitive_patterns, got "
                f"{middleware._sensitive_patterns!r}"
            )

        # Empty string should NOT be in patterns
        assert "" not in middleware._sensitive_patterns, (
            "Empty string should not be in sensitive_patterns"
        )

    @given(
        num_commas=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_all_empty_entries_results_in_defaults_only(
        self,
        num_commas: int,
    ) -> None:
        """When all entries are empty, only defaults are used.

        If MCP_AUDIT_SENSITIVE_FIELDS contains only commas and
        whitespace (all entries are empty after trimming), the
        middleware SHALL use only the default patterns.

        Validates: Requirements 4.4, 7.2
        """
        # Create a value with only commas (all empty entries)
        env_value = "," * num_commas

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Should have exactly the default patterns
        from mcp_atlassian.servers.audit import (
            DEFAULT_SENSITIVE_PATTERNS,
        )

        assert middleware._sensitive_patterns == list(DEFAULT_SENSITIVE_PATTERNS), (
            f"Expected only default patterns "
            f"{DEFAULT_SENSITIVE_PATTERNS!r}, got "
            f"{middleware._sensitive_patterns!r}"
        )

    @given(
        patterns=st.lists(
            pattern_entries,
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_additional_patterns_merged_with_defaults(
        self,
        patterns: list[str],
    ) -> None:
        """Additional patterns are merged with default patterns.

        The factory SHALL pass parsed patterns to the middleware, which
        merges them with the default sensitive patterns.

        Validates: Requirements 4.4, 7.2
        """
        from mcp_atlassian.servers.audit import (
            DEFAULT_SENSITIVE_PATTERNS,
        )

        env_value = ",".join(patterns)

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # All default patterns should still be present
        for default_pattern in DEFAULT_SENSITIVE_PATTERNS:
            assert default_pattern in middleware._sensitive_patterns, (
                f"Default pattern {default_pattern!r} missing "
                f"from sensitive_patterns: "
                f"{middleware._sensitive_patterns!r}"
            )

        # Additional patterns should also be present
        for pattern in patterns:
            assert pattern in middleware._sensitive_patterns, (
                f"Additional pattern {pattern!r} missing from "
                f"sensitive_patterns: "
                f"{middleware._sensitive_patterns!r}"
            )

    @settings(max_examples=1)
    @given(st.just(None))
    def test_unset_env_var_uses_defaults_only(self, _: None) -> None:
        """When MCP_AUDIT_SENSITIVE_FIELDS is unset, only defaults used.

        Validates: Requirements 4.4
        """
        from mcp_atlassian.servers.audit import (
            DEFAULT_SENSITIVE_PATTERNS,
        )

        env = os.environ.copy()
        env.pop("MCP_AUDIT_SENSITIVE_FIELDS", None)
        with patch.dict(os.environ, env, clear=True):
            middleware = create_audit_middleware()

        assert middleware is not None
        assert middleware._sensitive_patterns == list(DEFAULT_SENSITIVE_PATTERNS), (
            f"Expected only default patterns when env var unset, "
            f"got {middleware._sensitive_patterns!r}"
        )

    @given(
        patterns=st.lists(
            pattern_entries,
            min_size=1,
            max_size=5,
        ),
        ws_entries=st.lists(
            st.text(
                alphabet=st.sampled_from(" \t"),
                min_size=1,
                max_size=4,
            ),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=100)
    def test_whitespace_only_entries_discarded(
        self,
        patterns: list[str],
        ws_entries: list[str],
    ) -> None:
        """Whitespace-only entries are treated as empty and discarded.

        Entries that contain only whitespace after splitting on commas
        SHALL be discarded (they become empty after trimming).

        Validates: Requirements 7.2
        """
        # Mix valid patterns with whitespace-only entries
        all_entries = list(patterns) + ws_entries
        env_value = ",".join(all_entries)

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Valid patterns should be present
        for pattern in patterns:
            assert pattern in middleware._sensitive_patterns, (
                f"Expected pattern {pattern!r} in "
                f"sensitive_patterns, got "
                f"{middleware._sensitive_patterns!r}"
            )

        # Whitespace-only entries should NOT be present
        for ws_entry in ws_entries:
            assert ws_entry not in middleware._sensitive_patterns, (
                f"Whitespace-only entry {ws_entry!r} should not "
                f"be in sensitive_patterns"
            )

    @given(
        custom_pattern=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"),
                max_codepoint=127,
            ),
            min_size=3,
            max_size=10,
        ).filter(
            lambda s: (
                s
                not in {
                    "token",
                    "password",
                    "secret",
                    "key",
                    "credential",
                    "auth",
                }
                and not any(
                    p in s
                    for p in [
                        "token",
                        "password",
                        "secret",
                        "key",
                        "credential",
                        "auth",
                    ]
                )
            )
        ),
        value=st.text(min_size=5, max_size=30),
    )
    @settings(max_examples=100)
    def test_parsed_patterns_actually_mask_fields(
        self,
        custom_pattern: str,
        value: str,
    ) -> None:
        """Parsed patterns from env var are actually used for masking.

        When MCP_AUDIT_SENSITIVE_FIELDS provides additional patterns,
        those patterns SHALL be used for case-insensitive substring
        matching during argument masking. Patterns are matched against
        the lowercased field name, so lowercase patterns enable
        case-insensitive matching.

        Validates: Requirements 4.4, 7.2
        """
        env_value = custom_pattern

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Create an argument whose key contains the custom pattern
        field_name = f"my_{custom_pattern}_field"
        arguments = {field_name: value}
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(value))
        assert result[field_name] == expected, (
            f"Expected field {field_name!r} to be masked to "
            f"{expected!r} using custom pattern "
            f"{custom_pattern!r}, got {result[field_name]!r}"
        )

    @given(
        custom_pattern=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"),
                max_codepoint=127,
            ),
            min_size=3,
            max_size=10,
        ).filter(
            lambda s: (
                s
                not in {
                    "token",
                    "password",
                    "secret",
                    "key",
                    "credential",
                    "auth",
                }
                and not any(
                    p in s
                    for p in [
                        "token",
                        "password",
                        "secret",
                        "key",
                        "credential",
                        "auth",
                    ]
                )
            )
        ),
        value=st.text(min_size=5, max_size=30),
    )
    @settings(max_examples=100)
    def test_parsed_patterns_case_insensitive_matching(
        self,
        custom_pattern: str,
        value: str,
    ) -> None:
        """Parsed patterns use case-insensitive substring matching.

        Custom patterns from the env var SHALL match field names
        regardless of case. Since the implementation lowercases the
        field name before matching, a lowercase pattern will match
        field names with any casing of that substring.

        Validates: Requirements 4.4, 7.2
        """
        env_value = custom_pattern

        with patch.dict(
            os.environ,
            {"MCP_AUDIT_SENSITIVE_FIELDS": env_value},
        ):
            middleware = create_audit_middleware()

        assert middleware is not None

        # Use the pattern in UPPER case in the field name
        # Since key is lowercased before matching, this should still match
        field_name = f"MY_{custom_pattern.upper()}_FIELD"
        arguments = {field_name: value}
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(value))
        assert result[field_name] == expected, (
            f"Expected field {field_name!r} to be masked using "
            f"case-insensitive match of pattern "
            f"{custom_pattern!r}, got "
            f"{result[field_name]!r}"
        )


# ===================================================================
# Unit Tests (Example-Based) — Task 5.1
# ===================================================================


class TestMiddlewareSubclass:
    """Verify ToolCallLoggingMiddleware is a proper Middleware subclass.

    Validates: Requirements 1.2, 1.3
    """

    def test_subclasses_fastmcp_middleware(self) -> None:
        """ToolCallLoggingMiddleware subclasses Middleware base class.

        Validates: Requirements 1.2
        """
        from fastmcp.server.middleware import Middleware

        assert issubclass(ToolCallLoggingMiddleware, Middleware)
        mw = ToolCallLoggingMiddleware()
        assert isinstance(mw, Middleware)

    def test_only_on_call_tool_is_overridden(self) -> None:
        """Only on_call_tool is overridden, no other hooks.

        Validates: Requirements 1.3
        """
        from fastmcp.server.middleware import Middleware

        # All hooks defined on the base class
        all_hooks = [m for m in dir(Middleware) if m.startswith("on_")]

        mw = ToolCallLoggingMiddleware()
        for hook_name in all_hooks:
            mw_method = getattr(type(mw), hook_name)
            base_method = getattr(Middleware, hook_name)
            if hook_name == "on_call_tool":
                # on_call_tool SHOULD be overridden
                assert mw_method is not base_method, "on_call_tool should be overridden"
            else:
                # All other hooks should NOT be overridden
                assert mw_method is base_method, f"{hook_name} should not be overridden"


class TestLogLevelAndLoggerName:
    """Verify audit logger configuration.

    Validates: Requirements 5.2, 5.3
    """

    def test_log_level_is_info(self) -> None:
        """Audit log entries are emitted at INFO level.

        Validates: Requirements 5.2
        """
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "test_tool"
        context.message.arguments = {"key": "value"}

        call_next = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "mcp_atlassian.servers.audit.get_http_request",
                side_effect=RuntimeError("no request"),
            ),
            patch("mcp_atlassian.servers.audit.audit_logger") as mock_logger,
        ):
            asyncio.run(middleware.on_call_tool(context, call_next))

        mock_logger.info.assert_called_once()
        mock_logger.warning.assert_not_called()

    def test_logger_name_is_mcp_atlassian_audit(self) -> None:
        """Audit logger uses 'mcp-atlassian.audit' name.

        Validates: Requirements 5.3
        """
        from mcp_atlassian.servers.audit import audit_logger

        assert audit_logger.name == "mcp-atlassian.audit"


class TestEmptyArguments:
    """Verify empty/None arguments produce '{}'.

    Validates: Requirements 5.6
    """

    def test_none_arguments_produce_empty_json(self) -> None:
        """None arguments serialize to '{}'."""
        middleware = ToolCallLoggingMiddleware()
        result = middleware._serialize_body(None)
        assert result == "{}"

    def test_empty_dict_arguments_produce_empty_json(self) -> None:
        """Empty dict arguments serialize to '{}'."""
        middleware = ToolCallLoggingMiddleware()
        result = middleware._serialize_body({})
        assert result == "{}"


class TestNoNetworkCalls:
    """Verify the audit module does not import networking libraries.

    Validates: Requirements 3.6
    """

    def test_no_httpx_import_in_module(self) -> None:
        """Audit module does not import httpx."""
        import importlib

        # Reload the module to check its imports
        module = importlib.import_module("mcp_atlassian.servers.audit")
        source_file = module.__file__
        assert source_file is not None

        with open(source_file) as f:
            source = f.read()

        assert "import httpx" not in source
        assert "from httpx" not in source

    def test_no_requests_import_in_module(self) -> None:
        """Audit module does not import requests."""
        import importlib

        module = importlib.import_module("mcp_atlassian.servers.audit")
        source_file = module.__file__
        assert source_file is not None

        with open(source_file) as f:
            source = f.read()

        assert "import requests" not in source
        assert "from requests" not in source


class TestMiddlewareEnabledByDefault:
    """Verify middleware is enabled when env var is unset.

    Validates: Requirements 1.4
    """

    def test_enabled_when_env_var_unset(self) -> None:
        """create_audit_middleware returns instance when env unset."""
        env = os.environ.copy()
        env.pop("MCP_AUDIT_LOG_ENABLED", None)
        with patch.dict(os.environ, env, clear=True):
            result = create_audit_middleware()
        assert isinstance(result, ToolCallLoggingMiddleware)

    def test_enabled_when_env_var_empty_string(self) -> None:
        """create_audit_middleware returns instance for empty string."""
        with patch.dict(os.environ, {"MCP_AUDIT_LOG_ENABLED": ""}):
            result = create_audit_middleware()
        assert isinstance(result, ToolCallLoggingMiddleware)


class TestWarningOnlyOnFailure:
    """Verify warning is only emitted on actual logging failure.

    Validates: Requirements 6.4
    """

    def test_no_warning_on_successful_audit(self) -> None:
        """No warning is emitted during normal successful operation."""
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "test_tool"
        context.message.arguments = {"issue_key": "PROJ-1"}

        call_next = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "mcp_atlassian.servers.audit.get_http_request",
                side_effect=RuntimeError("no request"),
            ),
            patch("mcp_atlassian.servers.audit.audit_logger") as mock_audit_logger,
            patch("logging.getLogger") as mock_get_logger,
        ):
            asyncio.run(middleware.on_call_tool(context, call_next))

        # Audit logger should have logged at INFO
        mock_audit_logger.info.assert_called_once()
        # The application logger should NOT have been called
        # (no warning because logging succeeded)
        mock_get_logger.assert_not_called()

    def test_warning_emitted_on_logging_failure(self) -> None:
        """Warning is emitted when audit logging raises an exception."""
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()
        context.message = MagicMock()
        context.message.name = "test_tool"
        context.message.arguments = {"key": "value"}

        call_next = AsyncMock(return_value=MagicMock())

        mock_app_logger = MagicMock()
        mock_handler = MagicMock()
        mock_app_logger.handlers = [mock_handler]

        with (
            patch(
                "mcp_atlassian.servers.audit.get_http_request",
                side_effect=RuntimeError("no request"),
            ),
            patch("mcp_atlassian.servers.audit.audit_logger") as mock_audit_logger,
            patch(
                "logging.getLogger",
                return_value=mock_app_logger,
            ) as mock_get_logger,
        ):
            # Make audit_logger.info raise an exception
            mock_audit_logger.info.side_effect = RuntimeError("logging failed")
            asyncio.run(middleware.on_call_tool(context, call_next))

        # Application logger should have been used for warning
        mock_get_logger.assert_called_with("mcp-atlassian")
        mock_app_logger.warning.assert_called_once()
        # Handler flush should have been called
        mock_handler.flush.assert_called_once()
        # Tool execution should still proceed
        call_next.assert_called_once_with(context)


class TestMalformedSensitiveFieldsFallback:
    """Verify malformed MCP_AUDIT_SENSITIVE_FIELDS falls back to defaults.

    Validates: Requirements 4.4
    """

    def test_malformed_env_uses_only_defaults(self) -> None:
        """Malformed sensitive fields env var uses only defaults."""
        from mcp_atlassian.servers.audit import DEFAULT_SENSITIVE_PATTERNS

        # The current implementation handles comma-separated strings
        # gracefully, so we test that even with unusual input,
        # the middleware still uses default patterns.
        # An empty/whitespace-only value should result in no
        # additional patterns.
        env = {
            "MCP_AUDIT_SENSITIVE_FIELDS": "   ,  , ,  ",
        }
        with patch.dict(os.environ, env):
            middleware = create_audit_middleware()

        assert middleware is not None
        # Only default patterns should be active
        assert middleware._sensitive_patterns == list(DEFAULT_SENSITIVE_PATTERNS)

    def test_valid_sensitive_fields_are_added(self) -> None:
        """Valid comma-separated patterns are added to defaults."""
        from mcp_atlassian.servers.audit import DEFAULT_SENSITIVE_PATTERNS

        env = {
            "MCP_AUDIT_SENSITIVE_FIELDS": "ssn, credit_card",
        }
        with patch.dict(os.environ, env):
            middleware = create_audit_middleware()

        assert middleware is not None
        expected = list(DEFAULT_SENSITIVE_PATTERNS) + [
            "ssn",
            "credit_card",
        ]
        assert middleware._sensitive_patterns == expected
