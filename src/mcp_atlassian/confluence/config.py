"""Configuration module for the Confluence client."""

import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class ConfluenceConfig:
    """Configuration for Confluence client."""

    url: str
    is_cloud: bool = True
    ssl_verify: bool = True
    auth_type: Literal["basic", "token"] = "basic"
    username: str = ""
    api_token: str = ""
    personal_token: str = ""
    
    # Cache configuration
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300  # Default TTL: 5 minutes
    
    # Async configuration
    default_timeout_seconds: int = 30  # Default timeout: 30 seconds
    max_concurrent_requests: int = 5  # Default concurrency: 5 requests

    @property
    def verify_ssl(self) -> bool:
        """Compatibility property for old code.

        Returns:
            The ssl_verify value
        """
        return self.ssl_verify

    @classmethod
    def from_env(cls) -> "ConfluenceConfig":
        """Load configuration from environment variables.

        Returns:
            ConfluenceConfig instance with values from environment

        Raises:
            ValueError: If required environment variables are missing
        """
        # Required variables
        try:
            url = os.environ["CONFLUENCE_URL"]
        except KeyError as e:
            raise ValueError(f"Required environment variable {e} is missing") from e

        # Optional variables with defaults
        is_cloud = str(os.environ.get("CONFLUENCE_CLOUD", "true")).lower() == "true"
        ssl_verify = str(os.environ.get("CONFLUENCE_SSL_VERIFY", "true")).lower() == "true"
        auth_type = os.environ.get("CONFLUENCE_AUTH_TYPE", "basic")

        # Auth-specific variables
        username = os.environ.get("CONFLUENCE_USERNAME", "")
        api_token = os.environ.get("CONFLUENCE_API_TOKEN", "")
        personal_token = os.environ.get("CONFLUENCE_PERSONAL_TOKEN", "")

        # Cache configuration
        cache_enabled = str(os.environ.get("CONFLUENCE_CACHE_ENABLED", "true")).lower() == "true"
        cache_ttl_seconds = int(os.environ.get("CONFLUENCE_CACHE_TTL", "300"))
        
        # Async configuration
        default_timeout_seconds = int(os.environ.get("CONFLUENCE_TIMEOUT", "30"))
        max_concurrent_requests = int(os.environ.get("CONFLUENCE_MAX_CONCURRENT", "5"))

        # Validate auth configuration
        if auth_type == "basic" and (not username or not api_token):
            raise ValueError(
                "For basic authentication, CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN are required"
            )
        elif auth_type == "token" and not personal_token:
            raise ValueError(
                "For token authentication, CONFLUENCE_PERSONAL_TOKEN is required"
            )

        # Create and return the configuration instance
        return cls(
            url=url,
            is_cloud=is_cloud,
            ssl_verify=ssl_verify,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            cache_enabled=cache_enabled,
            cache_ttl_seconds=cache_ttl_seconds,
            default_timeout_seconds=default_timeout_seconds,
            max_concurrent_requests=max_concurrent_requests,
        )
