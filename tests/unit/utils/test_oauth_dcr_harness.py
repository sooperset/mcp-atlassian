"""Unit tests for the reusable OAuth DCR client test helper."""

from __future__ import annotations

from tests.utils.oauth_dcr_harness import build_pkce_verifier


def test_build_pkce_verifier_returns_rfc7636_s256_pair() -> None:
    """The challenge is URL-safe and derived from the returned verifier."""
    verifier, challenge = build_pkce_verifier()

    assert len(verifier) >= 43
    assert "=" not in challenge
    assert challenge == "GZxjAp2SHDH-5zrFuuLwz-h8rlUoY9fc7kq1GJXUhe0"
