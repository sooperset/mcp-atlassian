"""Async helpers for server tool implementations.

Fetcher methods are synchronous ``requests`` calls. An async tool handler that
calls one directly blocks the event loop, and on the HTTP transports that loop
serves every caller in the process. Handlers therefore send every fetcher call
through :func:`run_fetcher_call`, which runs it in a worker thread.

Worker slots are bounded per upstream site, so a slow or rate-limited upstream
can use up only its own slots. The total thread count stays bounded by
anyio's default thread limiter.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, ParamSpec, TypeVar

import anyio
from anyio.lowlevel import RunVar

from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.urls import upstream_key

P = ParamSpec("P")
T = TypeVar("T")

# The name predates the Confluence handlers using the same helper; it now caps
# the worker threads per upstream site for both services.
FETCHER_MAX_WORKERS_ENV = "JIRA_FETCHER_MAX_WORKERS"
DEFAULT_FETCHER_MAX_WORKERS = 8


@dataclass
class _UpstreamSlots:
    limiter: anyio.CapacityLimiter
    users: int = 0


_upstream_slots: RunVar[dict[str, _UpstreamSlots] | None] = RunVar(
    "fetcher_upstream_slots",
    default=None,
)


def get_fetcher_max_workers() -> int:
    """Return the configured maximum concurrent fetcher calls per upstream."""
    raw_value = os.getenv(FETCHER_MAX_WORKERS_ENV)
    if not raw_value:
        return DEFAULT_FETCHER_MAX_WORKERS

    try:
        worker_count = int(raw_value)
    except ValueError:
        return DEFAULT_FETCHER_MAX_WORKERS

    if worker_count <= 0:
        return DEFAULT_FETCHER_MAX_WORKERS
    return worker_count


def config_api_url(config: Any) -> str | None:
    """Return the URL a Jira or Confluence config actually sends requests to.

    Cloud OAuth requests go to ``api.atlassian.com/ex/<service>/<cloud id>``,
    not to ``config.url``, so two OAuth configs with the same ``url`` but
    different Cloud IDs are different upstreams.
    """
    oauth = getattr(config, "oauth_config", None)
    if (
        getattr(config, "auth_type", None) == "oauth"
        and oauth is not None
        and getattr(oauth, "is_data_center", False) is not True
    ):
        cloud_id = getattr(oauth, "cloud_id", None)
        if isinstance(cloud_id, str) and cloud_id:
            service = "confluence" if isinstance(config, ConfluenceConfig) else "jira"
            return f"https://api.atlassian.com/ex/{service}/{cloud_id}"
    url = getattr(config, "url", None)
    return url if isinstance(url, str) and url else None


def _fetcher_url(candidate: Any) -> str | None:
    """Return the upstream URL of the fetcher or service config behind ``candidate``."""
    while isinstance(candidate, partial):
        candidate = candidate.func
    owner = getattr(candidate, "__self__", candidate)
    for holder in (getattr(owner, "config", None), owner):
        if isinstance(holder, JiraConfig | ConfluenceConfig):
            return config_api_url(holder)
        url = getattr(holder, "url", None)
        if isinstance(url, str) and url:
            return url
    return None


def call_upstream(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    """Return the upstream key for a fetcher call.

    The upstream is found from the bound method being called, or from a
    fetcher, bound fetcher method or service config passed as an argument
    (for example the ``fetch_fn`` of an attachment helper, or the config a
    fetcher is built from). Calls with no fetcher share one
    default key.
    """
    for candidate in (func, *args, *kwargs.values()):
        url = _fetcher_url(candidate)
        if url:
            return upstream_key(url)
    return ""


def _checkout_slots(key: str) -> _UpstreamSlots:
    registry = _upstream_slots.get()
    if registry is None:
        registry = {}
        _upstream_slots.set(registry)
    worker_count = get_fetcher_max_workers()
    slots = registry.get(key)
    if slots is None:
        slots = _UpstreamSlots(anyio.CapacityLimiter(worker_count))
        registry[key] = slots
    elif slots.limiter.total_tokens != worker_count:
        slots.limiter.total_tokens = worker_count
    slots.users += 1
    return slots


def _release_slots(key: str, slots: _UpstreamSlots) -> None:
    slots.users -= 1
    registry = _upstream_slots.get()
    if slots.users == 0 and registry is not None and registry.get(key) is slots:
        del registry[key]


async def run_fetcher_call(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run a blocking Jira or Confluence fetcher call in a worker thread.

    Calls to one upstream site share that site's slots; calls to other sites
    do not wait for them.
    """
    key = call_upstream(func, args, kwargs)
    slots = _checkout_slots(key)
    try:
        async with slots.limiter:
            return await anyio.to_thread.run_sync(partial(func, *args, **kwargs))
    finally:
        _release_slots(key, slots)
