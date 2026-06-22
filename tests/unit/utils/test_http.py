"""Tests for the shared HTTP utilities (retry, concurrency, rate limit)."""

import threading
import time
from unittest.mock import MagicMock

import pytest
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

from mcp_atlassian.utils.http import (
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_STATUSES,
    DEFAULT_RETRY_TOTAL,
    CircuitBreakerOpenError,
    _reset_circuit_breaker_for_tests,
    _reset_concurrency_semaphore_for_tests,
    _reset_rate_limit_bucket_for_tests,
    configure_circuit_breaker,
    configure_concurrency,
    configure_rate_limit,
    configure_retry,
    format_rate_limit_error,
)


@pytest.fixture(autouse=True)
def _reset_state():
    _reset_concurrency_semaphore_for_tests()
    _reset_rate_limit_bucket_for_tests()
    _reset_circuit_breaker_for_tests()
    yield
    _reset_concurrency_semaphore_for_tests()
    _reset_rate_limit_bucket_for_tests()
    _reset_circuit_breaker_for_tests()


def _new_session() -> Session:
    """Fresh Session with default adapters mounted."""
    s = Session()
    assert s.adapters
    return s


def test_configure_retry_applies_to_all_adapters_with_defaults():
    session = _new_session()
    configure_retry(session, service="Test")

    for adapter in session.adapters.values():
        assert isinstance(adapter, HTTPAdapter)
        retry = adapter.max_retries
        assert isinstance(retry, Retry)
        assert retry.total == DEFAULT_RETRY_TOTAL
        assert retry.backoff_factor == DEFAULT_RETRY_BACKOFF
        assert set(retry.status_forcelist or ()) == set(DEFAULT_RETRY_STATUSES)
        assert retry.respect_retry_after_header is True
        assert retry.allowed_methods  # narrow Literal[False] away
        assert "GET" in retry.allowed_methods
        assert "POST" not in retry.allowed_methods


def test_configure_retry_respects_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "2")
    monkeypatch.setenv("ATLASSIAN_RETRY_BACKOFF", "0.25")
    monkeypatch.setenv("ATLASSIAN_RETRY_INCLUDE_WRITES", "true")

    session = _new_session()
    configure_retry(session, service="Test")

    adapter = next(iter(session.adapters.values()))
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 2
    assert retry.backoff_factor == 0.25
    assert retry.allowed_methods  # narrow Literal[False] away
    assert "POST" in retry.allowed_methods
    assert "DELETE" in retry.allowed_methods


def test_configure_retry_disabled_when_total_le_zero(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "0")

    session = _new_session()
    before = {}
    for prefix, adapter in session.adapters.items():
        assert isinstance(adapter, HTTPAdapter)
        before[prefix] = adapter.max_retries
    configure_retry(session, service="Test")

    for prefix, adapter in session.adapters.items():
        assert isinstance(adapter, HTTPAdapter)
        assert adapter.max_retries is before[prefix]


def test_configure_retry_invalid_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "not-an-int")
    monkeypatch.setenv("ATLASSIAN_RETRY_BACKOFF", "abc")

    session = _new_session()
    configure_retry(session, service="Test")

    adapter = next(iter(session.adapters.values()))
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
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


def test_format_rate_limit_error_includes_retry_after():
    http_err = MagicMock()
    http_err.response.headers = {"Retry-After": "42"}
    msg = format_rate_limit_error(http_err, service="Jira")
    assert "Jira" in msg
    assert "42" in msg
    assert "Retry-After" in msg


def test_format_rate_limit_error_handles_missing_header():
    http_err = MagicMock()
    http_err.response.headers = {}
    msg = format_rate_limit_error(http_err, service="Confluence")
    assert "Confluence" in msg
    assert "429" in msg
    assert "back off" in msg.lower()


def test_format_rate_limit_error_handles_no_response():
    http_err = MagicMock()
    http_err.response = None
    msg = format_rate_limit_error(http_err, service="Jira")
    assert "429" in msg


def test_format_rate_limit_error_handles_http_date_retry_after():
    """Retry-After can be an HTTP-date per RFC 9110 — surface the raw value
    without claiming it's in seconds."""
    http_err = MagicMock()
    http_err.response.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    msg = format_rate_limit_error(http_err, service="Jira")
    assert "Wed, 21 Oct 2026 07:28:00 GMT" in msg
    assert "seconds" not in msg.lower()


def test_configure_concurrency_disabled_by_default():
    from mcp_atlassian.utils.http import _THROTTLED_ATTR

    session = Session()
    configure_concurrency(session, service="Test")
    for adapter in session.adapters.values():
        assert not getattr(adapter, _THROTTLED_ATTR, False)


def test_configure_concurrency_caps_parallel_sends(monkeypatch: pytest.MonkeyPatch):
    """Cap=2 means at most 2 send() calls run concurrently."""
    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "2")

    session = Session()
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def slow_send(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return MagicMock()

    for adapter in session.adapters.values():
        adapter.send = slow_send  # type: ignore[method-assign]

    configure_concurrency(session, service="Test")

    threads = [
        threading.Thread(target=lambda: session.adapters["https://"].send(MagicMock()))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_in_flight <= 2, f"expected cap=2, observed {max_in_flight} in flight"


def test_configure_concurrency_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    from mcp_atlassian.utils.http import _THROTTLED_ATTR

    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "3")
    session = Session()
    configure_concurrency(session, service="Test")
    adapter = session.adapters["https://"]
    wrapped_func = adapter.send
    configure_concurrency(session, service="Test")
    assert adapter.send is wrapped_func
    assert getattr(adapter, _THROTTLED_ATTR) is True


def test_configure_concurrency_shares_semaphore_across_sessions(
    monkeypatch: pytest.MonkeyPatch,
):
    """Two sessions (Jira + Confluence) must share the cap, not get one each."""
    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "2")

    s1, s2 = Session(), Session()
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def slow_send(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return MagicMock()

    for sess in (s1, s2):
        for adapter in sess.adapters.values():
            adapter.send = slow_send  # type: ignore[method-assign]

    configure_concurrency(s1, service="S1")
    configure_concurrency(s2, service="S2")

    threads = []
    for sess in (s1, s2):
        for _ in range(4):
            threads.append(
                threading.Thread(
                    target=lambda s=sess: s.adapters["https://"].send(MagicMock())
                )
            )
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_in_flight <= 2


def test_configure_rate_limit_disabled_by_default():
    from mcp_atlassian.utils.http import _RATE_LIMITED_ATTR

    session = Session()
    configure_rate_limit(session, service="Test")
    for adapter in session.adapters.values():
        assert not getattr(adapter, _RATE_LIMITED_ATTR, False)


def test_configure_rate_limit_throttles_requests(monkeypatch: pytest.MonkeyPatch):
    """At 10 rps, 5 sends after the burst should take >= ~0.4s."""
    monkeypatch.setenv("ATLASSIAN_REQUESTS_PER_SECOND", "10")

    session = Session()
    for adapter in session.adapters.values():
        adapter.send = lambda *a, **kw: MagicMock()  # type: ignore[method-assign]

    configure_rate_limit(session, service="Test")

    adapter = session.adapters["https://"]
    for _ in range(10):
        adapter.send(MagicMock())  # drain burst

    start = time.monotonic()
    for _ in range(5):
        adapter.send(MagicMock())
    elapsed = time.monotonic() - start

    assert elapsed >= 0.35, f"expected throttling >= 0.35s, got {elapsed:.3f}s"


def test_configure_rate_limit_shares_bucket_across_sessions(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_REQUESTS_PER_SECOND", "5")

    s1, s2 = Session(), Session()
    for sess in (s1, s2):
        for adapter in sess.adapters.values():
            adapter.send = lambda *a, **kw: MagicMock()  # type: ignore[method-assign]

    configure_rate_limit(s1, service="S1")
    configure_rate_limit(s2, service="S2")

    s1.adapters["https://"].send(MagicMock())
    s1.adapters["https://"].send(MagicMock())
    s2.adapters["https://"].send(MagicMock())
    s2.adapters["https://"].send(MagicMock())
    s2.adapters["https://"].send(MagicMock())

    start = time.monotonic()
    s1.adapters["https://"].send(MagicMock())
    elapsed = time.monotonic() - start
    assert elapsed >= 0.1


def _build_circuit_session(status_codes_iter):
    session = Session()
    iterator = iter(status_codes_iter)

    def fake_send(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = next(iterator)
        return resp

    for adapter in session.adapters.values():
        adapter.send = fake_send  # type: ignore[method-assign]
    return session


def test_circuit_breaker_disabled_by_default():
    from mcp_atlassian.utils.http import _CIRCUIT_BREAKER_ATTR

    session = Session()
    configure_circuit_breaker(session, service="Test")
    for adapter in session.adapters.values():
        assert not getattr(adapter, _CIRCUIT_BREAKER_ATTR, False)


def test_circuit_breaker_trips_after_threshold(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "3")
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", "60")

    session = _build_circuit_session([429, 429, 429, 429])
    configure_circuit_breaker(session, service="Test")

    adapter = session.adapters["https://"]
    for _ in range(3):
        resp = adapter.send(MagicMock())
        assert resp.status_code == 429

    with pytest.raises(CircuitBreakerOpenError):
        adapter.send(MagicMock())


def test_circuit_breaker_resets_on_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "3")
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", "60")

    session = _build_circuit_session([429, 429, 200, 429, 429])
    configure_circuit_breaker(session, service="Test")

    adapter = session.adapters["https://"]
    for _ in range(5):
        adapter.send(MagicMock())  # must not raise

    from mcp_atlassian.utils.http import _circuit_breaker

    assert _circuit_breaker is not None
    assert _circuit_breaker.failures == 2  # last two 429s, no trip


def test_circuit_breaker_cooldown_then_reset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "2")
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", "0.1")

    session = _build_circuit_session([429, 429, 200])
    configure_circuit_breaker(session, service="Test")
    adapter = session.adapters["https://"]

    adapter.send(MagicMock())
    adapter.send(MagicMock())  # trips

    with pytest.raises(CircuitBreakerOpenError):
        adapter.send(MagicMock())

    time.sleep(0.15)
    resp = adapter.send(MagicMock())
    assert resp.status_code == 200
