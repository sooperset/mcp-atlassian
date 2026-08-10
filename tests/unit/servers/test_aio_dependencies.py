"""Unit tests for the AIO Tests fetcher dependency provider."""

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from mcp_atlassian.aio import AIOFetcher
from mcp_atlassian.aio.config import AIOConfig
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.dependencies import get_aio_fetcher


@pytest.fixture
def global_config() -> AIOConfig:
    """Provide the global AIO Tests configuration."""
    return AIOConfig(
        url="https://tcms.aiojiraapps.com/aio-tcms/api/v1",
        auth_type="token",
        api_token="global-token",
    )


def make_context(config: AIOConfig | None) -> MagicMock:
    """Build a FastMCP context exposing the given AIO configuration.

    Args:
        config: Configuration to publish in the lifespan context.

    Returns:
        The mock context.
    """
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "app_lifespan_context": MainAppContext(full_aio_config=config)
    }
    return ctx


def make_request(headers: dict[str, str] | None = None) -> MagicMock:
    """Build a mock Starlette request with the given service headers.

    Args:
        headers: Service headers to expose on the request state.

    Returns:
        The mock request.
    """
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.aio_fetcher = None
    request.state.atlassian_service_headers = headers or {}
    return request


@pytest.mark.anyio
async def test_uses_global_config_outside_http(global_config):
    """Outside an HTTP request the global configuration is used."""
    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request",
        side_effect=RuntimeError("no request"),
    ):
        fetcher = await get_aio_fetcher(make_context(global_config))

    assert isinstance(fetcher, AIOFetcher)
    assert fetcher.config.api_token == "global-token"


@pytest.mark.anyio
async def test_missing_config_raises():
    """Without a configuration the tools cannot run."""
    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request",
        side_effect=RuntimeError("no request"),
    ):
        with pytest.raises(ValueError, match="AIO Tests client"):
            await get_aio_fetcher(make_context(None))


@pytest.mark.anyio
async def test_reuses_fetcher_from_request_state(global_config):
    """A fetcher already built for this request is reused."""
    existing = MagicMock(spec=AIOFetcher)
    request = make_request()
    request.state.aio_fetcher = existing

    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request", return_value=request
    ):
        fetcher = await get_aio_fetcher(make_context(global_config))

    assert fetcher is existing


@pytest.mark.anyio
async def test_header_token_overrides_global_token(global_config):
    """A per-request token replaces the global one."""
    request = make_request({"X-Aio-Api-Token": "user-token"})

    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request", return_value=request
    ):
        fetcher = await get_aio_fetcher(make_context(global_config))

    assert fetcher.config.api_token == "user-token"
    assert fetcher.config.auth_type == "token"
    assert fetcher.config.url == global_config.url
    assert request.state.aio_fetcher is fetcher


@pytest.mark.anyio
async def test_header_token_without_global_config_raises():
    """A per-request token still needs the global URL and SSL settings."""
    request = make_request({"X-Aio-Api-Token": "user-token"})

    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request", return_value=request
    ):
        with pytest.raises(ValueError, match="global configuration"):
            await get_aio_fetcher(make_context(None))


@pytest.mark.anyio
async def test_falls_back_to_global_without_header(global_config):
    """An HTTP request without the header uses the global configuration."""
    request = make_request()

    with patch(
        "mcp_atlassian.servers.dependencies.get_http_request", return_value=request
    ):
        fetcher = await get_aio_fetcher(make_context(global_config))

    assert fetcher.config.api_token == "global-token"
