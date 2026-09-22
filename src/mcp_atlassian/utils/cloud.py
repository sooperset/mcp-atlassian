"""Trusted Atlassian Cloud endpoint selection from the configured tenant URL."""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class CloudEndpoints:
    """OAuth and API hosts for one Atlassian Cloud environment."""

    auth_host: str
    api_host: str

    @property
    def authorize_url(self) -> str:
        """Return the authorization endpoint."""
        return f"https://{self.auth_host}/authorize"

    @property
    def token_url(self) -> str:
        """Return the token exchange and refresh endpoint."""
        return f"https://{self.auth_host}/oauth/token"

    @property
    def resources_url(self) -> str:
        """Return the site discovery endpoint."""
        return f"https://{self.api_host}/oauth/token/accessible-resources"

    @property
    def api_url(self) -> str:
        """Return the API origin."""
        return f"https://{self.api_host}"


COMMERCIAL = CloudEndpoints("auth.atlassian.com", "api.atlassian.com")
GOV_MODERATE = CloudEndpoints(
    "auth.atlassian-us-gov-mod.com", "api.atlassian-us-gov-mod.com"
)


def cloud_endpoints(service_url: str | None) -> CloudEndpoints:
    """Select fixed hosts, never an arbitrary OAuth destination from user input.

    The legacy Government hostname has no verified endpoint mapping. Refuse it
    rather than sending government credentials to the commercial environment.
    """
    host = (urlparse(service_url or "").hostname or "").lower().rstrip(".")
    if host.endswith(".atlassian-us-gov.net"):
        raise ValueError(
            "Unsupported Government Cloud domain; use the Moderate tenant URL"
        )
    if host.endswith(".atlassian-us-gov-mod.net") or host in {
        GOV_MODERATE.auth_host,
        GOV_MODERATE.api_host,
    }:
        return GOV_MODERATE
    return COMMERCIAL
