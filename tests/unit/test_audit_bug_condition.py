"""Bug condition exploration test for audit log username timing bug.

This test encodes the EXPECTED behavior: after call_next completes and
dependency injection has backfilled the real email, the audit log entry
should contain the resolved email — NOT the generic fallback.

On UNFIXED code, this test is EXPECTED TO FAIL because the middleware
extracts the username BEFORE call_next, when email is still None.

Feature: audit-log-real-username
**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_atlassian.servers.audit import ToolCallLoggingMiddleware

# --- Strategies ---

# Generate valid email addresses for PAT/OAuth users
emails = st.from_regex(
    r"[a-z][a-z0-9._%+-]{0,15}@[a-z][a-z0-9.-]{0,10}\.[a-z]{2,4}",
    fullmatch=True,
)

# Auth types affected by the bug (PAT and OAuth)
bug_auth_types = st.sampled_from(["pat", "oauth"])


def _make_mock_request_with_state(
    auth_type: str,
    email: Any = None,
) -> MagicMock:
    """Create a mock request simulating pre-DI state.

    Before call_next runs, PAT/OAuth requests have auth_type set
    but email is None (not yet backfilled by DI).

    Args:
        auth_type: The user_atlassian_auth_type value.
        email: The initial user_atlassian_email value (None pre-DI).

    Returns:
        A MagicMock configured as a Starlette request with mutable
        state attributes.
    """
    mock_request = MagicMock()

    # Use a simple namespace for mutable state
    class State:
        user_atlassian_auth_type: str | None = None
        user_atlassian_email: str | None = None

    state = State()
    state.user_atlassian_auth_type = auth_type
    state.user_atlassian_email = email
    mock_request.state = state

    # Minimal scope for source IP extraction
    mock_request.scope = {
        "headers": [],
        "client": ("127.0.0.1", 8000),
    }
    mock_request.headers = {}

    return mock_request


class TestBugConditionExploration:
    """Bug Condition: PAT/OAuth Username Resolution Timing Bug.

    Property 1: For any tool call where auth type is 'pat' or 'oauth'
    and dependency injection successfully resolves the user email
    during call_next, the audit log entry SHALL contain the resolved
    real email address as the username.

    On UNFIXED code, this property FAILS because _extract_username is
    called BEFORE call_next, when user_atlassian_email is still None.

    **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**
    """

    @given(auth_type=bug_auth_types, resolved_email=emails)
    @settings(max_examples=50)
    def test_audit_log_contains_resolved_email_after_di(
        self,
        auth_type: str,
        resolved_email: str,
    ) -> None:
        """Audit log should contain the real email resolved by DI.

        Simulates the PAT/OAuth flow:
        1. Request arrives with auth_type set, email = None
        2. call_next triggers DI which backfills the real email
        3. Audit log entry should contain the resolved email

        On unfixed code, the audit log will contain 'pat-user' or
        'oauth-user' because username is extracted before call_next.
        """
        # Create request in pre-DI state (email is None)
        mock_request = _make_mock_request_with_state(
            auth_type=auth_type,
            email=None,
        )

        # Simulate call_next that triggers DI backfill
        async def mock_call_next(context: Any) -> MagicMock:
            """Simulate DI backfilling email during tool execution."""
            mock_request.state.user_atlassian_email = resolved_email
            # Return a mock ToolResult
            result = MagicMock()
            result.content = [MagicMock(type="text", text="ok")]
            return result

        middleware = ToolCallLoggingMiddleware()

        # Create mock context with tool call params
        context = MagicMock()
        context.message.name = "jira_get_issue"
        context.message.arguments = {"issue_key": "TEST-123"}

        # Capture the audit log output
        logged_messages: list[str] = []

        def capture_log(msg: str, *args: Any, **kwargs: Any) -> None:
            logged_messages.append(msg)

        with (
            patch(
                "mcp_atlassian.servers.audit.get_http_request",
                return_value=mock_request,
            ),
            patch(
                "mcp_atlassian.servers.audit.audit_logger.info",
                side_effect=capture_log,
            ),
        ):
            asyncio.run(middleware.on_call_tool(context, mock_call_next))

        # The audit log should contain the resolved email
        assert len(logged_messages) == 1, (
            f"Expected exactly 1 audit log entry, got {len(logged_messages)}"
        )

        log_entry = logged_messages[0]
        fallback = f"{auth_type}-user"

        # The key assertion: log should contain the real email,
        # NOT the generic fallback
        assert resolved_email in log_entry, (
            f"Bug confirmed: audit log does not contain resolved "
            f"email {resolved_email!r}. "
            f"Log entry: {log_entry!r}. "
            f"Auth type: {auth_type}. "
            f"Expected the real email after DI backfill, but got "
            f"the fallback '{fallback}' instead."
        )
        assert fallback not in log_entry, (
            f"Bug confirmed: audit log contains fallback "
            f"'{fallback}' instead of resolved email "
            f"{resolved_email!r}. "
            f"Log entry: {log_entry!r}. "
            f"The username was extracted BEFORE call_next "
            f"(when email was still None)."
        )
