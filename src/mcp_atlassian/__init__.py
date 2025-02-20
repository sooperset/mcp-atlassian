import asyncio

from . import server

__version__ = "0.1.8"


def main():
    """Main entry point for the package."""
    asyncio.run(server.main())


__all__ = ["main", "server", "__version__"]
