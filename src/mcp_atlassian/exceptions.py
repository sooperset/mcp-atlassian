class MCPAtlassianAuthenticationError(Exception):
    """Raised when Atlassian API authentication fails (401/403)."""

    pass


class ScopeViolationError(ValueError):
    """Raised when a tool targets a project or space outside the allowlist.

    ``JIRA_PROJECTS_FILTER`` and ``CONFLUENCE_SPACES_FILTER`` bound every tool,
    not only search. The message names only what the caller passed and does
    not say whether the target exists. The number of upstream requests and the
    time a denial takes can still differ between a missing target and one
    outside the allowlist.
    """
