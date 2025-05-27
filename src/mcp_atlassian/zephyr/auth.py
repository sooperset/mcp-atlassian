"""Authentication module for Zephyr Essential API."""

import hashlib
import time
from typing import Dict, Optional

import jwt  # PyJWT library


def generate_zephyr_jwt(
    method: str,
    api_path: str,
    query_params: Optional[Dict[str, str]] = None,
    account_id: str = "",
    access_key: str = "",
    secret_key: str = "",
    expiration_sec: int = 3600
) -> str:
    """
    Generate a JWT token for Zephyr API authentication.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        api_path: API path without base URL
        query_params: Query parameters as a dictionary
        account_id: Zephyr Account ID
        access_key: Zephyr Access Key
        secret_key: Zephyr Secret Key
        expiration_sec: Token expiration time in seconds
        
    Returns:
        JWT token string
    """
    if query_params is None:
        query_params = {}
    
    # Sort query parameters alphabetically
    canonical_query = "&".join(
        f"{key}={query_params[key]}" 
        for key in sorted(query_params.keys())
    )
    
    # Build the canonical string: METHOD&<path>&<query>
    canonical = f"{method.upper()}&{api_path}&{canonical_query}"
    
    # Create SHA-256 hex hash of canonical string
    qsh = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    
    # Timestamps
    now = int(time.time())
    exp = now + expiration_sec
    
    # JWT claims
    payload = {
        "sub": account_id,  # Atlassian account ID
        "iss": access_key,  # Zephyr Access Key
        "qsh": qsh,         # query-string hash
        "iat": now,
        "exp": exp,
    }
    
    # Sign with HMAC-SHA256 using Zephyr Secret Key
    return jwt.encode(payload, secret_key, algorithm="HS256")