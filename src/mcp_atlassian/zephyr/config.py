"""Configuration module for Zephyr Essential API."""

import os
from dataclasses import dataclass


@dataclass
class ZephyrConfig:
    """Configuration for Zephyr Essential API."""
    
    base_url: str
    account_id: str
    access_key: str
    secret_key: str
    
    @classmethod
    def from_env(cls) -> "ZephyrConfig":
        """Create configuration from environment variables.
        
        Returns:
            ZephyrConfig: Configuration object with values from environment variables
            
        Raises:
            ValueError: If required environment variables are missing
        """
        base_url = os.getenv("ZAPI_BASE_URL", "https://prod-api.zephyr4jiracloud.com/connect")
        account_id = os.getenv("JIRA_USERNAME")
        access_key = os.getenv("ZAPI_ACCESS_KEY")
        secret_key = os.getenv("ZAPI_SECRET_KEY")
        
        if not all([account_id, access_key, secret_key]):
            raise ValueError(
                "ZAPI_ACCOUNT_ID, ZAPI_ACCESS_KEY, and ZAPI_SECRET_KEY "
                "environment variables are required"
            )
            
        return cls(
            base_url=base_url.rstrip('/'),
            access_key=access_key,
            account_id=account_id,
            secret_key=secret_key
        )