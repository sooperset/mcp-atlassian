"""Configuration dataclass for the privacy filter, loaded from environment."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .patterns import BUILTIN_PATTERNS

DEFAULT_MASK_TOKEN = "[REDACTED]"  # noqa: S105 — sentinel, not a password


def _parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_pattern_names(raw: str | None) -> list[str]:
    names = _parse_csv(raw=raw)
    unknown = [n for n in names if n not in BUILTIN_PATTERNS]
    if unknown:
        msg = (
            f"Unknown PRIVACY_PII_PATTERNS entries: {sorted(unknown)}. "
            f"Valid options: {sorted(BUILTIN_PATTERNS)}"
        )
        raise ValueError(msg)
    return names


def _parse_custom_regex(raw: str | None) -> list[re.Pattern[str]]:
    if not raw:
        return []
    patterns: list[re.Pattern[str]] = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        try:
            patterns.append(re.compile(entry))
        except re.error as exc:
            msg = f"Invalid PRIVACY_PII_CUSTOM_REGEX entry {entry!r}: {exc}"
            raise ValueError(msg) from exc
    return patterns


def _parse_field_map(raw: str | None, *, var_name: str) -> dict[str, list[str]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = (
            f"{var_name} must be valid JSON object mapping resource names "
            f"to lists of glob paths; got error: {exc}"
        )
        raise ValueError(msg) from exc
    if not isinstance(parsed, dict):
        msg = f"{var_name} must be a JSON object, got {type(parsed).__name__}"
        raise ValueError(msg)
    result: dict[str, list[str]] = {}
    for resource, paths in parsed.items():
        if not isinstance(resource, str):  # pragma: no cover
            # Defensive: JSON object keys are always strings per the spec.
            msg = f"{var_name} keys must be strings, got {type(resource).__name__}"
            raise ValueError(msg)
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            msg = f"{var_name}[{resource!r}] must be a list of strings"
            raise ValueError(msg)
        result[resource] = list(paths)
    return result


@dataclass(frozen=True)
class PrivacyConfig:
    """Resolved privacy-filter configuration.

    Built via :meth:`from_env` from ``PRIVACY_*`` environment variables. All
    rules are off by default; ``enabled`` is the master toggle.
    """

    enabled: bool = False
    pii_pattern_names: list[str] = field(default_factory=list)
    pii_custom_regex: list[re.Pattern[str]] = field(default_factory=list)
    use_presidio: bool = False
    deny_labels: list[str] = field(default_factory=list)
    deny_space_keys: list[str] = field(default_factory=list)
    deny_project_keys: list[str] = field(default_factory=list)
    drop_fields: dict[str, list[str]] = field(default_factory=dict)
    mask_fields: dict[str, list[str]] = field(default_factory=dict)
    mask_token: str = DEFAULT_MASK_TOKEN

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> PrivacyConfig:
        """Build a config from environment variables.

        Args:
            env: Optional explicit env mapping (used in tests). Defaults to
                ``os.environ``.

        Returns:
            Resolved ``PrivacyConfig``. Returns the disabled default when
            ``PRIVACY_FILTER_ENABLED`` is not truthy.

        Raises:
            ValueError: If any rule env var is malformed.
        """
        source = env if env is not None else os.environ
        if not _parse_bool(raw=source.get("PRIVACY_FILTER_ENABLED")):
            return cls()
        return cls(
            enabled=True,
            pii_pattern_names=_parse_pattern_names(
                raw=source.get("PRIVACY_PII_PATTERNS")
            ),
            pii_custom_regex=_parse_custom_regex(
                raw=source.get("PRIVACY_PII_CUSTOM_REGEX")
            ),
            use_presidio=_parse_bool(raw=source.get("PRIVACY_USE_PRESIDIO")),
            deny_labels=_parse_csv(raw=source.get("PRIVACY_DENY_LABELS")),
            deny_space_keys=_parse_csv(raw=source.get("PRIVACY_DENY_SPACE_KEYS")),
            deny_project_keys=_parse_csv(raw=source.get("PRIVACY_DENY_PROJECT_KEYS")),
            drop_fields=_parse_field_map(
                raw=source.get("PRIVACY_DROP_FIELDS"),
                var_name="PRIVACY_DROP_FIELDS",
            ),
            mask_fields=_parse_field_map(
                raw=source.get("PRIVACY_MASK_FIELDS"),
                var_name="PRIVACY_MASK_FIELDS",
            ),
            mask_token=source.get("PRIVACY_MASK_TOKEN", DEFAULT_MASK_TOKEN),
        )
