"""PII redaction over arbitrary nested JSON-like structures.

Two engines are available:

* :class:`RegexRedactor` (default) — applies the configured built-in and
  custom regexes to every string in the structure.
* :class:`PresidioRedactor` (opt-in) — uses Microsoft Presidio's
  :class:`AnalyzerEngine` if both ``PRIVACY_USE_PRESIDIO=true`` *and* the
  ``presidio-analyzer`` package is importable.

Selection is performed by :func:`build_redactor`. Install alone is a no-op;
the env var alone surfaces a clear error.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Protocol

from .config import PrivacyConfig
from .patterns import BUILTIN_PATTERNS
from .stats import FilterStats


class Redactor(Protocol):
    """Protocol for PII redactors."""

    def redact(self, value: Any, *, stats: FilterStats | None = None) -> Any:
        """Return ``value`` with PII recursively replaced by the mask token.

        When ``stats`` is provided, ``stats.pii_redactions`` is bumped by the
        number of regex/NER matches replaced.
        """
        ...


class RegexRedactor:
    """Regex-based redactor: applies a fixed set of compiled patterns."""

    def __init__(
        self,
        patterns: list[re.Pattern[str]],
        mask_token: str,
    ) -> None:
        self._patterns: list[re.Pattern[str]] = patterns
        self._mask_token: str = mask_token

    def redact(self, value: Any, *, stats: FilterStats | None = None) -> Any:
        return _walk(value=value, redact_string=self._redact_string, stats=stats)

    def _redact_string(self, value: str, stats: FilterStats | None) -> str:
        result = value
        for pattern in self._patterns:
            result, count = pattern.subn(repl=self._mask_token, string=result)
            if stats is not None and count:
                stats.pii_redactions += count
        return result


class PresidioRedactor:
    """Presidio-backed redactor for entity types regex cannot easily catch."""

    def __init__(self, mask_token: str) -> None:
        from presidio_analyzer import (
            AnalyzerEngine,  # type: ignore[import-not-found]  # noqa: PLC0415
        )

        self._mask_token: str = mask_token
        self._analyzer: AnalyzerEngine = AnalyzerEngine()

    def redact(self, value: Any, *, stats: FilterStats | None = None) -> Any:
        return _walk(value=value, redact_string=self._redact_string, stats=stats)

    def _redact_string(self, value: str, stats: FilterStats | None) -> str:
        results = self._analyzer.analyze(text=value, language="en")
        if not results:
            return value
        # Sort by start desc so character offsets remain valid as we mutate.
        ordered = sorted(results, key=lambda r: r.start, reverse=True)
        out = value
        for match in ordered:
            out = out[: match.start] + self._mask_token + out[match.end :]
        if stats is not None:
            stats.pii_redactions += len(results)
        return out


class CompositeRedactor:
    """Applies multiple redactors in sequence."""

    def __init__(self, redactors: list[Redactor]) -> None:
        self._redactors: list[Redactor] = redactors

    def redact(self, value: Any, *, stats: FilterStats | None = None) -> Any:
        result = value
        for redactor in self._redactors:
            result = redactor.redact(value=result, stats=stats)
        return result


def _walk(
    value: Any,
    redact_string: Callable[[str, FilterStats | None], str],
    stats: FilterStats | None,
) -> Any:
    if isinstance(value, str):
        return redact_string(value, stats)
    if isinstance(value, list):
        return [
            _walk(value=item, redact_string=redact_string, stats=stats)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _walk(value=item, redact_string=redact_string, stats=stats)
            for key, item in value.items()
        }
    return value


def build_redactor(config: PrivacyConfig) -> Redactor | None:
    """Construct the redactor matching ``config``.

    Returns ``None`` when no PII rules are configured. Raises if the user
    requested Presidio but the package is not installed.
    """
    redactors: list[Redactor] = []
    regex_patterns: list[re.Pattern[str]] = [
        BUILTIN_PATTERNS[name] for name in config.pii_pattern_names
    ]
    regex_patterns.extend(config.pii_custom_regex)
    if regex_patterns:
        redactors.append(
            RegexRedactor(patterns=regex_patterns, mask_token=config.mask_token)
        )
    if config.use_presidio:
        try:
            redactors.append(PresidioRedactor(mask_token=config.mask_token))
        except ImportError as exc:
            raise RuntimeError(
                "PRIVACY_USE_PRESIDIO=true but presidio-analyzer is not "
                "installed. Install with: "
                "uv add 'mcp-atlassian[privacy-nlp]' (or pip install "
                "presidio-analyzer)."
            ) from exc
    if not redactors:
        return None
    if len(redactors) == 1:
        return redactors[0]
    return CompositeRedactor(redactors=redactors)
