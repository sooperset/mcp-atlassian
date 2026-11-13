"""Async helpers for server tool implementations."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from typing import ParamSpec, TypeVar

import anyio
from anyio.lowlevel import RunVar

P = ParamSpec("P")
T = TypeVar("T")

JIRA_FETCHER_MAX_WORKERS_ENV = "JIRA_FETCHER_MAX_WORKERS"
DEFAULT_JIRA_FETCHER_MAX_WORKERS = 8

CONFLUENCE_FETCHER_MAX_WORKERS_ENV = "CONFLUENCE_FETCHER_MAX_WORKERS"
DEFAULT_CONFLUENCE_FETCHER_MAX_WORKERS = 8

_jira_fetcher_limiter: RunVar[tuple[int, anyio.CapacityLimiter] | None] = RunVar(
    "jira_fetcher_limiter",
    default=None,
)

_confluence_fetcher_limiter: RunVar[tuple[int, anyio.CapacityLimiter] | None] = RunVar(
    "confluence_fetcher_limiter",
    default=None,
)


def _get_fetcher_max_workers(env_var: str, default: int) -> int:
    """Return the configured worker count for a fetcher, or the default."""
    raw_value = os.getenv(env_var)
    if not raw_value:
        return default

    try:
        worker_count = int(raw_value)
    except ValueError:
        return default

    if worker_count <= 0:
        return default
    return worker_count


def get_jira_fetcher_max_workers() -> int:
    """Return the configured maximum concurrent Jira fetcher calls."""
    return _get_fetcher_max_workers(
        JIRA_FETCHER_MAX_WORKERS_ENV,
        DEFAULT_JIRA_FETCHER_MAX_WORKERS,
    )


def get_confluence_fetcher_max_workers() -> int:
    """Return the configured maximum concurrent Confluence fetcher calls."""
    return _get_fetcher_max_workers(
        CONFLUENCE_FETCHER_MAX_WORKERS_ENV,
        DEFAULT_CONFLUENCE_FETCHER_MAX_WORKERS,
    )


def _get_fetcher_limiter(
    limiter_var: RunVar[tuple[int, anyio.CapacityLimiter] | None],
    worker_count: int,
) -> anyio.CapacityLimiter:
    """Return an event-loop-local limiter for fetcher worker threads."""
    limiter_state = limiter_var.get()
    if limiter_state is None or limiter_state[0] != worker_count:
        limiter_state = (worker_count, anyio.CapacityLimiter(worker_count))
        limiter_var.set(limiter_state)
    return limiter_state[1]


def _get_jira_fetcher_limiter() -> anyio.CapacityLimiter:
    """Return an event-loop-local limiter for Jira fetcher worker threads."""
    return _get_fetcher_limiter(_jira_fetcher_limiter, get_jira_fetcher_max_workers())


def _get_confluence_fetcher_limiter() -> anyio.CapacityLimiter:
    """Return an event-loop-local limiter for Confluence fetcher worker threads."""
    return _get_fetcher_limiter(
        _confluence_fetcher_limiter,
        get_confluence_fetcher_max_workers(),
    )


async def _run_fetcher_call(
    limiter: anyio.CapacityLimiter,
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run a blocking fetcher call in a bounded worker thread."""
    call = partial(func, *args, **kwargs)
    return await anyio.to_thread.run_sync(
        call,
        limiter=limiter,
    )


async def run_jira_fetcher_call(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run a blocking Jira fetcher call in a bounded worker thread."""
    return await _run_fetcher_call(_get_jira_fetcher_limiter(), func, *args, **kwargs)


async def run_confluence_fetcher_call(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run a blocking Confluence fetcher call in a bounded worker thread."""
    return await _run_fetcher_call(
        _get_confluence_fetcher_limiter(),
        func,
        *args,
        **kwargs,
    )
