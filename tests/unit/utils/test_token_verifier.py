"""Unit tests for Atlassian opaque token verifier."""

from __future__ import annotations

import pytest
from fastmcp.server.auth.auth import AccessToken

from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier


@pytest.mark.anyio
async def test_verify_token_returns_fastmcp_access_token() -> None:
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=["read:jira-work"])

    token = await verifier.verify_token("opaque-token")

    assert isinstance(token, AccessToken)
    assert token is not None
    assert token.token == "opaque-token"
    assert token.scopes == ["read:jira-work"]


@pytest.mark.anyio
async def test_verify_token_returns_none_for_empty_token() -> None:
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=[])

    token = await verifier.verify_token("")

    assert token is None
