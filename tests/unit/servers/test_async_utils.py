"""Tests for server async utility helpers."""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

import anyio
import pytest

from src.mcp_atlassian.servers.async_utils import (
    DEFAULT_JIRA_FETCHER_MAX_WORKERS,
    JIRA_FETCHER_MAX_WORKERS_ENV,
    get_jira_fetcher_max_workers,
    run_jira_fetcher_call,
)


@pytest.fixture(autouse=True)
def reset_jira_fetcher_workers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset the Jira worker limit env var between tests."""
    monkeypatch.delenv(JIRA_FETCHER_MAX_WORKERS_ENV, raising=False)
    yield
    monkeypatch.delenv(JIRA_FETCHER_MAX_WORKERS_ENV, raising=False)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, DEFAULT_JIRA_FETCHER_MAX_WORKERS),
        ("1", 1),
        ("8", 8),
        ("16", 16),
        ("0", DEFAULT_JIRA_FETCHER_MAX_WORKERS),
        ("-1", DEFAULT_JIRA_FETCHER_MAX_WORKERS),
        ("abc", DEFAULT_JIRA_FETCHER_MAX_WORKERS),
        ("", DEFAULT_JIRA_FETCHER_MAX_WORKERS),
    ],
)
def test_get_jira_fetcher_max_workers(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str | None,
    expected: int,
) -> None:
    """Jira worker limit falls back unless env var is a positive integer."""
    if raw_value is None:
        monkeypatch.delenv(JIRA_FETCHER_MAX_WORKERS_ENV, raising=False)
    else:
        monkeypatch.setenv(JIRA_FETCHER_MAX_WORKERS_ENV, raw_value)

    assert get_jira_fetcher_max_workers() == expected


@pytest.mark.anyio
async def test_run_jira_fetcher_call_allows_bounded_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocking Jira calls can overlap while respecting the configured limit."""
    monkeypatch.setenv(JIRA_FETCHER_MAX_WORKERS_ENV, "2")
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
        results.append(await run_jira_fetcher_call(blocking_call, value))

    async with anyio.create_task_group() as task_group:
        for value in range(4):
            task_group.start_soon(call, value)

    assert sorted(results) == [0, 1, 2, 3]
    assert max_active > 1
    assert max_active <= 2


@pytest.mark.anyio
async def test_run_jira_fetcher_call_respects_single_worker_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured single-worker limit serializes offloaded blocking calls."""
    monkeypatch.setenv(JIRA_FETCHER_MAX_WORKERS_ENV, "1")
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
            task_group.start_soon(run_jira_fetcher_call, blocking_call, value)

    assert max_active == 1


def test_run_jira_fetcher_call_works_from_foreign_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Limiter creation is safe when the first call happens outside the main thread."""
    monkeypatch.setenv(JIRA_FETCHER_MAX_WORKERS_ENV, "2")

    def run_from_worker() -> int:
        return anyio.run(run_jira_fetcher_call, lambda: 42)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future: Future[int] = executor.submit(run_from_worker)
        assert future.result(timeout=5) == 42


def test_run_jira_fetcher_call_works_across_anyio_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Limiter state is isolated between asyncio and Trio event loops."""
    monkeypatch.setenv(JIRA_FETCHER_MAX_WORKERS_ENV, "2")

    async def call(value: str) -> str:
        return await run_jira_fetcher_call(lambda: value)

    assert anyio.run(call, "asyncio") == "asyncio"
    assert anyio.run(call, "trio", backend="trio") == "trio"
