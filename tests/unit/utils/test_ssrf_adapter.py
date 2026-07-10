"""Regression tests for the SSRF DNS-pinning transport adapter (DNS rebinding).

These cover GHSA-49xv, GHSA-72fm, GHSA-489g: the validate-then-reconnect TOCTOU
where a rebinding host returns a public IP to ``validate_url_for_ssrf`` and a
private/metadata IP to the actual connection. The adapter resolves once, validates
that resolution, and connects to the same address — so there is no second
resolution to rebind.
"""

import socket
from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.utils.ssrf_adapter import (
    SsrfPinningAdapter,
    _pinned_create_connection,
)


def _gai_returning(ip: str):
    def gai(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]

    return gai


@pytest.mark.security_regression
def test_rebind_internal_address_refused_with_single_resolution():
    """A host resolving to a non-global address is refused, after exactly one
    resolution — the resolved address is the one that would be connected to."""
    calls = {"n": 0}

    def gai(host, port, *args, **kwargs):
        calls["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]

    with patch("mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo", side_effect=gai):
        with pytest.raises(OSError, match="non-global"):
            _pinned_create_connection(("rebind.attacker.test", 443))

    assert calls["n"] == 1


@pytest.mark.security_regression
@pytest.mark.parametrize("ip", ["169.254.169.254", "127.0.0.1", "10.0.0.5", "::1"])
def test_pinning_adapter_blocks_internal_through_real_stack(ip):
    """End-to-end through the mounted adapter and the real requests/urllib3 stack:
    a host resolving to an internal address is refused — proving the adapter is
    actually wired into the connection path (not a mock-only green)."""
    session = requests.Session()
    session.mount("https://", SsrfPinningAdapter())
    session.mount("http://", SsrfPinningAdapter())

    with patch(
        "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
        side_effect=_gai_returning(ip),
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="SSRF blocked"):
            session.get("https://rebind.attacker.test", timeout=5)


def test_global_address_connects_to_the_validated_ip():
    """A global address passes the gate and the connection targets that same IP
    (the pin) — not a re-resolved one."""
    connected = {"addr": None}

    class _FakeSock:
        def setsockopt(self, *a):
            pass

        def settimeout(self, *a):
            pass

        def bind(self, *a):
            pass

        def connect(self, sa):
            connected["addr"] = sa

        def close(self):
            pass

    with (
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
            side_effect=_gai_returning("93.184.216.34"),
        ),
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.socket",
            return_value=_FakeSock(),
        ),
    ):
        _pinned_create_connection(("example.com", 443))

    assert connected["addr"][0] == "93.184.216.34"
