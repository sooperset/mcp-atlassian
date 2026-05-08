"""Per-call filter statistics for visibility into what the filter changed.

Each :class:`FilterStats` instance is a mutable counter bag that the
filter stages bump as they make changes. The middleware constructs a
fresh instance per tool call, threads it through
:meth:`PrivacyPipeline.apply`, and emits a single structured log line
per call.

The counters are intentionally minimal — anything richer (per-rule
breakdowns, per-resource-type histograms) belongs in a follow-up
metrics layer rather than embedded here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FilterStats:
    """Mutable counters describing what one pipeline pass modified."""

    resources_dropped: int = 0
    """Whole resources removed by the resource-filter denylist (list items
    or top-level dicts)."""

    fields_dropped: int = 0
    """Field paths removed by ``PRIVACY_DROP_FIELDS``."""

    fields_masked: int = 0
    """Field paths replaced with the mask token by
    ``PRIVACY_MASK_FIELDS``."""

    pii_redactions: int = 0
    """Number of regex/Presidio matches replaced inside string values."""

    @property
    def total_changes(self) -> int:
        """Sum of all counters — convenient ``has_changes`` check."""
        return (
            self.resources_dropped
            + self.fields_dropped
            + self.fields_masked
            + self.pii_redactions
        )

    def summary(self) -> str:
        """One-line summary for log output."""
        return (
            f"resources_dropped={self.resources_dropped} "
            f"fields_dropped={self.fields_dropped} "
            f"fields_masked={self.fields_masked} "
            f"pii_redactions={self.pii_redactions}"
        )
