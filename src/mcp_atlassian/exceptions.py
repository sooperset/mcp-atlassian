class MCPAtlassianAuthenticationError(Exception):
    """Raised when Atlassian API authentication fails (401/403)."""

    pass


class MCPAtlassianError(Exception):
    """Base exception for MCP-Atlassian errors."""

    pass
