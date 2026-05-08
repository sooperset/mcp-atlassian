"""Tests for privacy.middleware."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import mcp.types as mt
import pytest
from fastmcp.tools.tool import ToolResult

from mcp_atlassian.privacy.config import PrivacyConfig
from mcp_atlassian.privacy.middleware import PrivacyFilterMiddleware
from mcp_atlassian.privacy.pipeline import PrivacyPipeline


@dataclass
class _FakeMessage:
    name: str


@dataclass
class _FakeContext:
    message: _FakeMessage


def _email_pipeline() -> PrivacyPipeline:
    return PrivacyPipeline(
        config=PrivacyConfig(
            enabled=True, pii_pattern_names=["email"], mask_token="[X]"
        )
    )


def _build_text_result(text: str) -> ToolResult:
    return ToolResult(content=[mt.TextContent(type="text", text=text)])


def _build_structured_result(data: dict[str, Any]) -> ToolResult:
    return ToolResult(structured_content=data)


@pytest.mark.asyncio
async def test_redacts_text_block_plain_string() -> None:
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())

    async def call_next(_: Any) -> ToolResult:
        return _build_text_result(text="ping alice@example.com")

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert isinstance(out.content[0], mt.TextContent)
    assert out.content[0].text == "ping [X]"


@pytest.mark.asyncio
async def test_redacts_text_block_json_string() -> None:
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())
    payload = {"email": "alice@example.com", "name": "Alice"}

    async def call_next(_: Any) -> ToolResult:
        return _build_text_result(text=json.dumps(payload))

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert isinstance(out.content[0], mt.TextContent)
    parsed = json.loads(out.content[0].text)
    assert parsed == {"email": "[X]", "name": "Alice"}


@pytest.mark.asyncio
async def test_redacts_structured_content() -> None:
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())

    async def call_next(_: Any) -> ToolResult:
        return _build_structured_result(data={"email": "alice@example.com"})

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert out.structured_content == {"email": "[X]"}


@pytest.mark.asyncio
async def test_noop_pipeline_returns_result_unchanged() -> None:
    pipeline = PrivacyPipeline(config=PrivacyConfig(enabled=True))
    middleware = PrivacyFilterMiddleware(pipeline=pipeline)
    original = _build_text_result(text="alice@example.com")

    async def call_next(_: Any) -> ToolResult:
        return original

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert out is original


@pytest.mark.asyncio
async def test_non_text_content_blocks_pass_through() -> None:
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())
    image = mt.ImageContent(type="image", data="abc", mimeType="image/png")
    text = mt.TextContent(type="text", text="alice@example.com")

    async def call_next(_: Any) -> ToolResult:
        return ToolResult(content=[image, text])

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert out.content[0] is image
    assert isinstance(out.content[1], mt.TextContent)
    assert out.content[1].text == "[X]"


@pytest.mark.asyncio
async def test_field_filter_uses_tool_name_for_resource_type() -> None:
    config = PrivacyConfig(
        enabled=True,
        drop_fields={"jira_issue": ["fields.reporter.emailAddress"]},
        mask_token="[X]",
    )
    middleware = PrivacyFilterMiddleware(pipeline=PrivacyPipeline(config=config))
    payload = {
        "fields": {
            "reporter": {
                "displayName": "Alice",
                "emailAddress": "alice@example.com",
            }
        }
    }

    async def call_next(_: Any) -> ToolResult:
        return _build_text_result(text=json.dumps(payload))

    out = await middleware.on_call_tool(
        context=_FakeContext(  # type: ignore[arg-type]
            message=_FakeMessage(name="jira_get_issue")
        ),
        call_next=call_next,
    )
    assert isinstance(out.content[0], mt.TextContent)
    parsed = json.loads(out.content[0].text)
    assert parsed == {"fields": {"reporter": {"displayName": "Alice"}}}


@pytest.mark.asyncio
async def test_returns_original_when_no_filterable_payload() -> None:
    """Empty content + no structured content → fall through unchanged."""
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())
    # ToolResult requires content xor structured non-None at construction;
    # empty list for content + non-None placeholder structured satisfies that,
    # then we manually clear structured to simulate a filter that emptied it.
    result = ToolResult(content=[], structured_content={})
    # Manually clear: simulate post-filter both-None state.
    result.structured_content = None  # type: ignore[assignment]

    async def call_next(_: Any) -> ToolResult:
        return result

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert out is result


@pytest.mark.asyncio
async def test_text_block_unchanged_returns_same_object() -> None:
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())

    async def call_next(_: Any) -> ToolResult:
        return _build_text_result(text="no pii here at all")

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    # No change → middleware should hand the same TextContent block back.
    assert isinstance(out.content[0], mt.TextContent)
    assert out.content[0].text == "no pii here at all"


@pytest.mark.asyncio
async def test_reserialize_falls_back_when_filtered_unserializable() -> None:
    """If the filtered structure can't be re-serialized, return original text."""
    from mcp_atlassian.privacy.pii_redactor import RegexRedactor

    class _BadRedactor(RegexRedactor):
        def __init__(self) -> None:
            super().__init__(patterns=[], mask_token="X")

        def redact(self, value: Any, *, stats: Any | None = None) -> Any:
            return {"k": object()}

    pipeline = _email_pipeline()
    pipeline._redactor = _BadRedactor()  # type: ignore[attr-defined]
    middleware = PrivacyFilterMiddleware(pipeline=pipeline)

    async def call_next(_: Any) -> ToolResult:
        return _build_text_result(text='{"a": "alice@example.com"}')

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert isinstance(out.content[0], mt.TextContent)
    assert out.content[0].text == '{"a": "alice@example.com"}'


@pytest.mark.asyncio
async def test_invalid_json_text_redacts_as_plain_string() -> None:
    middleware = PrivacyFilterMiddleware(pipeline=_email_pipeline())

    async def call_next(_: Any) -> ToolResult:
        return _build_text_result(text="{not real json with alice@example.com")

    out = await middleware.on_call_tool(
        context=_FakeContext(message=_FakeMessage(name="x")),  # type: ignore[arg-type]
        call_next=call_next,
    )
    assert isinstance(out.content[0], mt.TextContent)
    # Treated as plain string; only PII rule applies.
    assert "alice@example.com" not in out.content[0].text
    assert "[X]" in out.content[0].text
