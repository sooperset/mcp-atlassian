"""Base client module for Zephyr Essential API interactions."""

import logging
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .auth import generate_zephyr_jwt
from .config import ZephyrConfig

# Configure logging
logger = logging.getLogger("mcp-zephyr")


class ZephyrClient:
    """Base client for Zephyr Essential API interactions."""
    
    def __init__(self, config: ZephyrConfig = None) -> None:
        """Initialize the Zephyr client with configuration options.
        
        Args:
            config: Optional configuration object (will use env vars if not provided)
            
        Raises:
            ValueError: If configuration is invalid or required credentials are missing
        """
        # Load configuration from environment variables if not provided
        self.config = config or ZephyrConfig.from_env()
        
        # Initialize the session
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
    def _request(self, method: str, endpoint: str, params: Dict[str, str] = None, **kwargs) -> Any:
        """Make a request to the Zephyr API with JWT authentication.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: Query parameters as a dictionary
            **kwargs: Additional arguments to pass to requests.request
            
        Returns:
            API response parsed as JSON, or None if no content
            
        Raises:
            requests.exceptions.HTTPError: If the request fails
        """
        if params is None:
            params = {}
            
        url = f"{self.config.base_url}{endpoint}"
        
        # Parse the endpoint to get the path for JWT generation
        parsed_url = urlparse(url)
        api_path = parsed_url.path
        
        # Generate JWT token
        jwt_token = generate_zephyr_jwt(
            method=method,
            api_path=api_path,
            query_params=params,
            account_id=self.config.account_id,
            access_key=self.config.access_key,
            secret_key=self.config.secret_key
        )
        
        # Add JWT token to Authorization header
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f"JWT {jwt_token}"
        
        # Make the request
        response = self.session.request(
            method, 
            url, 
            params=params, 
            headers=headers, 
            **kwargs
        )
        
        try:
            response.raise_for_status()
            if response.content:
                return response.json()
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"Zephyr API error: {e}")
            if response.content:
                try:
                    error_data = response.json()
                    logger.error(f"Error details: {error_data}")
                except ValueError:
                    logger.error(f"Error response: {response.text}")
            raise