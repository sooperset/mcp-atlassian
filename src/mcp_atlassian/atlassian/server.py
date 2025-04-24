from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import JSONRPCMessage

from mcp_atlassian.utils import logging

from .session import AtlassianSession
from .transport import AtlassianSseServerTransport

logger = logging.getLogger("mcp-atlassian")


class AtlassianServer(Server):
    """Custom server class that uses AtlassianSession."""

    def __init__(
        self,
        name: str,
        version: str | None = None,
        lifespan: Callable[["AtlassianServer"], AbstractAsyncContextManager[Any]]
        | None = None,
    ) -> None:
        """Initialize the Atlassian server.

        Args:
            name: The server name
            version: Optional server version
            lifespan: Optional lifespan function
        """
        super().__init__(name, version=version, lifespan=lifespan)
        self._transport: AtlassianSseServerTransport | None = None

    async def run(
        self,
        read_stream: MemoryObjectReceiveStream[JSONRPCMessage | Exception],
        write_stream: MemoryObjectSendStream[JSONRPCMessage],
        initialization_options: InitializationOptions,
        raise_exceptions: bool = False,
    ) -> None:
        """Run the server with the given streams and options.

        Args:
            read_stream: Stream for receiving messages
            write_stream: Stream for sending messages
            initialization_options: Server initialization options
            raise_exceptions: Whether to raise exceptions or handle them internally
        """
        if not self._transport:
            raise ValueError("Transport not set. Call set_transport() before run()")

        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(self.lifespan(self))
            session = await stack.enter_async_context(
                AtlassianSession(
                    read_stream=read_stream,
                    write_stream=write_stream,
                    transport=self._transport,
                    init_options=initialization_options,
                )
            )

            async with anyio.create_task_group() as tg:
                async for message in session.incoming_messages:
                    logger.debug(f"Received message: {message}")

                    tg.start_soon(
                        self._handle_message,
                        message,
                        session,
                        lifespan_context,
                        raise_exceptions,
                    )

    def set_transport(self, transport: AtlassianSseServerTransport) -> None:
        """Set the transport instance.

        Args:
            transport: The transport instance to set
        """
        self._transport = transport
