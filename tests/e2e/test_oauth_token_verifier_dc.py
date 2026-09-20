"""Data Center E2E coverage for upstream OAuth token verification."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier

from .conftest import DCInstanceInfo

pytestmark = pytest.mark.dc_e2e


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("url_attribute", "token_attribute"),
    (("jira_url", "jira_pat"), ("confluence_url", "confluence_pat")),
    ids=("jira", "confluence"),
)
async def test_dc_oauth_token_verifier_accepts_live_pat_and_rejects_fabrication(
    dc_instance: DCInstanceInfo,
    url_attribute: str,
    token_attribute: str,
) -> None:
    """Validate a fixture-created PAT and reject a fabricated bearer token."""
    instance_url = getattr(dc_instance, url_attribute)
    access_token = getattr(dc_instance, token_attribute)
    assert access_token, f"No {token_attribute} was created for DC E2E"

    verifier = AtlassianOpaqueTokenVerifier(
        instance_url=instance_url,
        is_cloud=False,
    )
    accepted = await verifier.verify_token(access_token)
    rejected = await verifier.verify_token(f"invalid-{uuid.uuid4().hex}")

    assert accepted is not None, f"Valid {token_attribute} was rejected"
    assert accepted.token == access_token
    assert rejected is None, "Fabricated Data Center OAuth token was accepted"
