"""Constants for Bitbucket Server integration."""

from typing import Final

# Authentication methods
AUTH_TYPE_PERSONAL_TOKEN: Final[str] = "personal_token"
AUTH_TYPE_BASIC: Final[str] = "basic"

# Environment variable names
ENV_BITBUCKET_URL: Final[str] = "BITBUCKET_URL"
ENV_BITBUCKET_USERNAME: Final[str] = "BITBUCKET_USERNAME"
ENV_BITBUCKET_API_TOKEN: Final[str] = "BITBUCKET_API_TOKEN"
ENV_BITBUCKET_PERSONAL_TOKEN: Final[str] = "BITBUCKET_PERSONAL_TOKEN"
ENV_BITBUCKET_SSL_VERIFY: Final[str] = "BITBUCKET_SSL_VERIFY"
ENV_BITBUCKET_PROJECTS_FILTER: Final[str] = "BITBUCKET_PROJECTS_FILTER"

# API endpoints
API_BASE_PATH: Final[str] = "/rest/api/latest"

# Default values
DEFAULT_SSL_VERIFY: Final[bool] = True
