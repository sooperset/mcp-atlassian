"""Tests for server async utility helpers."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

import anyio
import pytest

from src.mcp_atlassian.servers.async_utils import (
    DEFAULT_FETCHER_MAX_WORKERS,
    FETCHER_MAX_WORKERS_ENV,
    get_fetcher_max_workers,
    run_fetcher_call,
)


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

    def blocking_call(value: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
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
    assert max_active > 1
    assert max_active <= 2


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
        if not self._release.wait(5):
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
            with anyio.fail_after(5):
                results.append(await run_fetcher_call(fast.quick_call))
            # Same-site calls still queue behind the site's own slots.
            with anyio.move_on_after(0.2) as same_site:
                await run_fetcher_call(slow.quick_call)
        finally:
            release.set()

    assert results == ["https://fast.example.test"]
    assert same_site.cancelled_caught


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
