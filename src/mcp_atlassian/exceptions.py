class MCPAtlassianAuthenticationError(Exception):
    """Raised when Atlassian API authentication fails (401/403)."""

    pass


class ApiError(Exception):
    """Raised when an API request fails."""

    pass


class BitbucketServerApiError(ApiError):
    """Raised when a Bitbucket Server API request fails."""

    pass
