"""Unit tests for shared server helpers."""

import logging

import pytest

from src.mcp_atlassian.servers.helpers import parse_include, resolve_transition


def test_parse_include_returns_valid_sections() -> None:
    """Parse comma-separated valid sections and ignore surrounding whitespace."""
    assert parse_include("summary, details", {"summary", "details"}) == {
        "summary",
        "details",
    }


def test_parse_include_all_returns_every_valid_section() -> None:
    """The all keyword expands to the complete valid section set."""
    valid_sections = {"summary", "details"}

    assert parse_include("all", valid_sections) == valid_sections


def test_parse_include_ignores_unknown_sections(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown sections are omitted and logged."""
    with caplog.at_level(logging.WARNING):
        result = parse_include("summary,unknown", {"summary"})

    assert result == {"summary"}
    assert "unknown" in caplog.text


def test_parse_include_none_returns_empty_set() -> None:
    """A missing include value does not request any sections."""
    assert parse_include(None, {"summary"}) == set()


@pytest.fixture
def transitions() -> list[dict[str, str]]:
    """Provide transitions for resolution tests."""
    return [
        {"id": "11", "name": "Start Progress"},
        {"id": "21", "name": "Done"},
    ]


def test_resolve_transition_by_name(
    transitions: list[dict[str, str]],
) -> None:
    """Resolve a transition using its name."""
    assert resolve_transition(transitions, "Done") == "21"


def test_resolve_transition_by_id(transitions: list[dict[str, str]]) -> None:
    """Resolve a transition using its exact ID."""
    assert resolve_transition(transitions, "11") == "11"


def test_resolve_transition_name_is_case_insensitive(
    transitions: list[dict[str, str]],
) -> None:
    """Transition names are matched without regard to case."""
    assert resolve_transition(transitions, "done") == "21"


def test_resolve_transition_not_found_lists_available_options(
    transitions: list[dict[str, str]],
) -> None:
    """An unresolved transition reports the available options."""
    with pytest.raises(ValueError, match=r"Start Progress \(11\).*Done \(21\)"):
        resolve_transition(transitions, "Missing")
