class MCPAtlassianAuthenticationError(Exception):
    """Raised when Atlassian API authentication fails (401/403)."""

    pass


class ScopeViolationError(ValueError):
    """Raised when a tool targets a project or space outside the allowlist.

    ``JIRA_PROJECTS_FILTER`` and ``CONFLUENCE_SPACES_FILTER`` bound every tool,
    not only search. The message never says whether the target exists.
    """
