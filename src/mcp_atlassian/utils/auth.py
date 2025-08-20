"""Authentication utilities for Atlassian Server/DC and Cloud instances."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from requests import Session

logger = logging.getLogger("mcp-atlassian")


def configure_server_pat_auth(session: "Session", personal_token: str) -> None:
    """Configure Bearer authentication for Server/DC Personal Access Tokens.
    
    Atlassian Server/Data Center instances use Bearer authentication for PATs,
    not Basic authentication like Cloud instances use for API tokens.
    
    Args:
        session: The requests session to configure
        personal_token: The Personal Access Token
    """
    logger.debug("Configuring Bearer authentication for Server/DC PAT")
    session.headers["Authorization"] = f"Bearer {personal_token}"
