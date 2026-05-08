"""FastMCP middleware that runs the privacy pipeline on tool responses."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

import mcp.types as mt
from fastmcp.server.middleware.middleware import (
    CallNext,
    Middleware,
    MiddlewareContext,
)
from fastmcp.tools.tool import ToolResult

from .pipeline import PrivacyPipeline
from .stats import FilterStats

logger = logging.getLogger(__name__)


_Kind = Literal["dict", "wrap", "wrap_json_string"]


@dataclass(frozen=True)
class _Canonical:
    """Canonical input value extracted from FastMCP ``structured_content``,
    plus enough state to repack a filtered version back into the same
    output shape.

    FastMCP wraps non-dict tool returns as ``{"result": <value>}``. When
    ``<value>`` is a JSON-encoded string of a list/dict, the user's
    structured payload lives inside that string — parsing it lets resource
    and field rules apply to the actual structure.
    """

    value: Any
    kind: _Kind
    original_inner: str = ""  # only meaningful when kind == "wrap_json_string"

    @staticmethod
    def of(*, structured: dict[str, Any] | None) -> _Canonical | None:
        if structured is None:
            return None
        if not _is_result_wrap(structured=structured):
            return _Canonical(value=structured, kind="dict")
        return _Canonical._from_result_wrap(inner=structured["result"])

    @staticmethod
    def _from_result_wrap(*, inner: Any) -> _Canonical:
        if isinstance(inner, str):
            parsed = _try_parse_json(text=inner)
            if isinstance(parsed, dict | list):
                return _Canonical(
                    value=parsed,
                    kind="wrap_json_string",
                    original_inner=inner,
                )
        return _Canonical(value=inner, kind="wrap")

    def repack(self, *, filtered: Any) -> dict[str, Any]:
        if self.kind == "dict":
            # Pipeline preserves the dict shape it receives at the top level.
            return cast(dict[str, Any], filtered)
        if self.kind == "wrap":
            return {"result": filtered}
        # kind == "wrap_json_string": original_inner is set at construction
        # by _from_result_wrap to the JSON-string we'll re-serialize back into.
        return {"result": _reserialize(original=self.original_inner, filtered=filtered)}


class PrivacyFilterMiddleware(Middleware):
    """Filters every tool response through the configured privacy pipeline.

    Operates on serialized tool responses, not on upstream model classes —
    so it survives upstream model/mixin refactors. Unknown tools still get
    PII redaction (the field-rule lookup degrades gracefully via
    ``tool_map.resource_type_for_tool``).

    Telemetry: emits one structured ``DEBUG``-level log line per tool call
    when any change was made, summarising counters (resources dropped,
    fields dropped, fields masked, PII strings redacted). Calls where the
    pipeline made no changes are silent to keep logs quiet.

    FastMCP duplicates each tool return into BOTH ``structured_content``
    and a ``TextContent`` block (the latter is the JSON-serialized form
    for clients that don't read structured output). The middleware runs
    the pipeline exactly once on the canonical input value and projects
    the filtered result back into both outputs — otherwise stats would
    double-count and field rules would not reach into JSON-string returns.
    """

    def __init__(self, pipeline: PrivacyPipeline) -> None:
        self._pipeline: PrivacyPipeline = pipeline

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        if self._pipeline.is_noop:
            return result
        tool_name = context.message.name
        stats = FilterStats()
        filtered = self._filter_result(tool_name=tool_name, result=result, stats=stats)
        if stats.total_changes:
            logger.debug(
                "privacy filter applied: tool=%s %s",
                tool_name,
                stats.summary(),
            )
        return filtered

    def _filter_result(
        self, tool_name: str, result: ToolResult, stats: FilterStats
    ) -> ToolResult:
        canonical = _Canonical.of(structured=result.structured_content)
        if canonical is None:
            filtered_canonical: Any = None
            new_structured: dict[str, Any] | None = None
        else:
            filtered_canonical, call_stats = self._pipeline.apply_with_stats(
                tool_name=tool_name, value=canonical.value
            )
            _merge(into=stats, other=call_stats)
            new_structured = canonical.repack(filtered=filtered_canonical)
        new_content = self._filter_content_blocks(
            tool_name=tool_name,
            blocks=result.content,
            canonical=canonical,
            filtered_canonical=filtered_canonical,
            stats=stats,
        )
        if new_structured is None and not new_content:
            return result
        return ToolResult(
            content=new_content if new_content else None,
            structured_content=new_structured,
            meta=result.meta,
        )

    def _filter_content_blocks(
        self,
        tool_name: str,
        blocks: list[mt.ContentBlock],
        canonical: _Canonical | None,
        filtered_canonical: Any,
        stats: FilterStats,
    ) -> list[mt.ContentBlock]:
        out: list[mt.ContentBlock] = []
        for block in blocks:
            if isinstance(block, mt.TextContent):
                out.append(
                    self._filter_text_block(
                        tool_name=tool_name,
                        block=block,
                        canonical=canonical,
                        filtered_canonical=filtered_canonical,
                        stats=stats,
                    )
                )
            else:
                out.append(block)
        return out

    def _filter_text_block(
        self,
        tool_name: str,
        block: mt.TextContent,
        canonical: _Canonical | None,
        filtered_canonical: Any,
        stats: FilterStats,
    ) -> mt.TextContent:
        derived = self._derive_text(
            original_text=block.text,
            canonical=canonical,
            filtered_canonical=filtered_canonical,
        )
        new_text = (
            derived
            if derived is not None
            else self._filter_text(tool_name=tool_name, text=block.text, stats=stats)
        )
        if new_text == block.text:
            return block
        return block.model_copy(update={"text": new_text})

    @staticmethod
    def _derive_text(
        *,
        original_text: str,
        canonical: _Canonical | None,
        filtered_canonical: Any,
    ) -> str | None:
        """Re-derive a text block from the already-filtered canonical
        value when the original text is just FastMCP's serialization of
        that value. Returns ``None`` when no match is detectable, so the
        caller falls back to filtering the text independently.
        """
        if canonical is None or filtered_canonical is None:
            return None
        if isinstance(canonical.value, str) and original_text == canonical.value:
            return filtered_canonical if isinstance(filtered_canonical, str) else None
        parsed = _try_parse_json(text=original_text)
        if parsed is not None and parsed == canonical.value:
            return _reserialize(original=original_text, filtered=filtered_canonical)
        return None

    def _filter_text(self, tool_name: str, text: str, stats: FilterStats) -> str:
        parsed = _try_parse_json(text=text)
        if parsed is None:
            redacted, call_stats = self._pipeline.apply_with_stats(
                tool_name=tool_name, value=text
            )
            _merge(into=stats, other=call_stats)
            return redacted if isinstance(redacted, str) else text
        filtered, call_stats = self._pipeline.apply_with_stats(
            tool_name=tool_name, value=parsed
        )
        _merge(into=stats, other=call_stats)
        return _reserialize(original=text, filtered=filtered)


def _is_result_wrap(*, structured: dict[str, Any]) -> bool:
    return (
        isinstance(structured, dict) and len(structured) == 1 and "result" in structured
    )


def _try_parse_json(*, text: str) -> Any:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(s=stripped)
    except json.JSONDecodeError:
        return None


def _reserialize(*, original: str, filtered: Any) -> str:
    # Mirror the upstream tool-output style (indented, non-ASCII allowed)
    # so diffs are minimal for users inspecting raw text content.
    try:
        return json.dumps(obj=filtered, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        logger.warning(
            "Privacy filter could not re-serialize filtered output; "
            "returning original text."
        )
        return original


def _merge(*, into: FilterStats, other: FilterStats) -> None:
    """Add ``other``'s counters into ``into`` in place."""
    into.resources_dropped += other.resources_dropped
    into.fields_dropped += other.fields_dropped
    into.fields_masked += other.fields_masked
    into.pii_redactions += other.pii_redactions
