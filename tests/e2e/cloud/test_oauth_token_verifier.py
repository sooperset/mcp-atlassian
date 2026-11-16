"""Cloud E2E coverage for upstream OAuth token verification."""

from __future__ import annotations

import os
import uuid

import pytest

from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier

from .conftest import CloudInstanceInfo

pytestmark = pytest.mark.cloud_e2e


def _required_scopes() -> list[str]:
    """Return the resource scopes configured for the OAuth proxy test."""
    configured = os.environ.get("ATLASSIAN_OAUTH_SCOPE", "")
    scopes = [scope for scope in configured.replace(",", " ").split() if scope]
    return scopes or ["read:jira-work"]


@pytest.fixture
def cloud_oauth_verifier(
    cloud_instance: CloudInstanceInfo,
) -> AtlassianOpaqueTokenVerifier:
    """Build the verifier bound to the configured Cloud site."""
    assert cloud_instance.has_oauth(), (
        "Cloud OAuth E2E requires CLOUD_E2E_OAUTH_ACCESS_TOKEN and "
        "CLOUD_E2E_OAUTH_CLOUD_ID"
    )
    return AtlassianOpaqueTokenVerifier(
        instance_url=cloud_instance.jira_url,
        cloud_id=cloud_instance.oauth_cloud_id,
        required_scopes=_required_scopes(),
    )


@pytest.mark.anyio
async def test_cloud_oauth_token_is_verified_upstream(
    cloud_instance: CloudInstanceInfo,
    cloud_oauth_verifier: AtlassianOpaqueTokenVerifier,
) -> None:
    """Accept the configured live Cloud OAuth token with its granted scopes."""
    accepted = await cloud_oauth_verifier.verify_token(
        cloud_instance.oauth_access_token
    )

    assert accepted is not None, "Configured Cloud OAuth token was rejected"
    assert accepted.token == cloud_instance.oauth_access_token
    assert set(_required_scopes()).issubset(accepted.scopes)


@pytest.mark.anyio
async def test_cloud_oauth_token_rejects_format_valid_fabrication(
    cloud_oauth_verifier: AtlassianOpaqueTokenVerifier,
) -> None:
    """Reject a fabricated token that passes superficial format checks."""
    fabricated = f"invalid-{uuid.uuid4().hex}"
    rejected = await cloud_oauth_verifier.verify_token(fabricated)

    assert rejected is None, "Fabricated Cloud OAuth token was accepted"
