"""Tests for privacy.pii_redactor."""

from __future__ import annotations

import re
import sys
from typing import Any

import pytest

from mcp_atlassian.privacy.config import PrivacyConfig
from mcp_atlassian.privacy.pii_redactor import (
    CompositeRedactor,
    PresidioRedactor,
    RegexRedactor,
    build_redactor,
)


class TestRegexRedactor:
    def test_redacts_in_string(self) -> None:
        redactor = RegexRedactor(patterns=[re.compile(r"\bsecret\b")], mask_token="X")
        assert redactor.redact(value="my secret here") == "my X here"

    def test_redacts_in_list(self) -> None:
        redactor = RegexRedactor(patterns=[re.compile(r"\d+")], mask_token="N")
        assert redactor.redact(value=["a 1 b", "c 22 d"]) == ["a N b", "c N d"]

    def test_redacts_in_nested_dict(self) -> None:
        redactor = RegexRedactor(patterns=[re.compile(r"\d+")], mask_token="N")
        result = redactor.redact(value={"outer": {"inner": "id 42", "list": ["x 7"]}})
        assert result == {"outer": {"inner": "id N", "list": ["x N"]}}

    def test_passes_through_non_string_scalars(self) -> None:
        redactor = RegexRedactor(patterns=[], mask_token="X")
        assert redactor.redact(value=42) == 42
        assert redactor.redact(value=None) is None
        assert redactor.redact(value=True) is True

    def test_no_patterns_no_change(self) -> None:
        redactor = RegexRedactor(patterns=[], mask_token="X")
        assert redactor.redact(value="alice@example.com") == "alice@example.com"


class TestCompositeRedactor:
    def test_applies_in_order(self) -> None:
        first = RegexRedactor(patterns=[re.compile(r"alpha")], mask_token="A")
        second = RegexRedactor(patterns=[re.compile(r"beta")], mask_token="B")
        redactor = CompositeRedactor(redactors=[first, second])
        assert redactor.redact(value="alpha beta gamma") == "A B gamma"


class TestBuildRedactor:
    def test_returns_none_when_no_rules(self) -> None:
        config = PrivacyConfig(enabled=True)
        assert build_redactor(config=config) is None

    def test_regex_only_returns_regex_redactor(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[REDACTED]",
        )
        redactor = build_redactor(config=config)
        assert isinstance(redactor, RegexRedactor)
        assert (
            redactor.redact(value="alice@example.com")  # type: ignore[union-attr]
            == "[REDACTED]"
        )

    def test_custom_regex_only(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            pii_custom_regex=[re.compile(r"\bSEC-\d+\b")],
            mask_token="X",
        )
        redactor = build_redactor(config=config)
        assert redactor is not None
        assert redactor.redact(value="see SEC-123") == "see X"

    def test_presidio_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force the soft import to fail.
        monkeypatch.setitem(sys.modules, "presidio_analyzer", None)
        config = PrivacyConfig(enabled=True, use_presidio=True)
        with pytest.raises(RuntimeError, match="presidio-analyzer"):
            build_redactor(config=config)

    def test_presidio_plus_regex_returns_composite(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_analyzer_module = _install_fake_presidio(monkeypatch=monkeypatch)
        config = PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            use_presidio=True,
            mask_token="X",
        )
        redactor = build_redactor(config=config)
        assert isinstance(redactor, CompositeRedactor)
        # The fake redacts every "PERSON"; combined with regex email rule.
        out = redactor.redact(value="alice@example.com Bob")
        assert "alice@example.com" not in out
        assert fake_analyzer_module.calls > 0


class TestPresidioRedactor:
    def test_uses_analyzer_results_to_redact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_presidio(monkeypatch=monkeypatch)
        redactor = PresidioRedactor(mask_token="X")
        assert redactor.redact(value="hello Bob") == "hello X"

    def test_no_analyzer_results_returns_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_presidio(monkeypatch=monkeypatch, find_substring="Bob")
        redactor = PresidioRedactor(mask_token="X")
        # Text doesn't contain "Bob" → no analyzer hits → unchanged.
        assert redactor.redact(value="hello world") == "hello world"

    def test_walks_into_nested_structures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_presidio(monkeypatch=monkeypatch)
        redactor = PresidioRedactor(mask_token="X")
        result = redactor.redact(value={"name": "Bob", "id": 7})
        assert result == {"name": "X", "id": 7}

    def test_bumps_stats_per_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp_atlassian.privacy.stats import FilterStats

        _install_fake_presidio(monkeypatch=monkeypatch)
        redactor = PresidioRedactor(mask_token="X")
        stats = FilterStats()
        redactor.redact(
            value={"a": "Bob is here", "b": "Bob and Bob again"},
            stats=stats,
        )
        # Fake matches 1 + 2 occurrences of "Bob".
        assert stats.pii_redactions == 3


def _install_fake_presidio(
    monkeypatch: pytest.MonkeyPatch, find_substring: str = "Bob"
) -> Any:
    """Install a stub `presidio_analyzer` module exposing `AnalyzerEngine`."""
    import types

    module = types.ModuleType("presidio_analyzer")

    class _Result:
        def __init__(self, start: int, end: int) -> None:
            self.start: int = start
            self.end: int = end

    class _AnalyzerEngine:
        def __init__(self) -> None:
            pass

        def analyze(self, text: str, language: str) -> list[_Result]:
            module.calls += 1  # type: ignore[attr-defined]
            results: list[_Result] = []
            start = 0
            while True:
                idx = text.find(find_substring, start)
                if idx == -1:
                    break
                results.append(_Result(start=idx, end=idx + len(find_substring)))
                start = idx + len(find_substring)
            return results

    module.AnalyzerEngine = _AnalyzerEngine  # type: ignore[attr-defined]
    module.calls = 0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "presidio_analyzer", module)
    return module
