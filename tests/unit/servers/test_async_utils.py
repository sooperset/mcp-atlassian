"""Tests for server async utility helpers."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from threading import Lock

import anyio
import pytest

from src.mcp_atlassian.servers.async_utils import (
    DEFAULT_FETCHER_MAX_WORKERS,
    FETCHER_MAX_WORKERS_ENV,
    get_fetcher_max_workers,
    run_fetcher_call,
)
from tests.utils.timing import budget


@pytest.fixture(autouse=True)
def reset_jira_fetcher_workers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset the Jira worker limit env var between tests."""
    monkeypatch.delenv(FETCHER_MAX_WORKERS_ENV, raising=False)
    yield
    monkeypatch.delenv(FETCHER_MAX_WORKERS_ENV, raising=False)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, DEFAULT_FETCHER_MAX_WORKERS),
        ("1", 1),
        ("8", 8),
        ("16", 16),
        ("0", DEFAULT_FETCHER_MAX_WORKERS),
        ("-1", DEFAULT_FETCHER_MAX_WORKERS),
        ("abc", DEFAULT_FETCHER_MAX_WORKERS),
        ("", DEFAULT_FETCHER_MAX_WORKERS),
    ],
)
def test_get_fetcher_max_workers(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str | None,
    expected: int,
) -> None:
    """Jira worker limit falls back unless env var is a positive integer."""
    if raw_value is None:
        monkeypatch.delenv(FETCHER_MAX_WORKERS_ENV, raising=False)
    else:
        monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, raw_value)

    assert get_fetcher_max_workers() == expected


@pytest.mark.anyio
async def test_run_fetcher_call_allows_bounded_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocking Jira calls can overlap while respecting the configured limit."""
    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "2")
    active = 0
    max_active = 0
    lock = Lock()
    # Each call waits until a second call runs beside it.
    together = threading.Barrier(2, timeout=budget(5))

    def blocking_call(value: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        together.wait()
        with lock:
            active -= 1
        return value

    results: list[int] = []

    async def call(value: int) -> None:
        results.append(await run_fetcher_call(blocking_call, value))

    async with anyio.create_task_group() as task_group:
        for value in range(4):
            task_group.start_soon(call, value)

    assert sorted(results) == [0, 1, 2, 3]
    assert max_active == 2


@pytest.mark.anyio
async def test_run_fetcher_call_respects_single_worker_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured single-worker limit serializes offloaded blocking calls."""
    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "1")
    active = 0
    max_active = 0
    lock = Lock()

    def blocking_call(value: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value

    async with anyio.create_task_group() as task_group:
        for value in range(3):
            task_group.start_soon(run_fetcher_call, blocking_call, value)

    assert max_active == 1


def test_run_fetcher_call_works_from_foreign_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Limiter creation is safe when the first call happens outside the main thread."""
    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "2")

    def run_from_worker() -> int:
        return anyio.run(run_fetcher_call, lambda: 42)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future: Future[int] = executor.submit(run_from_worker)
        assert future.result(timeout=5) == 42


def test_run_fetcher_call_works_across_anyio_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Limiter state is isolated between asyncio and Trio event loops."""
    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "2")

    async def call(value: str) -> str:
        return await run_fetcher_call(lambda: value)

    assert anyio.run(call, "asyncio") == "asyncio"
    assert anyio.run(call, "trio", backend="trio") == "trio"


class _SiteFetcher:
    """Minimal fetcher whose method blocks until released."""

    def __init__(self, url: str, release: threading.Event) -> None:
        self.config = type("Config", (), {"url": url})()
        self._release = release
        self.entered = threading.Semaphore(0)

    def slow_call(self) -> str:
        self.entered.release()
        if not self._release.wait(budget(5)):
            raise AssertionError("never released")
        return "slow"

    def quick_call(self) -> str:
        return self.config.url


@pytest.mark.anyio
async def test_slow_upstream_does_not_hold_other_upstreams_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A site using all of its worker slots does not delay another site."""
    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "2")
    release = threading.Event()
    slow = _SiteFetcher("https://slow.example.test", release)
    fast = _SiteFetcher("https://fast.example.test", release)
    results: list[str] = []

    async with anyio.create_task_group() as task_group:
        for _ in range(2):
            task_group.start_soon(run_fetcher_call, slow.slow_call)
        for _ in range(2):
            await anyio.to_thread.run_sync(slow.entered.acquire)
        try:
            with anyio.fail_after(budget(5)):
                results.append(await run_fetcher_call(fast.quick_call))
            # Same-site calls still queue behind the site's own slots.
            with anyio.move_on_after(0.2) as same_site:
                await run_fetcher_call(slow.quick_call)
        finally:
            release.set()

    assert results == ["https://fast.example.test"]
    assert same_site.cancelled_caught


@pytest.mark.anyio
async def test_untrusted_call_deadline_includes_waiting_for_a_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A call queued behind a stuck one still ends at its own deadline."""
    from src.mcp_atlassian.servers import async_utils

    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "1")
    monkeypatch.setattr(async_utils, "UNTRUSTED_CALL_TIMEOUT", 0.3, raising=False)
    release = threading.Event()
    # The first call ignores its abort, so it keeps the site's only slot.
    stuck = _SiteFetcher("https://attacker.example:8441", release)
    waited: list[float] = []

    async def stuck_call() -> None:
        with pytest.raises(TimeoutError):
            await run_fetcher_call(stuck.slow_call)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(stuck_call)
        await anyio.to_thread.run_sync(stuck.entered.acquire)
        try:
            start = time.monotonic()
            with anyio.move_on_after(budget(3)):
                try:
                    await run_fetcher_call(stuck.quick_call)
                except TimeoutError:
                    waited.append(time.monotonic() - start)
        finally:
            release.set()

    assert waited, "the queued call did not stop at its deadline"
    assert waited[0] < budget(1.5)


def _oauth_config(config_class: type, cloud_id: str) -> object:
    from mcp_atlassian.utils.oauth import OAuthConfig

    return config_class(
        url="https://api.atlassian.com",
        auth_type="oauth",
        oauth_config=OAuthConfig(
            client_id="id",
            client_secret="secret",  # noqa: S106
            redirect_uri="http://localhost",
            scope="read:jira-work",
            cloud_id=cloud_id,
        ),
    )


@pytest.mark.parametrize("service", ["jira", "confluence"])
def test_cloud_oauth_sites_get_separate_upstream_keys(service: str) -> None:
    """OAuth configs that differ only in Cloud ID are different upstreams.

    The key is the same while the fetcher is built (config argument) and for
    calls on the built fetcher (bound method).
    """
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig
    from mcp_atlassian.servers.async_utils import call_upstream

    config_class = JiraConfig if service == "jira" else ConfluenceConfig
    config_a = _oauth_config(config_class, "cloud-a")
    config_b = _oauth_config(config_class, "cloud-b")

    def build(config: object) -> None:
        return None

    class Fetcher:
        def __init__(self, config: object) -> None:
            self.config = config

        def call(self) -> None:
            return None

    key_a = call_upstream(build, (), {"config": config_a})
    key_b = call_upstream(build, (), {"config": config_b})

    assert key_a != key_b
    assert key_a == f"https://api.atlassian.com:443/ex/{service}/cloud-a"
    assert call_upstream(Fetcher(config_a).call, (), {}) == key_a
    assert call_upstream(build, (object(), "spec", config_b), {}) == key_b


class _DripServer:
    """Loopback HTTP server that sends its body one byte at a time.

    Each byte arrives well inside any per-read timeout, so only a deadline on
    the whole call stops a client that reads it.
    """

    def __init__(self, seconds: float, head: str = "HTTP/1.1 200 OK") -> None:
        import socket

        self._seconds = seconds
        self._head = head
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.url = f"http://127.0.0.1:{self._sock.getsockname()[1]}/"
        self._stop = threading.Event()
        self.requests = 0
        #: Released each time the server is done with a connection.
        self.closed = threading.Semaphore(0)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._drip, args=(conn,), daemon=True).start()

    def _drip(self, conn: object) -> None:
        import socket

        assert isinstance(conn, socket.socket)
        try:
            with conn:
                if not conn.recv(65536):
                    return
                self.requests += 1
                steps = round(self._seconds / 0.1)
                conn.sendall(
                    f"{self._head}\r\nContent-Length: {steps}\r\n\r\n".encode()
                )
                for _ in range(steps):
                    if self._stop.wait(0.1):
                        return
                    conn.sendall(b"x")
        except OSError:
            return
        finally:
            self.closed.release()

    def close(self) -> None:
        self._stop.set()
        self._sock.close()


@pytest.fixture
def drip_server() -> Iterator[_DripServer]:
    server = _DripServer(seconds=budget(6))
    yield server
    server.close()


class _HttpFetcher:
    """Fetcher for ``site`` whose call reads ``target`` through a real Session."""

    def __init__(self, site: str, target: str, *, pinned: bool = False) -> None:
        import requests

        from mcp_atlassian.utils.http import configure_default_timeout
        from mcp_atlassian.utils.ssrf_adapter import mount_ssrf_pinning

        self.config = type("Config", (), {"url": site})()
        self.session = requests.Session()
        if pinned:
            mount_ssrf_pinning(self.session)
        configure_default_timeout(self.session, 30)
        self._target = target
        self.returned = threading.Event()

    def read(self) -> int:
        try:
            return len(self.session.get(self._target).content)
        finally:
            self.returned.set()


@pytest.mark.anyio
async def test_untrusted_upstreams_share_a_small_fixed_thread_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request-supplied hosts on any number of ports hold only a fixed share."""
    from src.mcp_atlassian.servers import async_utils

    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "1")
    monkeypatch.setenv("JIRA_URL", "https://jira.corp.example")
    monkeypatch.setattr(async_utils, "UNTRUSTED_UPSTREAM_WORKERS", 2, raising=False)
    release = threading.Event()
    entered = threading.Semaphore(0)
    running = 0
    peak = 0
    lock = Lock()

    class _Attacker:
        def __init__(self, port: int) -> None:
            self.config = type("C", (), {"url": f"https://attacker.example:{port}"})()

        def call(self) -> None:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            entered.release()
            try:
                release.wait(budget(5))
            finally:
                with lock:
                    running -= 1

    operator_site = _SiteFetcher("https://jira.corp.example", release)
    cloud_site = _SiteFetcher("https://victim.atlassian.net", release)
    async with anyio.create_task_group() as task_group:
        for port in range(8441, 8446):
            task_group.start_soon(run_fetcher_call, _Attacker(port).call)
        try:
            for _ in range(2):
                assert await anyio.to_thread.run_sync(
                    partial(entered.acquire, timeout=budget(5))
                )
            # A third call that gets past the shared budget shows up here.
            assert not await anyio.to_thread.run_sync(
                partial(entered.acquire, timeout=0.3)
            )
            with anyio.fail_after(budget(2)):
                assert await run_fetcher_call(operator_site.quick_call)
                assert await run_fetcher_call(cloud_site.quick_call)
            assert peak == 2
        finally:
            release.set()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "site", ["https://attacker.example:8441", "https://jira.corp.example"]
)
async def test_cancelled_call_gives_its_thread_back_quickly(
    monkeypatch: pytest.MonkeyPatch, drip_server: _DripServer, site: str
) -> None:
    """Cancelling a call stops its upstream read instead of waiting it out."""
    monkeypatch.setenv("JIRA_URL", "https://jira.corp.example")
    fetcher = _HttpFetcher(site, drip_server.url)
    start = time.monotonic()
    with anyio.move_on_after(0.5):
        await run_fetcher_call(fetcher.read)
    assert await anyio.to_thread.run_sync(fetcher.returned.wait, budget(10))
    assert time.monotonic() - start < budget(2.5)


@pytest.mark.anyio
async def test_untrusted_call_stops_at_its_deadline(
    monkeypatch: pytest.MonkeyPatch, drip_server: _DripServer
) -> None:
    """A request-supplied host cannot keep a worker thread past the deadline."""
    from src.mcp_atlassian.servers import async_utils

    monkeypatch.setattr(async_utils, "UNTRUSTED_CALL_TIMEOUT", 0.5, raising=False)
    fetcher = _HttpFetcher("https://attacker.example:8441", drip_server.url)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await run_fetcher_call(fetcher.read)
    assert time.monotonic() - start < budget(2.5)
    assert fetcher.returned.is_set()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "head", ["HTTP/1.1 200 OK\r\nConnection: close", "HTTP/1.0 200 OK"]
)
async def test_untrusted_call_stops_at_its_deadline_on_closing_response(
    monkeypatch: pytest.MonkeyPatch, head: str
) -> None:
    """The deadline also stops a response that ends the connection after it."""
    from src.mcp_atlassian.servers import async_utils

    monkeypatch.setattr(async_utils, "UNTRUSTED_CALL_TIMEOUT", 0.5, raising=False)
    server = _DripServer(seconds=budget(6), head=head)
    try:
        fetcher = _HttpFetcher("https://attacker.example:8441", server.url)
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            await run_fetcher_call(fetcher.read)
        assert time.monotonic() - start < budget(2.5)
        assert fetcher.returned.is_set()
    finally:
        server.close()


class _SlowDns:
    """``slow-dns.test`` resolves to loopback once released or after ``delay``."""

    def __init__(self) -> None:
        self.delay = 1.0
        #: Set when a lookup of ``slow-dns.test`` starts.
        self.entered = threading.Event()
        self.release = threading.Event()


@pytest.fixture
def slow_dns(monkeypatch: pytest.MonkeyPatch) -> Iterator[_SlowDns]:
    """Make ``slow-dns.test`` resolve to loopback only after a wait."""
    import socket

    real = socket.getaddrinfo
    dns = _SlowDns()

    def getaddrinfo(host: object, port: object, *args: object) -> object:
        if host == "slow-dns.test":
            dns.entered.set()
            dns.release.wait(dns.delay)
            host = "127.0.0.1"
        return real(host, port, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield dns
    dns.release.set()


@pytest.mark.anyio
async def test_call_aborted_while_connecting_sends_no_request(
    monkeypatch: pytest.MonkeyPatch,
    drip_server: _DripServer,
    slow_dns: _SlowDns,
) -> None:
    """A connection that opens after the call is cancelled is dropped, not read."""
    from mcp_atlassian.utils.http import CallBudget

    slow_dns.delay = budget(10)
    real_abort = CallBudget.abort

    def abort_then_resolve(self: CallBudget) -> None:
        real_abort(self)
        # The lookup finishes and the connection opens only after the abort.
        slow_dns.release.set()

    monkeypatch.setattr(CallBudget, "abort", abort_then_resolve)
    target = drip_server.url.replace("127.0.0.1", "slow-dns.test")
    fetcher = _HttpFetcher("https://attacker.example:8441", target)
    with anyio.fail_after(budget(5)):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_fetcher_call, fetcher.read)
            assert await anyio.to_thread.run_sync(slow_dns.entered.wait, budget(5))
            task_group.cancel_scope.cancel()
    assert fetcher.returned.is_set()
    # The late connection reached the server and was closed with no request.
    assert await anyio.to_thread.run_sync(
        partial(drip_server.closed.acquire, timeout=budget(5))
    )
    assert drip_server.requests == 0


@pytest.mark.anyio
async def test_call_aborted_during_a_slow_lookup_returns_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
    drip_server: _DripServer,
    slow_dns: _SlowDns,
) -> None:
    """The pinning adapter's DNS lookup does not hold the call past its deadline."""
    from src.mcp_atlassian.servers import async_utils

    slow_dns.delay = budget(5.0)
    target = drip_server.url.replace("127.0.0.1", "slow-dns.test")
    # Lets the pinning adapter connect to the loopback test server.
    monkeypatch.setenv("JIRA_URL", target.rstrip("/"))
    monkeypatch.setattr(async_utils, "UNTRUSTED_CALL_TIMEOUT", 0.3, raising=False)
    fetcher = _HttpFetcher("https://attacker.example:8441", target, pinned=True)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await run_fetcher_call(fetcher.read)
    assert time.monotonic() - start < budget(1.5)
    assert fetcher.returned.is_set()
    assert drip_server.requests == 0


@pytest.mark.anyio
async def test_fetcher_calls_do_not_draw_on_anyio_default_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhausting anyio's shared default limiter does not stop fetcher calls."""
    monkeypatch.setenv("JIRA_URL", "https://jira.corp.example")
    default = anyio.to_thread.current_default_thread_limiter()
    monkeypatch.setattr(default, "total_tokens", 1)
    release = threading.Event()
    trusted = _SiteFetcher("https://jira.corp.example", release)
    untrusted = _SiteFetcher("https://attacker.example:8441", release)
    holding = threading.Event()

    def hold_default_thread() -> None:
        holding.set()
        release.wait(budget(5))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(anyio.to_thread.run_sync, hold_default_thread)
        try:
            # The only default token is taken, so poll instead of a thread wait.
            with anyio.fail_after(budget(5)):
                while not holding.is_set():
                    await anyio.sleep(0.01)
            assert default.borrowed_tokens == 1
            with anyio.fail_after(budget(2)):
                assert await run_fetcher_call(trusted.quick_call)
                assert await run_fetcher_call(untrusted.quick_call)
        finally:
            release.set()


async def _fill(
    task_group: anyio.abc.TaskGroup, fetcher: _SiteFetcher, calls: int, entered: int
) -> None:
    """Start ``calls`` blocking calls to ``fetcher`` and wait for ``entered``."""
    for _ in range(calls):
        task_group.start_soon(run_fetcher_call, fetcher.slow_call)
    for _ in range(entered):
        assert await anyio.to_thread.run_sync(
            partial(fetcher.entered.acquire, timeout=budget(5))
        )


@pytest.mark.anyio
@pytest.mark.parametrize("service_env", ["JIRA_URL", "CONFLUENCE_URL"])
async def test_operator_site_is_served_while_other_trusted_sites_are_busy(
    monkeypatch: pytest.MonkeyPatch, service_env: str
) -> None:
    """Busy allowlisted and Cloud sites do not stall the configured site."""
    server = _DripServer(seconds=0.1)
    try:
        monkeypatch.setenv(service_env, server.url.rstrip("/"))
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "corp.example")
        release = threading.Event()
        busy = [
            _SiteFetcher("https://a.corp.example", release),
            _SiteFetcher("https://b.corp.example", release),
            _SiteFetcher("https://one.atlassian.net", release),
            _SiteFetcher("https://two.atlassian.net", release),
        ]
        operator_site = _HttpFetcher(server.url, server.url)
        async with anyio.create_task_group() as task_group:
            try:
                for fetcher in busy:
                    await _fill(task_group, fetcher, 8, 8)
                with anyio.fail_after(budget(3)):
                    assert await run_fetcher_call(operator_site.read) == 1
            finally:
                release.set()
        assert server.requests == 1
    finally:
        server.close()


@pytest.mark.anyio
async def test_one_trusted_site_cannot_take_every_shared_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-site cap above the shared total still leaves room for other sites."""
    from src.mcp_atlassian.servers import async_utils

    monkeypatch.setenv(FETCHER_MAX_WORKERS_ENV, "64")
    server = _DripServer(seconds=0.1)
    try:
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "corp.example")
        release = threading.Event()
        hog = _SiteFetcher("https://hog.atlassian.net", release)
        other = _HttpFetcher("https://other.corp.example", server.url)
        async with anyio.create_task_group() as task_group:
            try:
                await _fill(
                    task_group, hog, 64, async_utils.TRUSTED_UPSTREAM_WORKERS // 2
                )
                with anyio.fail_after(budget(3)):
                    assert await run_fetcher_call(other.read) == 1
            finally:
                release.set()
    finally:
        server.close()


@pytest.mark.parametrize("service", ["jira", "confluence"])
def test_operator_cloud_oauth_site_counts_as_configured_site(
    monkeypatch: pytest.MonkeyPatch, service: str
) -> None:
    """The operator's Cloud OAuth site gets the configured-site pool."""
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig
    from src.mcp_atlassian.servers import async_utils

    config_class = JiraConfig if service == "jira" else ConfluenceConfig
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLOUD_ID", "cloud-a")
    own = async_utils.call_upstream(
        lambda config: None, (_oauth_config(config_class, "cloud-a"),), {}
    )
    other = async_utils.call_upstream(
        lambda config: None, (_oauth_config(config_class, "cloud-b"),), {}
    )
    assert own in async_utils._operator_upstreams()
    assert other not in async_utils._operator_upstreams()
