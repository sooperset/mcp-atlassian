from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession
from mcp.types import JSONRPCMessage

from .transport import AtlassianSseServerTransport


class AtlassianSession(ServerSession):
    """Custom session class that stores the transport instance."""

    def __init__(
        self,
        read_stream: MemoryObjectReceiveStream[JSONRPCMessage | Exception],
        write_stream: MemoryObjectSendStream[JSONRPCMessage],
        transport: AtlassianSseServerTransport,
        init_options: InitializationOptions,
    ) -> None:
        """Initialize the Atlassian session.

        Args:
            read_stream: Stream for receiving messages
            write_stream: Stream for sending messages
            transport: The SSE transport instance
            init_options: Server initialization options
        """
        super().__init__(
            read_stream=read_stream,
            write_stream=write_stream,
            init_options=init_options,
        )
        self.transport = transport

    def get_transport(self) -> AtlassianSseServerTransport:
        """Get the transport instance associated with this session.

        Returns:
            The SSE transport instance
        """
        return self.transport
