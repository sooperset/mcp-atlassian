"""Tests for the pagination clamp utility."""

import pytest

from mcp_atlassian.utils.pagination import clamp_limit


def test_clamp_limit_passthrough_when_env_unset(monkeypatch: pytest.MonkeyPatch):
    """Default behavior: no clamping unless env is set."""
    monkeypatch.delenv("ATLASSIAN_MAX_PAGINATION_LIMIT", raising=False)
    assert clamp_limit(500) == 500
    assert clamp_limit(50) == 50


def test_clamp_limit_respects_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_MAX_PAGINATION_LIMIT", "25")
    assert clamp_limit(500) == 25
    assert clamp_limit(10) == 10


def test_clamp_limit_disabled_when_cap_le_zero(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_MAX_PAGINATION_LIMIT", "0")
    assert clamp_limit(9999) == 9999


def test_clamp_limit_invalid_env_passes_through(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_MAX_PAGINATION_LIMIT", "not-a-number")
    assert clamp_limit(500) == 500


def test_clamp_limit_passes_through_non_positive():
    # Caller's own validation handles 0/negative; clamp doesn't fight it.
    assert clamp_limit(0) == 0
    assert clamp_limit(-5) == -5
