"""Property-based preservation tests for audit logging middleware.

These tests capture the EXISTING behavior of the unfixed code for
non-PAT/OAuth scenarios. They must PASS on unfixed code and continue
to pass after the fix is applied, ensuring no regressions.

Uses Hypothesis to verify that Basic auth, anonymous, sensitive field
masking, and body truncation behaviors are preserved across all inputs.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""

import base64
from typing import Any
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_atlassian.servers.audit import (
    DEFAULT_SENSITIVE_PATTERNS,
    ToolCallLoggingMiddleware,
)
from mcp_atlassian.utils.logging import mask_sensitive

# --- Strategies ---

# Generate valid email-like strings (local@domain.tld)
emails = st.from_regex(
    r"[a-z][a-z0-9._%+-]{0,20}@[a-z][a-z0-9.-]{0,10}\.[a-z]{2,4}",
    fullmatch=True,
)

# Generate non-empty passwords for Basic auth encoding
passwords = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P"),
        blacklist_characters=":",
    ),
    min_size=1,
    max_size=30,
)

# Generate tool names (snake_case identifiers)
tool_names = st.from_regex(
    r"[a-z][a-z0-9_]{2,30}",
    fullmatch=True,
)

# Safe field names that do NOT match any sensitive pattern
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
    "limit",
    "offset",
    "jql",
]

non_sensitive_field_names = st.sampled_from(_SAFE_NAMES)

# Generate field names that contain a sensitive pattern
sensitive_field_names = st.one_of(
    st.sampled_from(DEFAULT_SENSITIVE_PATTERNS),
    st.tuples(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=0,
            max_size=6,
        ),
        st.sampled_from(DEFAULT_SENSITIVE_PATTERNS),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=0,
            max_size=6,
        ),
    ).map(lambda t: f"{t[0]}{t[1]}{t[2]}"),
    st.sampled_from(DEFAULT_SENSITIVE_PATTERNS).map(str.upper),
    st.sampled_from(DEFAULT_SENSITIVE_PATTERNS).map(str.title),
)

# Generate arbitrary argument values
argument_values = st.one_of(
    st.text(min_size=1, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
)

# Generate argument dictionaries with only non-sensitive keys
safe_argument_dicts = st.dictionaries(
    keys=non_sensitive_field_names,
    values=argument_values,
    min_size=0,
    max_size=5,
)


def _make_mock_request_with_state(
    auth_type: str | None = None,
    email: str | None = None,
    authorization: str | None = None,
) -> MagicMock:
    """Create a mock request with auth state and optional headers."""
    mock_request = MagicMock()
    state = MagicMock()

    if auth_type is not None:
        state.user_atlassian_auth_type = auth_type
    else:
        del state.user_atlassian_auth_type

    if email is not None:
        state.user_atlassian_email = email
    else:
        del state.user_atlassian_email

    mock_request.state = state

    headers: dict[str, str] = {}
    if authorization is not None:
        headers["authorization"] = authorization
    mock_request.headers = headers

    return mock_request


class TestPreservationBasicAuth:
    """Preservation: Basic auth email extraction from Authorization header.

    For any valid email address encoded in a Basic Authorization header,
    the middleware SHALL extract and return that email as the username.
    This behavior must remain unchanged after the fix.

    **Validates: Requirements 3.1**
    """

    @given(email=emails, password=passwords)
    @settings(max_examples=200)
    def test_basic_auth_always_extracts_email(self, email: str, password: str) -> None:
        """Basic auth always extracts the email from the header."""
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
            f"Basic auth must extract email {email!r} from "
            f"Authorization header, got {result!r}"
        )


class TestPreservationAnonymous:
    """Preservation: Unauthenticated requests log 'anonymous'.

    For any tool call without authentication state, the middleware
    SHALL return 'anonymous' as the username. This behavior must
    remain unchanged after the fix.

    **Validates: Requirements 3.2**
    """

    @given(tool_name=tool_names, arguments=safe_argument_dicts)
    @settings(max_examples=200)
    def test_anonymous_always_returned_for_no_auth(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        """Unauthenticated requests always produce 'anonymous'."""
        mock_request = _make_mock_request_with_state(
            auth_type=None,
        )
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            return_value=mock_request,
        ):
            result = middleware._extract_username(context)

        assert result == "anonymous", (
            f"Unauthenticated request with tool={tool_name!r} "
            f"must log 'anonymous', got {result!r}"
        )

    @given(tool_name=tool_names, arguments=safe_argument_dicts)
    @settings(max_examples=100)
    def test_anonymous_when_get_http_request_fails(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        """Returns 'anonymous' when get_http_request raises."""
        middleware = ToolCallLoggingMiddleware()
        context = MagicMock()

        with patch(
            "mcp_atlassian.servers.audit.get_http_request",
            side_effect=RuntimeError("No request"),
        ):
            result = middleware._extract_username(context)

        assert result == "anonymous", (
            f"Must return 'anonymous' when request unavailable, got {result!r}"
        )


class TestPreservationSensitiveMasking:
    """Preservation: Sensitive fields are always masked.

    For any argument dictionary containing field names that match
    DEFAULT_SENSITIVE_PATTERNS (case-insensitive substring), the
    middleware SHALL mask those values using mask_sensitive(str(value)).
    This behavior must remain unchanged after the fix.

    **Validates: Requirements 3.4**
    """

    @given(
        sensitive_key=sensitive_field_names,
        sensitive_value=argument_values,
    )
    @settings(max_examples=200)
    def test_sensitive_values_always_masked(
        self, sensitive_key: str, sensitive_value: Any
    ) -> None:
        """Sensitive field values are always masked."""
        arguments = {sensitive_key: sensitive_value}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(sensitive_value))
        assert result[sensitive_key] == expected, (
            f"Sensitive key {sensitive_key!r} with value "
            f"{sensitive_value!r} must be masked to "
            f"{expected!r}, got {result[sensitive_key]!r}"
        )

    @given(
        sensitive_key=sensitive_field_names,
        sensitive_value=argument_values,
        safe_key=non_sensitive_field_names,
        safe_value=argument_values,
    )
    @settings(max_examples=200)
    def test_only_sensitive_fields_masked_in_mixed_dict(
        self,
        sensitive_key: str,
        sensitive_value: Any,
        safe_key: str,
        safe_value: Any,
    ) -> None:
        """In mixed dicts, only sensitive fields are masked."""
        arguments = {sensitive_key: sensitive_value, safe_key: safe_value}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        # Sensitive field must be masked
        expected_masked = mask_sensitive(str(sensitive_value))
        assert result[sensitive_key] == expected_masked, (
            f"Sensitive key {sensitive_key!r} must be masked"
        )

        # Non-sensitive field must be unchanged
        assert result[safe_key] == safe_value, (
            f"Non-sensitive key {safe_key!r} must remain "
            f"unchanged, got {result[safe_key]!r}"
        )

    @given(
        outer_key=non_sensitive_field_names,
        nested_sensitive_key=sensitive_field_names,
        nested_value=argument_values,
    )
    @settings(max_examples=200)
    def test_nested_sensitive_fields_masked(
        self,
        outer_key: str,
        nested_sensitive_key: str,
        nested_value: Any,
    ) -> None:
        """Sensitive keys in nested dicts (1 level) are masked."""
        arguments = {outer_key: {nested_sensitive_key: nested_value}}
        middleware = ToolCallLoggingMiddleware()
        result = middleware._mask_arguments(arguments)

        expected = mask_sensitive(str(nested_value))
        assert result[outer_key][nested_sensitive_key] == expected, (
            f"Nested sensitive key {nested_sensitive_key!r} "
            f"must be masked to {expected!r}, got "
            f"{result[outer_key][nested_sensitive_key]!r}"
        )


class TestPreservationBodyTruncation:
    """Preservation: Bodies exceeding max_body_length are truncated.

    For any argument dictionary whose str() representation exceeds
    max_body_length, the serialized body SHALL be truncated to
    max_body_length characters followed by '...truncated'. Bodies
    within the threshold SHALL NOT be truncated.
    This behavior must remain unchanged after the fix.

    **Validates: Requirements 3.5**
    """

    @given(
        # Generate values that will exceed a small threshold
        value_length=st.integers(min_value=80, max_value=300),
    )
    @settings(max_examples=200)
    def test_long_bodies_always_truncated(self, value_length: int) -> None:
        """Bodies exceeding max_body_length are always truncated."""
        # Use max_body_length=64 so we can easily exceed it
        middleware = ToolCallLoggingMiddleware(max_body_length=64)
        arguments = {"data": "x" * value_length}

        result = middleware._serialize_body(arguments)

        assert result.endswith("...truncated"), (
            f"Body with str(args) length > 64 must be truncated, got: {result[-30:]!r}"
        )

    @given(
        # Generate values that keep str(args) under the threshold
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
            ),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=200)
    def test_short_bodies_never_truncated(self, value: str) -> None:
        """Bodies within max_body_length are never truncated."""
        # Default max_body_length=2048, short values won't exceed it
        middleware = ToolCallLoggingMiddleware()
        arguments = {"key": value}

        result = middleware._serialize_body(arguments)

        assert "...truncated" not in result, (
            f"Short body must not be truncated, got: {result!r}"
        )

    @given(
        value_length=st.integers(min_value=80, max_value=300),
    )
    @settings(max_examples=200)
    def test_truncated_body_has_correct_prefix_length(self, value_length: int) -> None:
        """Truncated body prefix is exactly max_body_length chars."""
        max_len = 64
        middleware = ToolCallLoggingMiddleware(max_body_length=max_len)
        arguments = {"data": "x" * value_length}

        result = middleware._serialize_body(arguments)

        if result.endswith("...truncated"):
            prefix = result[: -len("...truncated")]
            assert len(prefix) == max_len, (
                f"Truncated prefix must be {max_len} chars, got {len(prefix)}"
            )

    @given(
        # Generate lengths right around the threshold boundary
        value_length=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=200)
    def test_truncation_threshold_is_str_representation(
        self, value_length: int
    ) -> None:
        """Truncation is based on str(arguments) length, not JSON."""
        max_len = 100
        middleware = ToolCallLoggingMiddleware(max_body_length=max_len)
        arguments = {"data": "a" * value_length}

        # The threshold is based on len(str(arguments))
        original_length = len(str(arguments))
        result = middleware._serialize_body(arguments)

        if original_length > max_len:
            assert result.endswith("...truncated"), (
                f"str(args) length {original_length} > {max_len} "
                f"must trigger truncation"
            )
        else:
            assert "...truncated" not in result, (
                f"str(args) length {original_length} <= {max_len} "
                f"must NOT trigger truncation"
            )
