"""Tests for project dependency declarations."""

import re
from pathlib import Path


def test_fastmcp_minimum_version_supports_http_transport_and_dcr() -> None:
    """Keep the FastMCP floor at the tested HTTP transport/DCR release."""
    pyproject = Path("pyproject.toml").read_text()

    requirement = re.search(r'"fastmcp(?P<specifiers>[^\"]+)"', pyproject)
    assert requirement is not None

    lower_bound = re.search(
        r"(?:^|,)\s*>=\s*(?P<version>\d+(?:\.\d+)*)",
        requirement.group("specifiers"),
    )
    assert lower_bound is not None

    minimum_version = tuple(
        int(part) for part in lower_bound.group("version").split(".")
    )
    assert minimum_version >= (3, 4, 4)


def test_starlette_minimum_version_includes_host_header_fix() -> None:
    """Ensure Starlette includes the fixed Host header parsing behavior."""
    pyproject = Path("pyproject.toml").read_text()

    requirement = re.search(r'"starlette(?P<specifiers>[^\"]+)"', pyproject)
    assert requirement is not None

    lower_bound = re.search(
        r"(?:^|,)\s*>=\s*(?P<version>\d+(?:\.\d+)*)",
        requirement.group("specifiers"),
    )
    assert lower_bound is not None

    minimum_version = tuple(
        int(part) for part in lower_bound.group("version").split(".")
    )
    assert minimum_version >= (1, 0, 1)
