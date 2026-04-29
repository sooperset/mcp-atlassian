"""Tests for the shared HTTP retry utilities."""

import pytest
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

from mcp_atlassian.utils.http import (
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_STATUSES,
    DEFAULT_RETRY_TOTAL,
    configure_retry,
)


def _new_session() -> Session:
    """Fresh Session with default adapters mounted."""
    s = Session()
    assert s.adapters
    return s


def test_configure_retry_applies_to_all_adapters_with_defaults():
    session = _new_session()
    configure_retry(session, service="Test")

    for adapter in session.adapters.values():
        retry = adapter.max_retries
        assert isinstance(retry, Retry)
        assert retry.total == DEFAULT_RETRY_TOTAL
        assert retry.backoff_factor == DEFAULT_RETRY_BACKOFF
        assert tuple(retry.status_forcelist) == DEFAULT_RETRY_STATUSES
        assert retry.respect_retry_after_header is True
        assert "GET" in retry.allowed_methods
        assert "POST" not in retry.allowed_methods


def test_configure_retry_respects_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "2")
    monkeypatch.setenv("ATLASSIAN_RETRY_BACKOFF", "0.25")
    monkeypatch.setenv("ATLASSIAN_RETRY_INCLUDE_WRITES", "true")

    session = _new_session()
    configure_retry(session, service="Test")

    adapter = next(iter(session.adapters.values()))
    retry = adapter.max_retries
    assert retry.total == 2
    assert retry.backoff_factor == 0.25
    assert "POST" in retry.allowed_methods
    assert "DELETE" in retry.allowed_methods


def test_configure_retry_disabled_when_total_le_zero(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "0")

    session = _new_session()
    before = {prefix: adapter.max_retries for prefix, adapter in session.adapters.items()}
    configure_retry(session, service="Test")

    for prefix, adapter in session.adapters.items():
        assert adapter.max_retries is before[prefix]


def test_configure_retry_invalid_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "not-an-int")
    monkeypatch.setenv("ATLASSIAN_RETRY_BACKOFF", "abc")

    session = _new_session()
    configure_retry(session, service="Test")

    retry = next(iter(session.adapters.values())).max_retries
    assert retry.total == DEFAULT_RETRY_TOTAL
    assert retry.backoff_factor == DEFAULT_RETRY_BACKOFF


def test_configure_retry_patches_custom_adapter_in_place():
    """Custom adapters mounted before configure_retry should be patched, not replaced."""
    session = Session()
    custom = HTTPAdapter()
    session.mount("https://example.com", custom)

    configure_retry(session, service="Test")

    assert session.adapters["https://example.com"] is custom
    assert isinstance(custom.max_retries, Retry)
