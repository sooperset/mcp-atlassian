"""Privacy filter pipeline — orchestrates the three filter stages."""

from __future__ import annotations

from typing import Any

from .config import PrivacyConfig
from .field_filter import build_field_filter
from .pii_redactor import Redactor, build_redactor
from .resource_filter import ResourceFilter
from .stats import FilterStats
from .tool_map import resource_type_for_tool


class PrivacyPipeline:
    """Applies (resource filter → field filter → PII redactor) in order.

    Order matters: resource filtering drops entire items first (cheap), then
    per-field rules apply to what remains, then PII redaction sweeps over
    every surviving string.
    """

    def __init__(self, config: PrivacyConfig) -> None:
        self._config: PrivacyConfig = config
        self._resource_filter: ResourceFilter = ResourceFilter(
            deny_labels=config.deny_labels,
            deny_space_keys=config.deny_space_keys,
            deny_project_keys=config.deny_project_keys,
        )
        self._redactor: Redactor | None = build_redactor(config=config)

    @property
    def is_noop(self) -> bool:
        """True when the pipeline has nothing to do regardless of input."""
        return (
            not self._resource_filter.has_rules
            and not self._config.drop_fields
            and not self._config.mask_fields
            and self._redactor is None
        )

    def apply(self, tool_name: str, value: Any) -> Any:
        """Run all configured filters for ``tool_name`` on ``value``."""
        result, _stats = self.apply_with_stats(tool_name=tool_name, value=value)
        return result

    def apply_with_stats(self, tool_name: str, value: Any) -> tuple[Any, FilterStats]:
        """Like :meth:`apply` but also returns per-call counters."""
        stats = FilterStats()
        if self.is_noop:
            return value, stats
        result = self._resource_filter.apply(value=value, stats=stats)
        result = self._field_filter_for(tool_name=tool_name).apply(
            value=result, stats=stats
        )
        if self._redactor is not None:
            result = self._redactor.redact(value=result, stats=stats)
        return result, stats

    def _field_filter_for(self, tool_name: str) -> Any:
        return build_field_filter(
            drop_fields=self._config.drop_fields,
            mask_fields=self._config.mask_fields,
            mask_token=self._config.mask_token,
            resource_type=resource_type_for_tool(tool_name=tool_name),
        )
