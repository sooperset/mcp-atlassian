"""Tests for inline-markup pairing boundaries in the Jira wiki converter.

Jira inline markup never spans lines and never has an empty body, so the
converter must not pair delimiters across newlines or collapse adjacent
empty pairs (`++`, `__`, `**`) that occur inside literal text such as
UTC offsets ("+00:00", "+0300") or double-underscore env keys
("Ppc__Enabled").
"""

from mcp_atlassian.preprocessing.jira import JiraPreprocessor


def _to_markdown(text: str) -> str:
    return JiraPreprocessor(
        base_url="https://jira.example.com", disable_translation=False
    ).jira_to_markdown(text)


def test_plus_signs_on_different_lines_are_not_paired():
    text = (
        'as is\n"2026-11-09T03:00:00.0000000+00:00"\n'
        'to be\n"2026-08-11 11:46:40.682 +0300"'
    )
    result = _to_markdown(text)

    assert "<ins>" not in result
    assert "+00:00" in result
    assert "+0300" in result


def test_underline_within_one_line_still_converts():
    result = _to_markdown("see +underlined+ text")
    assert "<ins>underlined</ins>" in result


def test_adjacent_plus_signs_are_left_alone():
    result = _to_markdown("counter ++ 5")
    assert "<ins>" not in result
    assert "++" in result


def test_double_underscore_in_env_key_is_not_italic():
    result = _to_markdown("set Ppc__Enabled=true to turn it on")
    assert result == "set Ppc__Enabled=true to turn it on"


def test_adjacent_asterisks_are_left_alone():
    result = _to_markdown("literal ** at the start")
    assert result == "literal ** at the start"


def test_real_bold_and_italic_still_convert():
    result = _to_markdown("*bold* and _italic_")
    assert "**bold**" in result
    assert "*italic*" in result
