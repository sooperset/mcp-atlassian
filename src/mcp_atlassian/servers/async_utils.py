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

_jira_fetcher_limiter: RunVar[tuple[int, anyio.CapacityLimiter] | None] = RunVar(
    "jira_fetcher_limiter",
    default=None,
)


def get_jira_fetcher_max_workers() -> int:
    """Return the configured maximum concurrent Jira fetcher calls."""
    raw_value = os.getenv(JIRA_FETCHER_MAX_WORKERS_ENV)
    if not raw_value:
        return DEFAULT_JIRA_FETCHER_MAX_WORKERS

    try:
        worker_count = int(raw_value)
    except ValueError:
        return DEFAULT_JIRA_FETCHER_MAX_WORKERS

    if worker_count <= 0:
        return DEFAULT_JIRA_FETCHER_MAX_WORKERS
    return worker_count


def _get_jira_fetcher_limiter() -> anyio.CapacityLimiter:
    """Return an event-loop-local limiter for Jira fetcher worker threads."""
    worker_count = get_jira_fetcher_max_workers()
    limiter_state = _jira_fetcher_limiter.get()
    if limiter_state is None or limiter_state[0] != worker_count:
        limiter_state = (worker_count, anyio.CapacityLimiter(worker_count))
        _jira_fetcher_limiter.set(limiter_state)
    return limiter_state[1]


async def run_jira_fetcher_call(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run a blocking Jira fetcher call in a bounded worker thread."""
    call = partial(func, *args, **kwargs)
    return await anyio.to_thread.run_sync(
        call,
        limiter=_get_jira_fetcher_limiter(),
    )
