"""Async helpers for server tool implementations.

Fetcher methods are synchronous ``requests`` calls. An async tool handler that
calls one directly blocks the event loop, and on the HTTP transports that loop
serves every caller in the process. Handlers therefore send every fetcher call
through :func:`run_fetcher_call`, which runs it in a worker thread.

Worker slots are bounded per upstream site, so a slow or rate-limited upstream
can use up only its own slots. Calls draw their threads from this module's own
pools, not from anyio's default thread limiter: each configured service site
(``JIRA_URL``, ``CONFLUENCE_URL``) has a pool of its own, other sites the
operator trusts (``MCP_ALLOWED_URL_DOMAINS``, Atlassian Cloud) share one pool,
and sites a request names share a small one. A caller who points requests at
hosts of their own, on any number of ports, holds at most the small pool, and
such calls also stop at a wall-clock deadline. A cancelled call stops its
upstream reads, so its thread comes back within one connect timeout.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, ParamSpec, TypeVar
from urllib.parse import urlparse

import anyio
from anyio.lowlevel import RunVar

from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.http import CallBudget
from mcp_atlassian.utils.ssrf_adapter import (
    _configured_service_urls,
    is_operator_trusted_url,
)
from mcp_atlassian.utils.urls import (
    _get_domain_allowlist,
    _hostname_matches_allowlist,
    is_atlassian_cloud_url,
    upstream_key,
    validate_url_for_ssrf,
)

P = ParamSpec("P")
T = TypeVar("T")

# The name predates the Confluence handlers using the same helper; it now caps
# the worker threads per upstream site for both services.
FETCHER_MAX_WORKERS_ENV = "JIRA_FETCHER_MAX_WORKERS"
DEFAULT_FETCHER_MAX_WORKERS = 8

# Threads for all trusted sites other than the configured service sites
# together. One such site gets at most half of them, whatever the per-site cap.
TRUSTED_UPSTREAM_WORKERS = 32
# Threads for all request-supplied sites together, and the wall-clock limit of
# one call to such a site, in seconds.
UNTRUSTED_UPSTREAM_WORKERS = 8
UNTRUSTED_CALL_TIMEOUT = 120.0
# Address (DNS) checks of request URL headers: threads per trust class, and the
# seconds a request waits for one before it is refused.
URL_CHECK_WORKERS = 4
URL_CHECK_TIMEOUT = 10.0


@dataclass
class _UpstreamSlots:
    limiter: anyio.CapacityLimiter
    users: int = 0


@dataclass
class _Pool:
    """Worker threads shared by a group of upstream sites."""

    threads: anyio.CapacityLimiter
    site_cap: int
    sites: dict[str, _UpstreamSlots] = field(default_factory=dict)


_pools: RunVar[dict[str, _Pool] | None] = RunVar("fetcher_pools", default=None)
_url_check_threads: dict[bool, tuple[int, threading.BoundedSemaphore]] = {}
_url_check_lock = threading.Lock()


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


def _call_url(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str | None:
    for candidate in (func, *args, *kwargs.values()):
        url = _fetcher_url(candidate)
        if url:
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
    url = _call_url(func, args, kwargs)
    return upstream_key(url) if url else ""


def is_trusted_upstream(url: str) -> bool:
    """Return True for a site whose pace no request can choose.

    These are the operator's configured service URLs and
    ``MCP_ALLOWED_URL_DOMAINS`` hosts, and Atlassian Cloud on its standard
    HTTPS port. Any other host named in a request header may belong to the
    caller, who can make it answer as slowly as they like.
    """
    if is_operator_trusted_url(url):
        return True
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https" and port in (None, 443) and is_atlassian_cloud_url(url)
    )


def _operator_upstreams() -> set[str]:
    """Return the upstream keys of the service sites the operator configured.

    These are the ``JIRA_URL`` and ``CONFLUENCE_URL`` sites, and for Cloud
    OAuth the ``api.atlassian.com`` paths of ``ATLASSIAN_OAUTH_CLOUD_ID``.
    """
    keys = {upstream_key(url) for url in _configured_service_urls()}
    cloud_id = os.getenv("ATLASSIAN_OAUTH_CLOUD_ID", "").strip()
    if cloud_id:
        keys.update(
            upstream_key(f"https://api.atlassian.com/ex/{service}/{cloud_id}")
            for service in ("jira", "confluence")
        )
    keys.discard("")
    return keys


def _pool(name: str, total: int, site_cap: int) -> _Pool:
    pools = _pools.get()
    if pools is None:
        pools = {}
        _pools.set(pools)
    pool = pools.get(name)
    if pool is None:
        pool = _Pool(anyio.CapacityLimiter(total), site_cap)
        pools[name] = pool
    else:
        if pool.threads.total_tokens != total:
            pool.threads.total_tokens = total
        pool.site_cap = site_cap
    return pool


def _site_pool(url: str | None, key: str, trusted: bool) -> _Pool:
    """Return the thread pool for calls to the upstream ``key``.

    A configured service site has a pool of its own of the per-site size, so
    calls to other sites, however many, never hold its threads.
    """
    per_site = get_fetcher_max_workers()
    if url is not None and key in _operator_upstreams():
        return _pool(f"operator {key}", per_site, per_site)
    if trusted:
        total = TRUSTED_UPSTREAM_WORKERS
        return _pool("trusted", total, min(per_site, max(1, total // 2)))
    total = UNTRUSTED_UPSTREAM_WORKERS
    return _pool("untrusted", total, min(per_site, total))


def _checkout_slots(pool: _Pool, key: str) -> _UpstreamSlots:
    worker_count = pool.site_cap
    slots = pool.sites.get(key)
    if slots is None:
        slots = _UpstreamSlots(anyio.CapacityLimiter(worker_count))
        pool.sites[key] = slots
    elif slots.limiter.total_tokens != worker_count:
        slots.limiter.total_tokens = worker_count
    slots.users += 1
    return slots


def _release_slots(pool: _Pool, key: str, slots: _UpstreamSlots) -> None:
    slots.users -= 1
    if slots.users == 0 and pool.sites.get(key) is slots:
        del pool.sites[key]


async def _run_in_thread(
    call: Callable[[], T],
    threads: anyio.CapacityLimiter,
    deadline: float | None = None,
) -> T:
    """Run ``call`` in a worker thread; stop it when the caller is cancelled.

    The thread's pool token is held until the thread really returns, so the
    pool size bounds the number of threads. Waiting for the thread is not
    shielded from cancellation: the caller's cancel or deadline aborts the
    call's budget, and then the shielded thread wait finishes quickly.
    """
    budget = CallBudget(deadline)
    outcome: list[tuple[bool, Any]] = []
    finished = anyio.Event()

    async def runner() -> None:
        try:
            value = await anyio.to_thread.run_sync(
                partial(budget.run, call), limiter=threads
            )
        except anyio.get_cancelled_exc_class():
            raise
        except BaseException as exc:  # noqa: BLE001 - re-raised by the caller
            outcome.append((False, exc))
        else:
            outcome.append((True, value))
        finally:
            finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(runner)
        try:
            await finished.wait()
        finally:
            if not finished.is_set():
                budget.abort()
    if not outcome:
        raise TimeoutError("Upstream call was stopped.")
    ok, value = outcome[0]
    if ok:
        return value  # type: ignore[no-any-return]
    raise value


async def run_fetcher_call(
    func: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run a blocking Jira or Confluence fetcher call in a worker thread.

    Calls to one upstream site share that site's slots; calls to other sites
    do not wait for them. Each configured service site has threads of its
    own. Calls to request-supplied sites share a small pool of their own and
    raise ``TimeoutError`` past ``UNTRUSTED_CALL_TIMEOUT``.
    """
    url = _call_url(func, args, kwargs)
    key = upstream_key(url) if url else ""
    trusted = url is None or is_trusted_upstream(url)
    pool = _site_pool(url, key, trusted)
    timeout = None if trusted else UNTRUSTED_CALL_TIMEOUT
    slots = _checkout_slots(pool, key)
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        # The deadline covers the wait for a slot as well as the call itself.
        with anyio.move_on_after(timeout):
            async with slots.limiter:
                return await _run_in_thread(
                    partial(func, *args, **kwargs), pool.threads, deadline
                )
    finally:
        _release_slots(pool, key, slots)
    raise TimeoutError(f"Upstream call did not finish within {timeout:g} seconds.")


URL_CHECK_BUSY_MESSAGE = "Server busy checking request URLs; retry shortly."


class UrlCheckBusy(Exception):  # noqa: N818 - reads as a state
    """Every address-check thread of the URL's trust class is in use."""


def _url_check_semaphore(trusted: bool) -> threading.BoundedSemaphore:
    with _url_check_lock:
        size, sem = _url_check_threads.get(trusted, (0, None))  # type: ignore[assignment]
        if sem is None or size != URL_CHECK_WORKERS:
            # Checks still running release the semaphore they took.
            sem = threading.BoundedSemaphore(URL_CHECK_WORKERS)
            _url_check_threads[trusted] = (URL_CHECK_WORKERS, sem)
        return sem


async def run_url_check(url: str) -> str | None:
    """Check a request-supplied URL for SSRF, including its DNS lookup.

    The lookup cannot be interrupted, so each trust class (see
    :func:`is_trusted_upstream`) has a few threads of its own, separate from
    the fetcher pools. A thread keeps its place until the lookup returns, so
    their number stays fixed; the request stops waiting after
    ``URL_CHECK_TIMEOUT`` seconds, and is refused at once while every place is
    taken.

    A lookup that runs past the deadline is answered like one that failed:
    refused, except for an ``MCP_ALLOWED_URL_DOMAINS`` host, which the
    connect-time pinning adapter checks again.

    Returns:
        None if the URL is safe, otherwise the reason it is refused.

    Raises:
        UrlCheckBusy: Every check thread of this trust class is in use; this
            is a server capacity limit, not a problem with the URL.
    """
    sem = _url_check_semaphore(is_trusted_upstream(url))
    if not sem.acquire(blocking=False):
        raise UrlCheckBusy(URL_CHECK_BUSY_MESSAGE)
    claim = threading.Lock()
    state = {"started": False, "dropped": False}

    def check() -> str | None:
        with claim:
            if state["dropped"]:
                return None
            state["started"] = True
        try:
            return validate_url_for_ssrf(url)
        finally:
            sem.release()

    try:
        with anyio.fail_after(URL_CHECK_TIMEOUT):
            return await anyio.to_thread.run_sync(
                check,
                abandon_on_cancel=True,
                limiter=anyio.CapacityLimiter(1),
            )
    except TimeoutError:
        hostname = (urlparse(url).hostname or "").lower()
        if _hostname_matches_allowlist(hostname, _get_domain_allowlist() or []):
            return None
        return f"DNS resolution failed for {hostname}"
    finally:
        with claim:
            if not state["started"]:
                state["dropped"] = True
                sem.release()
