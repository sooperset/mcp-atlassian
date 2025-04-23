"""Entry point for running the MCP Atlassian server."""

import argparse
import asyncio
import logging
import os
import sys

from mcp_atlassian.server import run_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-atlassian")


async def main() -> None:
    """Run the MCP Atlassian server."""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Run the MCP Atlassian server")
        parser.add_argument(
            "--transport",
            type=str,
            choices=["stdio", "sse"],
            default=os.getenv("MCP_TRANSPORT", "stdio"),
            help="Transport type (stdio or sse)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("MCP_PORT", "8000")),
            help="Port number for SSE transport",
        )
        args = parser.parse_args()

        # Run the server
        await run_server(transport=args.transport, port=args.port)
    except Exception as e:
        logger.error(f"Error running server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
