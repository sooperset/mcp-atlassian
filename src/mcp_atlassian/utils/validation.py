"""Validation utilities for MCP Atlassian."""

import json
from typing import Any


def ensure_json_string(v: Any) -> str:
    """
    Pydantic validator that ensures the input is a JSON string.
    If input is already parsed (list/dict), dump it back to string.
    """
    if isinstance(v, str):
        # It's already a string, potentially JSON, pass through
        return v
    elif isinstance(v, list | dict):
        # It was pre-parsed, dump back to JSON string
        try:
            return json.dumps(v)
        except TypeError as e:
            # Handle potential serialization errors
            raise ValueError(
                f"Could not serialize pre-parsed input back to JSON string: {e}"
            ) from e
    # Handle other unexpected types
    raise ValueError(f"Unexpected input type: {type(v)}. Expected str, list, or dict.")
