import logging
from uuid import UUID

from anyio.streams.memory import MemoryObjectSendStream
from mcp.server.sse import SseServerTransport
from mcp.types import JSONRPCMessage

from ..server import AppContext

logger = logging.getLogger("mcp-atlassian")


class AtlassianSseServerTransport(SseServerTransport):
    """Custom SSE transport that handles session-specific Atlassian services."""

    def __init__(self, path: str = "/messages/") -> None:
        """Initialize the SSE transport.

        Args:
            path: The path for the SSE endpoint
        """
        super().__init__(path)
        self._sessions: dict[UUID, AppContext] = {}  # Store session-specific services
        self._current_session_id: UUID | None = None  # Store current session ID
        self._session_ids: set[UUID] = set()  # Track all active session IDs
        self._read_stream_writers: dict[
            UUID, MemoryObjectSendStream[JSONRPCMessage | Exception]
        ] = {}

    def get_session_id(self) -> UUID | None:
        """Get the current session ID.

        Returns:
            The current session ID or None if no session is active
        """
        logger.debug(f"Getting session ID: {self._current_session_id}")
        return self._current_session_id

    def get_session_context(self, session_id: UUID | None = None) -> AppContext | None:
        """Get the session context for a specific session ID or the current session.

        Args:
            session_id: Optional specific session ID to get context for

        Returns:
            The session context or None if not found
        """
        if session_id is None:
            session_id = self._current_session_id
        logger.debug(f"Getting session context for ID: {session_id}")
        return self._sessions.get(session_id) if session_id else None

    def get_transport(self) -> "AtlassianSseServerTransport":
        """Get the transport instance.

        Returns:
            The transport instance
        """
        return self

    def set_current_session_id(self, session_id: UUID) -> None:
        """Set the current session ID.

        Args:
            session_id: The session ID to set as current
        """
        self._current_session_id = session_id
        if session_id not in self._session_ids:
            self._session_ids.add(session_id)
            self._sessions[session_id] = AppContext(confluence=None, jira=None)
