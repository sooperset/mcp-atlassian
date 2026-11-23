"""Tests for the shared HTTP utilities (retry, concurrency, rate limit)."""

import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock

import pytest
import requests
from requests import Response
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry
from urllib3.util.ssltransport import SSLTransport

import mcp_atlassian.utils.http as http_module
from mcp_atlassian.utils.http import (
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_MAX_RETRY_AFTER,
    DEFAULT_RETRY_STATUSES,
    DEFAULT_RETRY_TOTAL,
    CallBudget,
    CircuitBreakerOpenError,
    UpstreamCallAborted,
    _BoundedRetry,
    _reset_circuit_breaker_for_tests,
    _reset_concurrency_semaphore_for_tests,
    _reset_rate_limit_bucket_for_tests,
    configure_circuit_breaker,
    configure_concurrency,
    configure_default_timeout,
    configure_rate_limit,
    configure_retry,
    format_rate_limit_error,
)
from mcp_atlassian.utils.ssrf_adapter import _pinned_create_connection


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


def test_configure_retry_bounded_reads_by_default(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "ATLASSIAN_RETRY_TOTAL",
        "ATLASSIAN_RETRY_BACKOFF",
        "ATLASSIAN_RETRY_INCLUDE_WRITES",
        "ATLASSIAN_RETRY_IGNORE_RETRY_AFTER",
        "ATLASSIAN_RETRY_MAX_RETRY_AFTER",
    ):
        monkeypatch.delenv(name, raising=False)

    session = _new_session()
    configure_retry(session, service="Test")

    assert DEFAULT_RETRY_TOTAL == 3
    for adapter in session.adapters.values():
        assert isinstance(adapter, HTTPAdapter)
        retry = adapter.max_retries
        assert isinstance(retry, Retry)
        assert retry.total == 3
        assert retry.backoff_factor == DEFAULT_RETRY_BACKOFF
        assert isinstance(retry, _BoundedRetry)
        assert retry.max_retry_after == DEFAULT_RETRY_MAX_RETRY_AFTER
        assert retry.respect_retry_after_header is True
        assert set(retry.allowed_methods or ()) == {"GET", "HEAD", "OPTIONS"}
        assert 401 not in retry.status_forcelist


def test_configure_retry_applies_to_all_adapters_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "5")

    session = _new_session()
    configure_retry(session, service="Test")

    for adapter in session.adapters.values():
        assert isinstance(adapter, HTTPAdapter)
        retry = adapter.max_retries
        assert isinstance(retry, Retry)
        assert retry.total == 5
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


def test_configure_retry_respects_retry_after_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "5")
    monkeypatch.delenv("ATLASSIAN_RETRY_IGNORE_RETRY_AFTER", raising=False)

    session = _new_session()
    configure_retry(session, service="Test")

    adapter = next(iter(session.adapters.values()))
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.respect_retry_after_header is True


def test_configure_retry_ignores_retry_after_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "5")
    monkeypatch.setenv("ATLASSIAN_RETRY_IGNORE_RETRY_AFTER", "true")

    session = _new_session()
    configure_retry(session, service="Test")

    adapter = next(iter(session.adapters.values()))
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    # A gateway sending `Retry-After: 0` would otherwise trigger instant retries;
    # ignoring the header forces exponential backoff instead.
    assert retry.respect_retry_after_header is False


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
    before = {}
    for prefix, adapter in session.adapters.items():
        assert isinstance(adapter, HTTPAdapter)
        before[prefix] = adapter.max_retries

    configure_retry(session, service="Test")

    for prefix, adapter in session.adapters.items():
        assert isinstance(adapter, HTTPAdapter)
        assert adapter.max_retries is not before[prefix]
        retry = adapter.max_retries
        assert isinstance(retry, Retry)
        assert retry.total == DEFAULT_RETRY_TOTAL
        assert retry.backoff_factor == DEFAULT_RETRY_BACKOFF


def test_configure_retry_invalid_backoff_falls_back_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "5")
    monkeypatch.setenv("ATLASSIAN_RETRY_BACKOFF", "abc")

    session = _new_session()
    configure_retry(session, service="Test")

    adapter = next(iter(session.adapters.values()))
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 5
    assert retry.backoff_factor == DEFAULT_RETRY_BACKOFF


def test_configure_retry_patches_custom_adapter_in_place(
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom adapters mounted before configure_retry should be patched, not replaced."""
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "5")

    session = Session()
    custom = HTTPAdapter()
    session.mount("https://example.com", custom)

    configure_retry(session, service="Test")

    assert session.adapters["https://example.com"] is custom
    assert isinstance(custom.max_retries, Retry)


# --- Wire-level retry behaviour against a local server (no real sleeping) ---


class _ScriptedServer:
    """Local HTTP server that answers every request with one fixed response."""

    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self) -> None:
                outer.hits += 1
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = do_HEAD = _reply  # noqa: N815

            def log_message(self, *args: object) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/rest/api/2/x"
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, args=(0.05,), daemon=True
        )
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def scripted_server() -> Iterator[object]:
    servers: list[_ScriptedServer] = []

    def make(status: int, headers: dict[str, str] | None = None) -> _ScriptedServer:
        server = _ScriptedServer(status, headers or {})
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.close()


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace time.sleep (shared module object) so retries never really wait."""
    sleeps: list[float] = []
    monkeypatch.setattr(
        "mcp_atlassian.utils.http.time.sleep", lambda s: sleeps.append(s)
    )
    return sleeps


def _clear_retry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ATLASSIAN_RETRY_TOTAL",
        "ATLASSIAN_RETRY_BACKOFF",
        "ATLASSIAN_RETRY_INCLUDE_WRITES",
        "ATLASSIAN_RETRY_IGNORE_RETRY_AFTER",
        "ATLASSIAN_RETRY_MAX_RETRY_AFTER",
    ):
        monkeypatch.delenv(name, raising=False)


def _retrying_session() -> Session:
    session = _new_session()
    session.trust_env = False  # ignore any proxy env in the test runner
    configure_retry(session, service="Test")
    return session


def test_default_retry_after_zero_is_bounded_and_backs_off(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    """#1543: ``Retry-After: 0`` must not loop; 1 try + 3 retries, never 0s apart."""
    _clear_retry_env(monkeypatch)
    server = scripted_server(429, {"Retry-After": "0"})

    response = _retrying_session().get(server.url, timeout=5)

    assert response.status_code == 429
    assert server.hits == DEFAULT_RETRY_TOTAL + 1
    assert recorded_sleeps == [1.0, 2.0, 4.0]


def test_default_large_retry_after_is_capped(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    server = scripted_server(503, {"Retry-After": "3600"})

    _retrying_session().get(server.url, timeout=5)

    assert server.hits == DEFAULT_RETRY_TOTAL + 1
    assert recorded_sleeps == [float(DEFAULT_RETRY_MAX_RETRY_AFTER)] * 3


def test_max_retry_after_env_override(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "1")
    monkeypatch.setenv("ATLASSIAN_RETRY_MAX_RETRY_AFTER", "5")
    server = scripted_server(429, {"Retry-After": "120"})

    _retrying_session().get(server.url, timeout=5)

    assert server.hits == 2
    assert recorded_sleeps == [5.0]


def test_retry_after_within_cap_is_honoured(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "1")
    server = scripted_server(429, {"Retry-After": "7"})

    _retrying_session().get(server.url, timeout=5)

    assert recorded_sleeps == [7.0]


def test_invalid_retry_after_falls_back_to_backoff(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    server = scripted_server(429, {"Retry-After": "soon"})

    response = _retrying_session().get(server.url, timeout=5)

    assert response.status_code == 429
    assert server.hits == DEFAULT_RETRY_TOTAL + 1
    # Plain urllib3 backoff: first retry immediate, then exponential.
    assert recorded_sleeps == [2.0, 4.0]


def test_ignore_retry_after_uses_backoff_only(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    monkeypatch.setenv("ATLASSIAN_RETRY_IGNORE_RETRY_AFTER", "true")
    server = scripted_server(429, {"Retry-After": "3600"})

    _retrying_session().get(server.url, timeout=5)

    assert server.hits == DEFAULT_RETRY_TOTAL + 1
    assert recorded_sleeps == [2.0, 4.0]


def test_unauthorized_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    """A 401 (the #1543 symptom) is returned at once, even with Retry-After."""
    _clear_retry_env(monkeypatch)
    server = scripted_server(401, {"Retry-After": "0"})

    response = _retrying_session().get(server.url, timeout=5)

    assert response.status_code == 401
    assert server.hits == 1
    assert recorded_sleeps == []


def test_writes_not_retried_by_default(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    server = scripted_server(429, {"Retry-After": "1"})

    response = _retrying_session().post(server.url, json={"a": 1}, timeout=5)

    assert response.status_code == 429
    assert server.hits == 1
    assert recorded_sleeps == []


def test_retry_total_zero_disables_retries_on_the_wire(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    _clear_retry_env(monkeypatch)
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "0")
    server = scripted_server(429, {"Retry-After": "0"})

    response = _retrying_session().get(server.url, timeout=5)

    assert response.status_code == 429
    assert server.hits == 1
    assert recorded_sleeps == []


def test_circuit_breaker_counts_one_failure_per_retried_request(
    monkeypatch: pytest.MonkeyPatch, scripted_server, recorded_sleeps
) -> None:
    """Retries run inside adapter.send, so the breaker sees one 429 per call."""
    _clear_retry_env(monkeypatch)
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "2")
    server = scripted_server(429, {"Retry-After": "0"})
    session = _retrying_session()
    configure_circuit_breaker(session, service="Test")

    session.get(server.url, timeout=5)
    assert server.hits == DEFAULT_RETRY_TOTAL + 1
    session.get(server.url, timeout=5)
    with pytest.raises(CircuitBreakerOpenError):
        session.get(server.url, timeout=5)
    assert server.hits == 2 * (DEFAULT_RETRY_TOTAL + 1)


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
    """At 10 rps (burst 10), 15 sends must take >= 0.5s from the first send."""
    monkeypatch.setenv("ATLASSIAN_REQUESTS_PER_SECOND", "10")

    session = Session()
    for adapter in session.adapters.values():
        adapter.send = lambda *a, **kw: MagicMock()  # type: ignore[method-assign]

    configure_rate_limit(session, service="Test")

    adapter = session.adapters["https://"]
    # Timer covers all 15 sends: the bucket holds 10 tokens, so the last 5
    # must wait for refill at 10/s — a >= 0.5s lower bound a slow runner can
    # only lengthen. (Timing only the post-drain sends was flaky: tokens
    # refilled during a slow drain loop, shrinking the measured wait.)
    start = time.monotonic()
    for _ in range(15):
        adapter.send(MagicMock())
    elapsed = time.monotonic() - start

    assert elapsed >= 0.45, f"expected throttling >= 0.45s, got {elapsed:.3f}s"


def test_configure_rate_limit_shares_bucket_across_sessions(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_REQUESTS_PER_SECOND", "5")
    clock = [0.0]

    def advance_clock(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr("mcp_atlassian.utils.http.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("mcp_atlassian.utils.http.time.sleep", advance_clock)

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

    s1.adapters["https://"].send(MagicMock())
    assert clock[0] == pytest.approx(0.2)


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

    from mcp_atlassian.utils.http import _circuit_breakers

    breaker = _circuit_breakers.get("")
    assert breaker is not None
    assert breaker.failures == 2  # last two 429s, no trip


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


def test_circuit_breaker_allows_only_one_half_open_probe(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "1")
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", "0.1")

    session = Session()
    probe_started = threading.Event()
    release_probe = threading.Event()
    call_count = 0
    lock = threading.Lock()

    def fake_send(*args, **kwargs):
        nonlocal call_count
        with lock:
            call_count += 1
            current_call = call_count
        resp = MagicMock()
        if current_call == 1:
            resp.status_code = 429
            return resp

        probe_started.set()
        assert release_probe.wait(timeout=1.0)
        resp.status_code = 200
        return resp

    for adapter in session.adapters.values():
        adapter.send = fake_send  # type: ignore[method-assign]

    configure_circuit_breaker(session, service="Test")
    adapter = session.adapters["https://"]

    adapter.send(MagicMock())  # trips immediately
    time.sleep(0.15)

    results: list[str] = []

    def send_request() -> None:
        try:
            adapter.send(MagicMock())
        except CircuitBreakerOpenError:
            results.append("blocked")
        else:
            results.append("sent")

    probe_thread = threading.Thread(target=send_request)
    probe_thread.start()
    assert probe_started.wait(timeout=1.0)

    blocked_threads = [threading.Thread(target=send_request) for _ in range(3)]
    for thread in blocked_threads:
        thread.start()
    for thread in blocked_threads:
        thread.join()

    release_probe.set()
    probe_thread.join()

    assert results.count("sent") == 1
    assert results.count("blocked") == 3


def test_configure_default_timeout_bounds_request_without_timeout():
    """A direct ``session.get()`` without ``timeout=`` against a server that
    accepts the connection but never answers must time out instead of blocking
    forever (requests' default is no timeout)."""
    import socket

    import requests

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    try:
        session = _new_session()
        configure_default_timeout(session, 0.5, service="Test")

        started = time.monotonic()
        with pytest.raises(requests.exceptions.ReadTimeout):
            session.get(f"http://127.0.0.1:{port}/")
        assert time.monotonic() - started < 5
    finally:
        server.close()


def test_configure_default_timeout_keeps_explicit_timeout():
    session = Session()
    adapter = MagicMock(spec=HTTPAdapter)
    original_send = adapter.send
    session.mount("https://", adapter)
    configure_default_timeout(session, 75, service="Test")

    session.adapters["https://"].send(MagicMock(), timeout=3)
    session.adapters["https://"].send(MagicMock(), timeout=None)
    session.adapters["https://"].send(MagicMock())

    timeouts = [c.kwargs["timeout"] for c in original_send.call_args_list]
    assert timeouts == [3, 75, 75]


def _build_host_session(status_by_host: dict[str, int]) -> tuple[Session, list[str]]:
    """Session whose transport answers by host and records each request URL."""
    session = Session()
    sent: list[str] = []

    def fake_send(request, **kwargs):
        sent.append(request.url)
        resp = Response()
        resp.status_code = next(
            code for prefix, code in status_by_host.items() if prefix in request.url
        )
        resp.url = request.url
        resp.request = request
        resp._content = b"{}"
        return resp

    for adapter in session.adapters.values():
        adapter.send = fake_send  # type: ignore[method-assign]
    return session, sent


def test_circuit_breaker_state_is_per_upstream(monkeypatch: pytest.MonkeyPatch):
    """Tripping the breaker for one upstream leaves other upstreams usable."""
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "3")
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", "60")
    statuses = {
        "a.example.test": 503,
        "b.example.test": 200,
        "/ex/jira/site-a/": 429,
        "/ex/jira/site-b/": 200,
    }
    session_a, _ = _build_host_session(statuses)
    session_b, sent_b = _build_host_session(statuses)
    configure_circuit_breaker(session_a, service="Jira")
    configure_circuit_breaker(session_b, service="Confluence")

    for _ in range(3):
        assert (
            session_a.get("https://a.example.test/rest/api/2/myself").status_code == 503
        )
    with pytest.raises(CircuitBreakerOpenError):
        session_a.get("https://a.example.test/rest/api/2/myself")

    # Another upstream, through another session and through the tripped one.
    assert (
        session_b.get("https://b.example.test/wiki/rest/api/space").status_code == 200
    )
    assert session_a.get("https://b.example.test/rest/api/2/myself").status_code == 200
    assert len(sent_b) == 1

    # Cloud OAuth sites share the api.atlassian.com host but not breaker state.
    gateway = "https://api.atlassian.com/ex/jira"
    for _ in range(3):
        session_a.get(f"{gateway}/site-a/rest/api/3/myself")
    with pytest.raises(CircuitBreakerOpenError):
        session_a.get(f"{gateway}/site-a/rest/api/3/myself")
    assert session_a.get(f"{gateway}/site-b/rest/api/3/myself").status_code == 200


def test_circuit_breaker_registry_stays_bounded(monkeypatch: pytest.MonkeyPatch):
    """Failures on many sites do not grow the registry past its limit."""
    from mcp_atlassian.utils import http

    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "3")
    session, _ = _build_host_session({"example.test": 503})
    configure_circuit_breaker(session, service="Jira")

    for n in range(1100):
        session.get(f"https://site{n}.example.test/rest/api/2/myself")

    assert len(http._circuit_breakers) <= http.MAX_SITE_ENTRIES


def test_circuit_breaker_in_use_is_not_evicted(monkeypatch: pytest.MonkeyPatch):
    """A breaker with a request in flight keeps its failure record."""
    from mcp_atlassian.utils import http

    monkeypatch.setattr(http, "MAX_SITE_ENTRIES", 2)

    def new_breaker() -> http._CircuitBreaker:
        return http._CircuitBreaker(3, 60)

    with http._circuit_breakers.use("https://busy.test:443", new_breaker) as busy:
        busy.on_response(503, probe=False)
        for n in range(5):
            with http._circuit_breakers.use(f"https://s{n}.test:443", new_breaker):
                pass

        assert http._circuit_breakers.get("https://busy.test:443") is busy
        assert busy.failures == 1
        assert len(http._circuit_breakers) <= 3


def test_circuit_breaker_registry_shrinks_after_saturation(
    monkeypatch: pytest.MonkeyPatch,
):
    """While every entry is in use the registry may exceed the limit; once
    they are returned it drops back to the limit."""
    from contextlib import ExitStack

    from mcp_atlassian.utils import http

    monkeypatch.setattr(http, "MAX_SITE_ENTRIES", 2)
    with ExitStack() as stack:
        for n in range(5):
            stack.enter_context(
                http._circuit_breakers.use(
                    f"https://s{n}.test:443", lambda: http._CircuitBreaker(3, 60)
                )
            )
        assert len(http._circuit_breakers) == 5  # all in use: nothing evictable

    assert len(http._circuit_breakers) <= 2


def _blocking_host_session(
    blocked_host: str, release: threading.Event
) -> tuple[Session, threading.Event]:
    """Session whose transport blocks on ``blocked_host`` until released."""
    session = Session()
    entered = threading.Event()

    def fake_send(request, **kwargs):
        if blocked_host in request.url:
            entered.set()
            release.wait(5)
        resp = Response()
        resp.status_code = 200
        resp.url = request.url
        resp.request = request
        resp._content = b"{}"
        return resp

    for adapter in session.adapters.values():
        adapter.send = fake_send  # type: ignore[method-assign]
    return session, entered


def _in_thread(call) -> threading.Event:
    """Run ``call`` in a daemon thread; the event is set when it returns."""
    done = threading.Event()

    def run() -> None:
        call()
        done.set()

    threading.Thread(target=run, daemon=True).start()
    return done


def test_concurrency_cap_is_per_upstream(monkeypatch: pytest.MonkeyPatch):
    """A slow site holding its permits does not block requests to another site."""
    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "1")
    release = threading.Event()
    slow, entered = _blocking_host_session("slow-a.example.test", release)
    other, _ = _blocking_host_session("slow-a.example.test", release)
    configure_concurrency(slow, service="Confluence")
    configure_concurrency(other, service="Jira")

    holder = threading.Thread(
        target=lambda: slow.get("https://slow-a.example.test/wiki/rest/api/space")
    )
    holder.start()
    try:
        assert entered.wait(5)
        done = _in_thread(
            lambda: other.get("https://victim-b.example.test/rest/api/2/myself")
        )
        assert done.wait(1), "site B waited for site A's permit"
    finally:
        release.set()
        holder.join(5)


def test_concurrency_cap_still_applies_within_one_upstream(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "1")
    release = threading.Event()
    session, entered = _blocking_host_session("site.example.test", release)
    configure_concurrency(session, service="Jira")
    url = "https://site.example.test/rest/api/2/myself"
    holder = threading.Thread(target=lambda: session.get(url))
    holder.start()
    try:
        assert entered.wait(5)
        done = _in_thread(lambda: session.get(url))
        assert not done.wait(0.3)
    finally:
        release.set()
        holder.join(5)


def test_call_waiting_for_a_concurrency_permit_stops_when_aborted(
    monkeypatch: pytest.MonkeyPatch,
):
    """A stopped call leaves the permit queue instead of waiting for a stuck one."""
    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "1")
    release = threading.Event()
    session, entered = _blocking_host_session("site.example.test", release)
    configure_concurrency(session, service="Jira")
    url = "https://site.example.test/rest/api/2/myself"
    holder = threading.Thread(target=lambda: session.get(url))
    holder.start()
    budget = CallBudget()
    raised: list[BaseException] = []

    def waiting_call() -> None:
        try:
            budget.run(lambda: session.get(url))
        except UpstreamCallAborted as exc:
            raised.append(exc)

    try:
        assert entered.wait(5)
        done = _in_thread(waiting_call)
        assert not done.wait(0.2), "the second call did not wait for the permit"
        budget.abort()
        assert done.wait(2), "the aborted call kept waiting for the permit"
        assert len(raised) == 1
    finally:
        release.set()
        holder.join(5)


def test_rate_limit_is_per_upstream(monkeypatch: pytest.MonkeyPatch):
    """Spending one site's tokens does not make another site wait."""
    monkeypatch.setenv("ATLASSIAN_REQUESTS_PER_SECOND", "1")
    clock = [0.0]
    monkeypatch.setattr("mcp_atlassian.utils.http.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "mcp_atlassian.utils.http.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    session, _ = _build_host_session({"example.test": 200})
    configure_rate_limit(session, service="Jira")

    session.get("https://a.example.test/rest/api/2/myself")
    session.get("https://b.example.test/rest/api/2/myself")
    assert clock[0] == 0.0
    session.get("https://a.example.test/rest/api/2/myself")
    assert clock[0] == pytest.approx(1.0)


def test_circuit_breaker_is_per_credential_on_one_site(
    monkeypatch: pytest.MonkeyPatch,
):
    """One user's 429s on a site do not block another user of that site."""
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "2")
    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_COOLDOWN", "60")
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "0")
    url = "https://site.example.net/rest/api/2/myself"
    user_a, _ = _build_host_session({"site.example.net": 429})
    user_b, sent_b = _build_host_session({"site.example.net": 200})
    user_a.headers["Authorization"] = "Bearer dummy-a"
    user_b.headers["Authorization"] = "Bearer dummy-b"
    for session in (user_a, user_b):
        configure_circuit_breaker(session, service="Jira")

    for _ in range(2):
        assert user_a.get(url).status_code == 429
    with pytest.raises(CircuitBreakerOpenError):
        user_a.get(url)

    assert (
        user_b.get("https://SITE.example.net:443/rest/api/2/myself").status_code == 200
    )
    assert len(sent_b) == 1


def test_circuit_breaker_credential_keys_stay_bounded_and_hide_secrets(
    monkeypatch: pytest.MonkeyPatch,
):
    """Many credentials on one site keep the registry bounded, and its keys
    carry a fingerprint, never the credential."""
    from mcp_atlassian.utils import http

    monkeypatch.setenv("ATLASSIAN_CIRCUIT_BREAKER_THRESHOLD", "3")
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "0")
    monkeypatch.setattr(http, "MAX_SITE_ENTRIES", 4)
    session, _ = _build_host_session({"site.example.net": 503})
    configure_circuit_breaker(session, service="Jira")

    for n in range(20):
        session.get(
            "https://site.example.net/rest/api/2/myself",
            headers={"Authorization": f"Bearer secret-token-{n}"},
        )

    keys = list(http._circuit_breakers._entries)
    assert len(keys) <= 4
    assert all("secret-token" not in key for key in keys)
    assert all(key.startswith("https://site.example.net:443#") for key in keys)


class _KeepAliveServer:
    """Loopback HTTP/1.1 server that keeps connections open between requests.

    Request ``n`` (counted across connections) sets ``arrived[n]`` and is
    answered once ``respond[n]`` is set. ``conns`` lists the connection number
    each request came in on.
    """

    def __init__(self, requests: int) -> None:
        self.arrived = [threading.Event() for _ in range(requests)]
        self.respond = [threading.Event() for _ in range(requests)]
        self.conns: list[int] = []
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.url = f"http://127.0.0.1:{self._sock.getsockname()[1]}/"
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        number = 0
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(
                target=self._serve, args=(conn, number), daemon=True
            ).start()
            number += 1

    def _serve(self, conn: socket.socket, number: int) -> None:
        with conn:
            buffer = b""
            while True:
                try:
                    chunk = conn.recv(65536)
                except OSError:
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\r\n\r\n" in buffer:
                    _, buffer = buffer.split(b"\r\n\r\n", 1)
                    with self._lock:
                        index = len(self.conns)
                        self.conns.append(number)
                    self.arrived[index].set()
                    self.respond[index].wait(5)
                    try:
                        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
                    except OSError:
                        return

    def close(self) -> None:
        for event in self.respond:
            event.set()
        self._sock.close()


def test_abort_leaves_a_connection_another_call_took_over_alone(
    monkeypatch: pytest.MonkeyPatch,
):
    """Stopping one call does not break a call that reuses its pooled connection."""
    server = _KeepAliveServer(requests=2)
    session = Session()
    # One pooled connection, so the second call waits for the first one's.
    session.mount("http://", HTTPAdapter(pool_maxsize=1, pool_block=True))
    configure_default_timeout(session, 10)
    results: dict[str, object] = {}

    def call(name: str) -> None:
        budget = CallBudget()
        if name == "first":
            results["budget"] = budget
        try:
            results[name] = budget.run(lambda: session.get(server.url).status_code)
        except Exception as exc:  # noqa: BLE001 - checked below
            results[name] = exc

    # The first call hands its connection back (untrack) and the second call
    # takes it from the pool (track); each step is recorded as an event.
    handing_back = threading.Event()
    taken_over = threading.Event()
    handed: list[object] = []
    taken: list[object] = []
    real_track = CallBudget.track
    real_untrack = CallBudget.untrack

    def track(self: CallBudget, conn: object) -> None:
        real_track(self, conn)
        if self is not results.get("budget"):
            taken.append(conn)
            taken_over.set()

    def untrack(self: CallBudget, conn: object) -> None:
        if self is results.get("budget"):
            handed.append(conn)
            handing_back.set()
        real_untrack(self, conn)

    monkeypatch.setattr(CallBudget, "track", track)
    monkeypatch.setattr(CallBudget, "untrack", untrack)

    first = threading.Thread(target=call, args=("first",))
    second = threading.Thread(target=call, args=("second",))
    try:
        first.start()
        assert server.arrived[0].wait(5)
        second.start()
        real_shutdown = socket.socket.shutdown

        def shutdown_during_handover(sock: socket.socket, how: int) -> None:
            # Let the first call finish while the abort is under way, so it
            # tries to hand its connection back before the socket is shut down.
            server.respond[0].set()
            results["handing_back"] = handing_back.wait(5)
            # The hand-back must wait for the abort. Without that, the second
            # call takes the connection here; the short wait only gives a
            # broken hand-back the time to show up.
            results["taken_during_abort"] = taken_over.wait(0.5)
            real_shutdown(sock, how)
            server.respond[1].set()

        monkeypatch.setattr(socket.socket, "shutdown", shutdown_during_handover)
        budget = results["budget"]
        assert isinstance(budget, CallBudget)
        budget.abort()
        first.join(5)
        second.join(5)
    finally:
        server.close()
    assert results["handing_back"] is True
    assert results["taken_during_abort"] is False
    # The second call got the very connection the first one handed back,
    # found its socket shut down, reopened it and got its answer.
    assert taken_over.is_set()
    assert handed and taken and taken[0] is handed[0]
    assert server.arrived[1].is_set()
    assert server.conns == [0, 1]
    assert results["second"] == 200


@pytest.fixture
def _dns_slots_taken() -> Iterator[None]:
    """Hold every bounded DNS slot, as lookups for header hosts would."""
    taken = 0
    try:
        while http_module._dns_slots.acquire(blocking=False):
            taken += 1
        yield
    finally:
        for _ in range(taken):
            http_module._dns_slots.release()


def _gai_public(host: str, port: int, *args: object, **kwargs: object) -> list:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


class _ConnectingSock:
    def __init__(self, *args: object) -> None:
        self.addr: object = None

    def setsockopt(self, *args: object) -> None:
        pass

    def settimeout(self, *args: object) -> None:
        pass

    def bind(self, *args: object) -> None:
        pass

    def connect(self, sa: object) -> None:
        self.addr = sa

    def close(self) -> None:
        pass


class TestDnsSlotsServeHeaderHostsOnly:
    """Lookups for calls with a deadline cannot hold up calls without one."""

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "corp.example.com")
        monkeypatch.setattr(socket, "getaddrinfo", _gai_public)
        monkeypatch.setattr(socket, "socket", _ConnectingSock)

    @pytest.mark.usefixtures("_dns_slots_taken")
    @pytest.mark.parametrize(
        "host",
        ["jira.example.com", "wiki.corp.example.com", "api.atlassian.com"],
        ids=["configured", "allowlisted", "cloud-oauth-gateway"],
    )
    def test_call_without_deadline_resolves_while_slots_are_full(
        self, host: str
    ) -> None:
        sock = CallBudget().run(lambda: _pinned_create_connection((host, 443), 0.5))
        assert sock.addr == ("93.184.216.34", 443)

    @pytest.mark.usefixtures("_dns_slots_taken")
    @pytest.mark.parametrize("host", ["other.example.net", "jira.example.com"])
    def test_call_with_deadline_waits_for_a_slot(self, host: str) -> None:
        budget = CallBudget(deadline=time.monotonic() + 30)
        with pytest.raises(TimeoutError):
            budget.run(lambda: _pinned_create_connection((host, 443), 0.2))

    def test_call_with_deadline_resolves_with_a_free_slot(self) -> None:
        budget = CallBudget(deadline=time.monotonic() + 30)
        sock = budget.run(
            lambda: _pinned_create_connection(("other.example.net", 443), 0.5)
        )
        assert sock.addr == ("93.184.216.34", 443)


def test_abort_shuts_down_the_socket_behind_a_proxy_tls_transport() -> None:
    """A tunnelled HTTPS connection wraps its socket in urllib3's SSLTransport."""
    inner, peer = socket.socketpair()
    try:
        transport = object.__new__(SSLTransport)
        transport.socket = inner  # type: ignore[assignment]
        conn = MagicMock(spec_set=["sock"])
        conn.sock = transport
        budget = CallBudget()
        budget.track(conn)

        budget.abort()

        peer.settimeout(2)
        assert peer.recv(1) == b""
    finally:
        inner.close()
        peer.close()


# --- decoded response size limit ---------------------------------------------
#
# A loopback server replays scripted responses through a real Session with the
# real retry and send wrappers, so urllib3's own retries and redirects run.

_CAP = 64 * 1024
_SLACK = 64 * 1024


def _gzip(data: bytes, layers: int = 1) -> bytes:
    import gzip

    for _ in range(layers):
        data = gzip.compress(data)
    return data


class _ReplayServer:
    """Serve ``(status, headers, body)`` responses in order, one per request."""

    def __init__(self, responses: list[tuple[int, dict[str, str], bytes]]) -> None:
        script = list(responses)
        self.paths: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                outer.paths.append(self.path)
                status, headers, body = script.pop(0)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def body_meter(monkeypatch: pytest.MonkeyPatch) -> "_Meter":
    """Record, per urllib3 response, the larger of raw bytes read and decoded
    bytes produced: the most body memory that response could have held."""
    from urllib3.response import HTTPResponse

    sizes: dict[int, list[int]] = {}
    order: list[int] = []
    real_raw_read = getattr(HTTPResponse, "_raw_read")  # noqa: B009
    real_decode = getattr(HTTPResponse, "_decode")  # noqa: B009

    def entry(response: object) -> list[int]:
        key = id(response)
        if key not in sizes:
            sizes[key] = [0, 0]
            order.append(key)
        return sizes[key]

    def raw_read(self, *args, **kwargs):
        data = real_raw_read(self, *args, **kwargs)
        entry(self)[0] += len(data or b"")
        return data

    def decode(self, *args, **kwargs):
        data = real_decode(self, *args, **kwargs)
        entry(self)[1] += len(data or b"")
        return data

    monkeypatch.setattr(HTTPResponse, "_raw_read", raw_read)
    monkeypatch.setattr(HTTPResponse, "_decode", decode)
    return _Meter(sizes, order)


class _Meter:
    def __init__(self, sizes: dict[int, list[int]], order: list[int]) -> None:
        self._sizes = sizes
        self._order = order

    def __getitem__(self, index: int) -> int:
        return max(self._sizes[self._order[index]])


def _capped_session(
    monkeypatch: pytest.MonkeyPatch, server_url: str, retries: int = 0
) -> Session:
    """A session set up like a Jira client's: pinning adapter, then the
    retry and send wrappers. The loopback server is the configured site."""
    from mcp_atlassian.utils.ssrf_adapter import mount_ssrf_pinning

    monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", str(_CAP))
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", str(retries))
    monkeypatch.setenv("ATLASSIAN_RETRY_BACKOFF", "0.01")
    monkeypatch.setenv("JIRA_URL", server_url)
    session = Session()
    mount_ssrf_pinning(session, server_url)
    configure_retry(session, service="Jira")
    configure_default_timeout(session, 10, service="Jira")
    return session


@pytest.fixture
def scripted():
    servers: list[_ReplayServer] = []

    def start(responses):
        server = _ReplayServer(responses)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


@pytest.mark.security_regression
@pytest.mark.parametrize(
    ("encoding", "layers"), [("gzip", 1), ("gzip, gzip", 2)], ids=["gzip", "gzip2"]
)
def test_compressed_body_past_the_limit_is_refused(
    monkeypatch, scripted, body_meter, encoding, layers
):
    body = b"[" + b"0," * (8 * _CAP) + b"0]"
    server = scripted([(200, {"Content-Encoding": encoding}, _gzip(body, layers))])
    session = _capped_session(monkeypatch, server.url)
    with pytest.raises(requests.RequestException, match="limit"):
        session.get(f"{server.url}/rest/api/2/search")
    assert body_meter[0] <= _CAP + _SLACK


@pytest.mark.security_regression
def test_plain_body_past_the_limit_is_refused(monkeypatch, scripted, body_meter):
    """A body that declares its length is refused once the bytes read pass
    the limit, the same as one that does not."""
    server = scripted([(200, {}, b"x" * (8 * _CAP))])
    session = _capped_session(monkeypatch, server.url)
    with pytest.raises(requests.RequestException, match="limit"):
        session.get(f"{server.url}/rest/api/2/myself")
    assert body_meter[0] <= _CAP + _SLACK


@pytest.mark.security_regression
def test_redirect_body_past_the_limit_is_refused(monkeypatch, scripted, body_meter):
    """Redirect bodies are read even for a streamed request, so they are
    limited too."""
    redirect = (
        302,
        {"Location": "/next", "Content-Encoding": "gzip"},
        _gzip(b"x" * (8 * _CAP)),
    )
    server = scripted([redirect, (200, {}, b"{}")])
    session = _capped_session(monkeypatch, server.url)
    with pytest.raises(requests.RequestException, match="limit"):
        session.get(f"{server.url}/start", stream=True)
    assert body_meter[0] <= _CAP + _SLACK


@pytest.mark.security_regression
def test_retried_response_body_is_limited(monkeypatch, scripted, body_meter):
    """urllib3 reads and drops the body of a response it retries; that read
    is limited as well, and the retry still goes ahead."""
    big = b"x" * (8 * _CAP)
    headers = {"Retry-After": "0"}
    server = scripted([(503, headers, big), (200, {}, b'{"ok": true}')])
    session = _capped_session(monkeypatch, server.url, retries=1)
    response = session.get(f"{server.url}/rest/api/2/myself")
    assert response.json() == {"ok": True}
    assert len(server.paths) == 2
    assert body_meter[0] <= _CAP + _SLACK


def test_body_within_the_limit_is_unchanged(monkeypatch, scripted):
    payload = b'{"issues": [' + b'{"id": 1},' * 100 + b'{"id": 2}]}'
    server = scripted([(200, {"Content-Encoding": "gzip"}, _gzip(payload))])
    session = _capped_session(monkeypatch, server.url)
    response = session.get(f"{server.url}/rest/api/2/search")
    assert response.content == payload
    assert response.json()["issues"][-1] == {"id": 2}


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_streamed_download_is_not_limited(monkeypatch, scripted, encoding):
    """A streamed download that declares a length past the limit is read in
    full by its caller, which applies the attachment size limit instead."""
    body = b"x" * (4 * _CAP)
    headers: dict[str, str] = {}
    sent = body
    if encoding == "gzip":
        headers["Content-Encoding"] = "gzip"
        sent = _gzip(body)
    headers["Content-Length"] = str(len(sent))
    server = scripted([(200, headers, sent)])
    session = _capped_session(monkeypatch, server.url)
    response = session.get(f"{server.url}/secure/attachment/1/a.bin", stream=True)
    assert b"".join(response.iter_content(8192)) == body


def test_response_limit_can_be_turned_off(monkeypatch, scripted):
    server = scripted([(200, {}, b"x" * (2 * _CAP))])
    session = _capped_session(monkeypatch, server.url)
    monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", "0")
    assert len(session.get(f"{server.url}/big").content) == 2 * _CAP


@pytest.mark.security_regression
def test_jira_fetcher_refuses_a_compressed_identity_past_the_limit(
    monkeypatch, scripted, body_meter
):
    """Through the real JiraFetcher session (pinning adapter and all wrappers),
    a small gzip reply that decodes past the limit fails the call."""
    from mcp_atlassian.jira import JiraFetcher
    from mcp_atlassian.jira.config import JiraConfig

    body = b'{"accountId": "' + b"a" * (8 * _CAP) + b'"}'
    reply = (200, {"Content-Encoding": "gzip", "Content-Type": "application/json"})
    server = scripted([(*reply, _gzip(body))])
    monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", str(_CAP))
    monkeypatch.setenv("ATLASSIAN_RETRY_TOTAL", "0")
    monkeypatch.setenv("JIRA_URL", server.url)
    fetcher = JiraFetcher(
        config=JiraConfig(
            url=server.url,
            auth_type="pat",
            personal_token="dummy-token",  # noqa: S106
        )
    )
    with pytest.raises(Exception, match="limit"):
        fetcher.get_current_user_account_id()
    assert body_meter[0] <= _CAP + _SLACK


# Decoder memory: a decoder may hold input it has not turned into output yet.
# These bodies decode to nothing, so only the memory held on the way counts.


def _empty_deflate_blocks(count: int, *, zlib_wrapped: bool = True) -> bytes:
    """A valid deflate stream of ``count`` empty stored blocks: no output."""
    blocks = b"\x00\x00\x00\xff\xff" * count + b"\x01\x00\x00\xff\xff"
    if zlib_wrapped:
        return b"\x78\x9c" + blocks + b"\x00\x00\x00\x01"
    return blocks


def _empty_gzip_blocks_compressed(megabytes: int) -> bytes:
    """gzip of a gzip member made of empty stored blocks, ``megabytes`` long.

    Built from one compressed 1 MiB segment repeated, so the test does not
    compress the whole member. The outer stream has no trailer; it ends early,
    which gzip decoding accepts.
    """
    import zlib

    segment = b"\x00\x00\x00\xff\xff" * (1024 * 1024 // 5)
    member_head = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
    deflate = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    head = deflate.compress(member_head) + deflate.flush(zlib.Z_FULL_FLUSH)
    body = deflate.compress(segment) + deflate.flush(zlib.Z_FULL_FLUSH)
    outer_head = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
    return outer_head + head + body * megabytes


@contextmanager
def _peak_memory():
    import tracemalloc

    result = {}
    tracemalloc.start()
    try:
        yield result
    finally:
        result["peak"] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()


@pytest.mark.security_regression
@pytest.mark.parametrize(
    "encoding", ["deflate", "deflate, gzip"], ids=["deflate", "deflate-gzip"]
)
def test_deflate_body_without_output_keeps_little_in_memory(
    monkeypatch, scripted, encoding
):
    """urllib3 keeps every deflate byte until the first decoded byte, so a
    stream of empty blocks would be held in full, past the limit."""
    wire = _empty_deflate_blocks(800_000)  # 4 MB, decodes to nothing
    if encoding == "deflate, gzip":
        wire = _gzip(wire)
    server = scripted([(200, {"Content-Encoding": encoding}, wire)])
    session = _capped_session(monkeypatch, server.url)
    # A limit far above the body, so only the decoder's own memory is measured.
    monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", str(1 << 30))
    with _peak_memory() as memory:
        response = session.get(f"{server.url}/rest/api/2/search")
        assert response.content == b""
    assert memory["peak"] < 8 * _CAP


@pytest.mark.security_regression
def test_middle_decoding_step_keeps_little_in_memory(monkeypatch, scripted):
    """With three gzip layers, urllib3 feeds the middle layer faster than its
    limited output lets it consume, so its unread input piles up."""
    inner = _empty_gzip_blocks_compressed(200)
    server = scripted([(200, {"Content-Encoding": "gzip, gzip, gzip"}, _gzip(inner))])
    session = _capped_session(monkeypatch, server.url)
    monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", str(1 << 30))
    with _peak_memory() as memory:
        response = session.get(f"{server.url}/rest/api/2/search")
        assert response.content == b""
    assert memory["peak"] < 4 * _CAP


def test_deflate_without_zlib_header_still_decodes(monkeypatch, scripted):
    payload = b'{"values": [' + b'{"id": 1},' * 50 + b'{"id": 2}]}'
    import zlib

    raw = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
    wire = raw.compress(payload) + raw.flush()
    server = scripted(
        [
            (200, {"Content-Encoding": "deflate"}, wire),
            (200, {"Content-Encoding": "deflate"}, zlib.compress(payload)),
        ]
    )
    session = _capped_session(monkeypatch, server.url)
    assert session.get(f"{server.url}/a").content == payload
    assert session.get(f"{server.url}/b").content == payload


def _single_connection(session: Session) -> None:
    """Give the session one pooled connection and wait for it when busy, so a
    connection that is never returned blocks the next request."""
    for adapter in session.adapters.values():
        assert isinstance(adapter, HTTPAdapter)
        adapter.init_poolmanager(1, 1, block=True)


def _finishes(call: Callable[[], object], seconds: float = 10.0) -> object:
    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            outcome["value"] = call()
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "request waited for a connection never returned"
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome["value"]


@pytest.mark.security_regression
def test_refused_body_returns_its_connection_to_the_pool(monkeypatch, scripted):
    """The refused body is cut off mid-transfer; its connection is closed and
    handed back, so the next request does not wait for it."""
    big = (200, {}, b"x" * (8 * _CAP))
    server = scripted([big, (200, {}, b'{"ok": true}')])
    session = _capped_session(monkeypatch, server.url)
    _single_connection(session)
    with pytest.raises(requests.RequestException, match="limit"):
        _finishes(lambda: session.get(f"{server.url}/rest/api/2/search"))
    response = _finishes(lambda: session.get(f"{server.url}/rest/api/2/myself"))
    assert response.json() == {"ok": True}


@pytest.mark.security_regression
@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_refused_retry_body_returns_its_connection_to_the_pool(
    monkeypatch, scripted, status
):
    big = (status, {"Retry-After": "0"}, b"x" * (8 * _CAP))
    server = scripted([big, (200, {}, b'{"ok": true}')])
    session = _capped_session(monkeypatch, server.url, retries=1)
    _single_connection(session)
    response = _finishes(lambda: session.get(f"{server.url}/rest/api/2/myself"))
    assert response.json() == {"ok": True}
    assert len(server.paths) == 2


_NESTED = {"Content-Encoding": "gzip, gzip, gzip"}


@pytest.mark.security_regression
def test_nested_body_that_decodes_to_nothing_stops_at_the_deadline(
    monkeypatch, scripted
):
    """A 1.6 KB body whose middle step expands to 200 MB and decodes to
    nothing is worked through only until the call's deadline."""
    server = scripted([(200, _NESTED, _gzip(_empty_gzip_blocks_compressed(200)))])
    session = _capped_session(monkeypatch, server.url)
    budget = CallBudget(deadline=time.monotonic() + 0.1)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        budget.run(lambda: session.get(f"{server.url}/rest/api/2/search"))
    assert time.monotonic() - started < 0.5


def _gzip_flushed(data: bytes, level: int, every: int) -> bytes:
    """gzip with a sync flush every ``every`` bytes, as a streaming encoder
    does: valid, and larger than ``data`` when flushed often."""
    import zlib

    obj = zlib.compressobj(level, zlib.DEFLATED, 31)
    parts = []
    for i in range(0, len(data), every):
        parts.append(obj.compress(data[i : i + every]))
        parts.append(obj.flush(zlib.Z_SYNC_FLUSH))
    parts.append(obj.flush())
    return b"".join(parts)


def test_nested_body_with_a_larger_inner_step_is_decoded(monkeypatch, scripted):
    """An inner step may be larger than the body it decodes to (here a gzip
    flushed every 4 bytes, about 2x); only the decoded size counts."""
    payload = b'{"data":"' + b"a" * (_CAP - 11) + b'"}'
    inner = _gzip_flushed(payload, level=6, every=4)
    assert len(inner) > _CAP + _SLACK
    server = scripted([(200, {"Content-Encoding": "gzip, gzip"}, _gzip(inner))])
    session = _capped_session(monkeypatch, server.url)
    assert session.get(f"{server.url}/rest/api/2/search").content == payload


def _slow_to_decode_session(monkeypatch, scripted):
    """A body that takes seconds of decoding with no output, under a limit
    high enough that only the call's deadline or abort can stop it."""
    slow = (200, _NESTED, _gzip(_empty_gzip_blocks_compressed(400)))
    server = scripted([slow, (200, {}, b'{"ok": true}')])
    session = _capped_session(monkeypatch, server.url)
    monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", str(1 << 30))
    _single_connection(session)
    return server, session


@pytest.mark.security_regression
def test_decoding_stops_when_the_call_is_aborted(monkeypatch, scripted):
    server, session = _slow_to_decode_session(monkeypatch, scripted)
    budget = CallBudget()
    outcome: dict[str, BaseException] = {}

    def call() -> None:
        try:
            budget.run(lambda: session.get(f"{server.url}/rest/api/2/search"))
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            outcome["error"] = exc

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.paths and time.monotonic() < deadline:
        time.sleep(0.005)
    time.sleep(0.05)
    budget.abort()
    thread.join(0.5)
    assert not thread.is_alive(), "decoding went on after the call was aborted"
    assert isinstance(outcome.get("error"), UpstreamCallAborted)
    # The connection went back to the one-slot pool.
    response = _finishes(lambda: session.get(f"{server.url}/rest/api/2/myself"))
    assert response.json() == {"ok": True}


@pytest.mark.security_regression
def test_decoding_stops_at_the_call_deadline(monkeypatch, scripted):
    server, session = _slow_to_decode_session(monkeypatch, scripted)
    budget = CallBudget(deadline=time.monotonic() + 0.2)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        budget.run(lambda: session.get(f"{server.url}/rest/api/2/search"))
    assert time.monotonic() - started < 1.0


class _UnboundedBrotli:
    """A Brotli without ``output_buffer_limit`` (older than 1.2.0)."""

    class Decompressor:
        def process(self, data: bytes) -> bytes:
            return data


@pytest.fixture
def unbounded_brotli(monkeypatch):
    import urllib3.response as urllib3_response
    from urllib3.response import HTTPResponse

    from mcp_atlassian.utils import http as http_module

    monkeypatch.setattr(urllib3_response, "brotli", _UnboundedBrotli, raising=False)
    monkeypatch.setattr(
        HTTPResponse, "CONTENT_DECODERS", [*HTTPResponse.CONTENT_DECODERS, "br"]
    )
    http_module._brotli_output_is_bounded.cache_clear()
    yield
    http_module._brotli_output_is_bounded.cache_clear()


class _HeaderRecorder(_ReplayServer):
    def __init__(self, responses):
        super().__init__(responses)
        self.accept_encoding: list[str | None] = []
        recorder = self
        handler = self._server.RequestHandlerClass
        real = handler.do_GET

        def do_get(handler_self) -> None:
            recorder.accept_encoding.append(handler_self.headers.get("Accept-Encoding"))
            real(handler_self)

        handler.do_GET = do_get


@pytest.mark.parametrize(
    "sent", ["gzip, deflate, br", "br", "gzip;q=1.0, br;q=0.9, deflate"]
)
def test_br_is_not_asked_for_when_brotli_cannot_limit_its_output(
    monkeypatch, unbounded_brotli, sent
):
    """With an old Brotli a br body would be refused, so the request does not
    offer br and a server sends a coding that can be decoded."""
    server = _HeaderRecorder([(200, {}, b'{"ok": true}')])
    try:
        session = _capped_session(monkeypatch, server.url)
        response = session.get(f"{server.url}/x", headers={"Accept-Encoding": sent})
        assert response.json() == {"ok": True}
        offered = server.accept_encoding[0] or ""
        assert "br" not in [c.split(";")[0].strip() for c in offered.split(",")]
        assert offered
    finally:
        server.close()


def test_unasked_br_body_is_still_refused_with_an_old_brotli(
    monkeypatch, scripted, unbounded_brotli
):
    body = bytes.fromhex("0b05807b226f6b223a747275657d03")
    server = scripted([(200, {"Content-Encoding": "br"}, body)])
    session = _capped_session(monkeypatch, server.url)
    with pytest.raises(requests.RequestException, match="Brotli"):
        session.get(f"{server.url}/x")


class _DripServer:
    """Serve one response whose body arrives in ``pieces`` slow writes."""

    def __init__(self, headers: dict[str, str], pieces: list[bytes], delay: float):
        chunked = headers.get("Transfer-Encoding") == "chunked"
        self.sent = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                for name, value in headers.items():
                    self.send_header(name, value)
                if not chunked:
                    total = sum(len(p) for p in pieces)
                    self.send_header("Content-Length", str(total))
                self.end_headers()
                try:
                    for piece in pieces:
                        time.sleep(delay)
                        if chunked:
                            piece = b"%x\r\n%s\r\n" % (len(piece), piece)
                        self.wfile.write(piece)
                        self.wfile.flush()
                        outer.sent += 1
                    if chunked:
                        self.wfile.write(b"0\r\n\r\n")
                except OSError:
                    pass

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.mark.security_regression
@pytest.mark.parametrize("framing", ["length", "chunked"])
def test_body_still_arriving_after_the_deadline_is_not_read_on(
    monkeypatch, body_meter, framing
):
    """Once the deadline passes, the read stops at the next piece instead of
    reading the rest of the body before reporting it."""
    import gzip

    wire = gzip.compress(b"a" * 1_000_000, compresslevel=0)  # 123 pieces
    pieces = [wire[i : i + 8192] for i in range(0, len(wire), 8192)]
    headers = {"Content-Encoding": "gzip"}
    if framing == "chunked":
        headers["Transfer-Encoding"] = "chunked"
    server = _DripServer(headers, pieces, delay=0.01)
    try:
        session = _capped_session(monkeypatch, server.url)
        monkeypatch.setenv("ATLASSIAN_MAX_RESPONSE_BYTES", str(1 << 30))
        budget = CallBudget(deadline=time.monotonic() + 0.2)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            budget.run(lambda: session.get(f"{server.url}/rest/api/2/search"))
        assert time.monotonic() - started < 0.6
        assert server.sent < len(pieces) // 2
        assert body_meter[0] < len(wire) // 2
    finally:
        server.close()
