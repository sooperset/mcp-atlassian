class MCPAtlassianError(Exception):
    """Base exception for MCP Atlassian tool failures.

    Raised from `@jira_mcp.tool()` / `@confluence_mcp.tool()` handlers so the
    failure surfaces on the MCP wire as `isError=true` (not as a JSON-encoded
    success content block). The original cause should be chained via
    `raise MCPAtlassianError(...) from e` to preserve the traceback.
    """

    pass


class MCPAtlassianAuthenticationError(MCPAtlassianError):
    """Raised when Atlassian API authentication fails (401/403)."""

    pass
