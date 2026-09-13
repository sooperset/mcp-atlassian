"""Hermetic safety contracts for the MCP stdio readiness probe."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import mcp_wire_probe


def _staging_env() -> dict[str, str]:
    """Return placeholder staging values; no network is contacted."""
    return {
        "HOME": "/tmp/readiness-home",
        "PATH": "/usr/bin",
        "UNRELATED_SECRET": "must-not-be-inherited",
        "MCP_READINESS_JIRA_URL": "https://jira-staging.example.test",
        "MCP_READINESS_JIRA_PAT": "jira-placeholder",
        "MCP_READINESS_JIRA_ISSUE_KEY": "TEST-1",
        "MCP_READINESS_CONFLUENCE_URL": "https://wiki-staging.example.test",
        "MCP_READINESS_CONFLUENCE_PAT": "confluence-placeholder",
        "MCP_READINESS_CONFLUENCE_PAGE_ID": "12345",
    }


def test_staging_profile_enforces_read_only_and_30_rpm_default() -> None:
    """The live profile must fail closed with bounded Atlassian traffic."""
    profile = mcp_wire_probe.build_staging_profile(_staging_env())

    assert profile.max_rpm == 30
    assert profile.child_env["READ_ONLY_MODE"] == "true"
    assert profile.child_env["ATLASSIAN_REQUESTS_PER_SECOND"] == "0.5"
    assert profile.child_env["ATLASSIAN_MAX_CONCURRENT_REQUESTS"] == "1"
    assert profile.child_env["ATLASSIAN_RETRY_TOTAL"] == "0"
    assert profile.child_env["ATLASSIAN_OAUTH_PROXY_ENABLE"] == "false"
    assert profile.child_env["ENABLED_TOOLS"] == ("confluence_get_page,jira_get_issue")


@pytest.mark.parametrize("value", ["0", "31", "not-an-integer"])
def test_staging_profile_rejects_invalid_rate(value: str) -> None:
    """A caller cannot loosen or disable the live-system traffic limit."""
    env = _staging_env() | {"MCP_READINESS_MAX_RPM": value}

    with pytest.raises(ValueError, match="between 1 and 30"):
        mcp_wire_probe.build_staging_profile(env)


def test_staging_profile_requires_values_without_echoing_secrets() -> None:
    """Missing-value errors identify the variable but never another value."""
    env = _staging_env()
    secret = env.pop("MCP_READINESS_JIRA_PAT")

    with pytest.raises(ValueError) as exc_info:
        mcp_wire_probe.build_staging_profile(env)

    assert "MCP_READINESS_JIRA_PAT" in str(exc_info.value)
    assert secret not in str(exc_info.value)


def test_staging_profile_passes_only_approved_environment() -> None:
    """The server child receives no unrelated parent-process secrets."""
    profile = mcp_wire_probe.build_staging_profile(_staging_env())

    assert "UNRELATED_SECRET" not in profile.child_env
    assert "MCP_READINESS_JIRA_PAT" not in profile.child_env
    assert profile.child_env["JIRA_PERSONAL_TOKEN"] == "jira-placeholder"
    assert profile.child_env["CONFLUENCE_PERSONAL_TOKEN"] == ("confluence-placeholder")
    assert set(profile.child_env) <= (
        set(mcp_wire_probe.STAGING_INHERITED_ENV)
        | set(mcp_wire_probe.STAGING_ENV_MAP.values())
        | {
            "READ_ONLY_MODE",
            "ATLASSIAN_OAUTH_PROXY_ENABLE",
            "MCP_LOGGING_STDOUT",
            "TOOLSETS",
            "ENABLED_TOOLS",
            "ATLASSIAN_REQUESTS_PER_SECOND",
            "ATLASSIAN_MAX_CONCURRENT_REQUESTS",
            "ATLASSIAN_RETRY_TOTAL",
        }
    )


def test_staging_tool_gate_requires_exact_read_allowlist() -> None:
    """Unexpected or missing tools stop the probe before any live calls."""
    allowed = set(mcp_wire_probe.STAGING_ALLOWED_TOOLS)
    mcp_wire_probe._validate_staging_tools(allowed)

    with pytest.raises(RuntimeError, match="unexpected tools"):
        mcp_wire_probe._validate_staging_tools(allowed | {"jira_create_issue"})
    with pytest.raises(RuntimeError, match="missing required tools"):
        mcp_wire_probe._validate_staging_tools({"jira_get_issue"})


def test_sdk_field_supports_v1_and_v2_names() -> None:
    """Protocol evidence works across the MCP SDK naming boundary."""
    assert (
        mcp_wire_probe._sdk_field(
            SimpleNamespace(protocol_version="v1"),
            "protocol_version",
            "protocolVersion",
            default="unknown",
        )
        == "v1"
    )
    assert (
        mcp_wire_probe._sdk_field(
            SimpleNamespace(protocolVersion="v2"),
            "protocol_version",
            "protocolVersion",
            default="unknown",
        )
        == "v2"
    )


def test_expected_protocol_version_accepts_matching_lane() -> None:
    """A lane-specific expected protocol passes when negotiation matches."""
    mcp_wire_probe._validate_protocol_version("2025-11-25", "2025-11-25")
    mcp_wire_probe._validate_protocol_version("2025-11-25", None)


def test_expected_protocol_version_rejects_mismatch() -> None:
    """A lane fails clearly instead of silently testing another protocol."""
    with pytest.raises(RuntimeError, match="Expected MCP protocol 2026-07-28"):
        mcp_wire_probe._validate_protocol_version("2025-11-25", "2026-07-28")


def test_tool_expectations_accept_matching_listing() -> None:
    """Presence and absence expectations pass for a matching public listing."""
    mcp_wire_probe._validate_tool_expectations(
        {"jira_get_issue"},
        {"jira_get_issue"},
        {"jira_create_issue"},
    )


def test_tool_expectations_reject_missing_expected_tool() -> None:
    """A lane fails clearly when a required tool is not discoverable."""
    with pytest.raises(RuntimeError, match="Expected tools are missing"):
        mcp_wire_probe._validate_tool_expectations(
            set(),
            {"jira_get_issue"},
            set(),
        )


def test_tool_expectations_reject_visible_hidden_tool() -> None:
    """A lane fails clearly when policy exposes an expected-hidden tool."""
    with pytest.raises(RuntimeError, match="Expected-hidden tools are visible"):
        mcp_wire_probe._validate_tool_expectations(
            {"jira_create_issue"},
            set(),
            {"jira_create_issue"},
        )


def test_tool_expectations_reject_contradictory_configuration() -> None:
    """A caller cannot configure the same tool as both present and absent."""
    with pytest.raises(ValueError, match="cannot be both expected and absent"):
        mcp_wire_probe._validate_tool_expectations(
            {"jira_get_issue"},
            {"jira_get_issue"},
            {"jira_get_issue"},
        )


def test_installed_versions_are_sanitized_and_tolerate_missing_package() -> None:
    """Version evidence contains package metadata only and permits absence."""
    with patch.object(
        mcp_wire_probe,
        "package_version",
        side_effect=[
            "2.0.0",
            "2.0.0",
            "4.0.0b1",
            "4.0.0b1",
            mcp_wire_probe.PackageNotFoundError("cryptography"),
        ],
    ):
        versions = mcp_wire_probe._installed_versions()

    assert versions == {
        "mcp": "2.0.0",
        "mcp-types": "2.0.0",
        "fastmcp": "4.0.0b1",
        "fastmcp-slim": "4.0.0b1",
        "cryptography": None,
    }
    assert "MCP_READINESS_JIRA_PAT" not in json.dumps(versions)


def test_result_record_omits_response_content() -> None:
    """Recorded evidence contains types but no Atlassian response bodies."""
    result = SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(type="text", text="sensitive issue content")],
    )

    record = mcp_wire_probe._result_record("jira_get_issue", result)
    rendered = json.dumps(record)

    assert record == {
        "tool": "jira_get_issue",
        "is_error": False,
        "content_types": ["text"],
    }
    assert "sensitive issue content" not in rendered
