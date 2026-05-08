"""Tests for privacy.stats — counters and pipeline aggregation."""

from __future__ import annotations

import json
import logging
import re

import pytest

from mcp_atlassian.privacy.config import PrivacyConfig
from mcp_atlassian.privacy.field_filter import FieldFilter
from mcp_atlassian.privacy.middleware import PrivacyFilterMiddleware
from mcp_atlassian.privacy.pii_redactor import RegexRedactor
from mcp_atlassian.privacy.pipeline import PrivacyPipeline
from mcp_atlassian.privacy.stats import FilterStats


class TestFilterStats:
    def test_defaults_zero(self) -> None:
        s = FilterStats()
        assert s.resources_dropped == 0
        assert s.fields_dropped == 0
        assert s.fields_masked == 0
        assert s.pii_redactions == 0
        assert s.total_changes == 0

    def test_total_changes_sums_all(self) -> None:
        s = FilterStats(
            resources_dropped=1,
            fields_dropped=2,
            fields_masked=3,
            pii_redactions=4,
        )
        assert s.total_changes == 10

    def test_summary_format(self) -> None:
        s = FilterStats(resources_dropped=1, pii_redactions=2)
        assert "resources_dropped=1" in s.summary()
        assert "pii_redactions=2" in s.summary()
        assert "fields_dropped=0" in s.summary()


class TestFieldFilterStats:
    def test_drop_counts_per_path(self) -> None:
        f = FieldFilter(
            drop_paths=["a.b", "c.d"],
            mask_paths=[],
            mask_token="X",
        )
        stats = FilterStats()
        f.apply(value={"a": {"b": 1, "x": 2}, "c": {"d": 3}}, stats=stats)
        assert stats.fields_dropped == 2

    def test_mask_counts_per_path(self) -> None:
        f = FieldFilter(
            drop_paths=[],
            mask_paths=["a.b", "c.d"],
            mask_token="X",
        )
        stats = FilterStats()
        f.apply(value={"a": {"b": 1}, "c": {"d": 2}}, stats=stats)
        assert stats.fields_masked == 2

    def test_drop_in_list_index_counts_each(self) -> None:
        f = FieldFilter(
            drop_paths=["items.*.secret"],
            mask_paths=[],
            mask_token="X",
        )
        stats = FilterStats()
        f.apply(
            value={"items": [{"secret": 1}, {"secret": 2}, {"keep": 3}]},
            stats=stats,
        )
        assert stats.fields_dropped == 2

    def test_drop_at_list_index_path_counts(self) -> None:
        f = FieldFilter(
            drop_paths=["items.0", "items.2"],
            mask_paths=[],
            mask_token="X",
        )
        stats = FilterStats()
        f.apply(value={"items": ["a", "b", "c", "d"]}, stats=stats)
        assert stats.fields_dropped == 2

    def test_mask_at_list_index_path_counts(self) -> None:
        f = FieldFilter(
            drop_paths=[],
            mask_paths=["items.1"],
            mask_token="[X]",
        )
        stats = FilterStats()
        f.apply(value={"items": ["a", "b", "c"]}, stats=stats)
        assert stats.fields_masked == 1


class TestRegexRedactorStats:
    def test_count_matches_replaced(self) -> None:
        r = RegexRedactor(patterns=[re.compile(r"\bsecret\b")], mask_token="X")
        stats = FilterStats()
        out = r.redact(
            value={"a": "one secret", "b": ["secret again", "also secret"]},
            stats=stats,
        )
        assert "secret" not in json.dumps(out)
        # 3 occurrences of the word "secret" across the structure.
        assert stats.pii_redactions == 3

    def test_no_matches_no_increment(self) -> None:
        r = RegexRedactor(patterns=[re.compile(r"\bsecret\b")], mask_token="X")
        stats = FilterStats()
        r.redact(value={"a": "nothing here"}, stats=stats)
        assert stats.pii_redactions == 0


class TestPipelineApplyWithStats:
    def test_aggregates_across_stages(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            deny_labels=["confidential"],
            drop_fields={"jira_issue_list": ["issues.*.assignee"]},
            mask_fields={"jira_issue_list": ["issues.*.summary"]},
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        payload = {
            "issues": [
                {
                    "key": "PROJ-1",
                    "labels": ["public"],
                    "summary": "ping alice@example.com",
                    "assignee": "alice",
                },
                {
                    "key": "PROJ-2",
                    "labels": ["confidential"],
                    "summary": "drop me",
                    "assignee": "bob",
                },
            ]
        }
        result, stats = pipeline.apply_with_stats(
            tool_name="jira_search", value=payload
        )
        assert stats.resources_dropped == 1  # PROJ-2
        assert stats.fields_dropped == 1  # PROJ-1.assignee
        assert stats.fields_masked == 1  # PROJ-1.summary
        # PII redaction ran AFTER masking; "ping alice@example.com" became
        # "[X]" via mask, so no email survived to redact. Confirm shape.
        assert result["issues"][0]["summary"] == "[X]"
        assert "assignee" not in result["issues"][0]

    def test_noop_returns_zero_stats(self) -> None:
        pipeline = PrivacyPipeline(config=PrivacyConfig(enabled=True))
        result, stats = pipeline.apply_with_stats(
            tool_name="jira_get_issue", value={"a": 1}
        )
        assert result == {"a": 1}
        assert stats.total_changes == 0


class TestMiddlewareLogsTelemetry:
    @pytest.mark.asyncio
    async def test_emits_one_debug_log_per_changed_call(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from typing import Any

        import mcp.types as mt
        from fastmcp.tools.tool import ToolResult

        config = PrivacyConfig(
            enabled=True, pii_pattern_names=["email"], mask_token="[X]"
        )
        middleware = PrivacyFilterMiddleware(pipeline=PrivacyPipeline(config=config))

        async def call_next(_: Any) -> ToolResult:
            return ToolResult(
                content=[mt.TextContent(type="text", text="alice@example.com")]
            )

        from dataclasses import dataclass

        @dataclass
        class _Msg:
            name: str

        @dataclass
        class _Ctx:
            message: _Msg

        with caplog.at_level(logging.DEBUG, logger="mcp_atlassian.privacy.middleware"):
            await middleware.on_call_tool(
                context=_Ctx(message=_Msg(name="jira_get_issue")),  # type: ignore[arg-type]
                call_next=call_next,
            )
        records = [
            r
            for r in caplog.records
            if r.name == "mcp_atlassian.privacy.middleware"
            and "privacy filter applied" in r.getMessage()
        ]
        assert len(records) == 1, (
            f"expected exactly one telemetry log line, got {len(records)}"
        )
        message = records[0].getMessage()
        assert "tool=jira_get_issue" in message
        assert "pii_redactions=1" in message

    @pytest.mark.asyncio
    async def test_no_log_when_no_changes(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from typing import Any

        import mcp.types as mt
        from fastmcp.tools.tool import ToolResult

        config = PrivacyConfig(
            enabled=True, pii_pattern_names=["email"], mask_token="[X]"
        )
        middleware = PrivacyFilterMiddleware(pipeline=PrivacyPipeline(config=config))

        async def call_next(_: Any) -> ToolResult:
            return ToolResult(content=[mt.TextContent(type="text", text="no pii here")])

        from dataclasses import dataclass

        @dataclass
        class _Msg:
            name: str

        @dataclass
        class _Ctx:
            message: _Msg

        with caplog.at_level(logging.DEBUG, logger="mcp_atlassian.privacy.middleware"):
            await middleware.on_call_tool(
                context=_Ctx(message=_Msg(name="jira_get_issue")),  # type: ignore[arg-type]
                call_next=call_next,
            )
        # No log when the pipeline made no changes — keeps logs quiet.
        applied = [
            r for r in caplog.records if "privacy filter applied" in r.getMessage()
        ]
        assert applied == []
