"""Main server implementation that mounts all service servers."""

import logging
import sys
from typing import Literal

import click
import uvicorn
from fastmcp import FastMCP

from .confluence import confluence_mcp
from .jira import jira_mcp

logger = logging.getLogger("mcp-atlassian")


# Create the main FastMCP instance
main_mcp = FastMCP(
    "Atlassian MCP",
    description="Atlassian tools and resources for interacting with Jira and Confluence",
)

# Mount service-specific FastMCP instances
main_mcp.mount("jira", jira_mcp)
main_mcp.mount("confluence", confluence_mcp)


async def run_server(
    transport: Literal["stdio", "websocket", "http"] = "stdio",
    port: int = 8000,
    host: str = "127.0.0.1",
) -> None:
    """Run the MCP Atlassian server.

    Args:
        transport: The transport to use. One of "stdio", "websocket", or "http".
        port: The port to use for websocket or http transports.
        host: The host to bind to for http transport (default: localhost).
    """
    if transport == "stdio":
        # Use the built-in method if available, otherwise fallback
        if hasattr(main_mcp, "run_stdio_async"):
            await main_mcp.run_stdio_async()
        else:
            await main_mcp.run(transport="mcp.server.StdioTransport")

    elif transport == "websocket":
        await main_mcp.run(
            transport="mcp.server.WebsocketTransport", transport_kwargs={"port": port}
        )

    elif transport == "http":
        app = main_mcp.get_asgi_app()
        uvicorn.run(app, host=host, port=port)

    else:
        raise ValueError(f"Unknown transport: {transport}")


@click.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "websocket", "http"]),
    default="stdio",
    help="Transport to use",
)
@click.option(
    "--port",
    type=int,
    default=8000,
    help="Port to use (only for websocket/http transport)",
)
def cli(transport: str, port: int) -> None:
    """CLI entry point for running the MCP Atlassian server."""
    import asyncio

    try:
        asyncio.run(run_server(transport=transport, port=port))
    except KeyboardInterrupt:
        logger.info("Shutting down MCP Atlassian server...")
        sys.exit(0)


if __name__ == "__main__":
    cli()
