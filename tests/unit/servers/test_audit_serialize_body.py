"""Unit tests for ToolCallLoggingMiddleware._serialize_body method."""

import json

import pytest

from mcp_atlassian.servers.audit import ToolCallLoggingMiddleware


@pytest.fixture
def middleware() -> ToolCallLoggingMiddleware:
    """Create a middleware instance with default settings."""
    return ToolCallLoggingMiddleware()


@pytest.fixture
def middleware_short() -> ToolCallLoggingMiddleware:
    """Create a middleware instance with a short max_body_length."""
    return ToolCallLoggingMiddleware(max_body_length=64)


class TestSerializeBodyEmpty:
    """Tests for empty/None arguments returning '{}'."""

    def test_none_arguments(self, middleware: ToolCallLoggingMiddleware):
        assert middleware._serialize_body(None) == "{}"

    def test_empty_dict(self, middleware: ToolCallLoggingMiddleware):
        assert middleware._serialize_body({}) == "{}"


class TestSerializeBodyBasic:
    """Tests for basic JSON serialization."""

    def test_simple_arguments(self, middleware: ToolCallLoggingMiddleware):
        args = {"issue_key": "PROJ-123", "summary": "Test issue"}
        result = middleware._serialize_body(args)
        parsed = json.loads(result)
        assert parsed == args

    def test_single_line_output(self, middleware: ToolCallLoggingMiddleware):
        args = {"description": "line1\nline2\nline3"}
        result = middleware._serialize_body(args)
        assert "\n" not in result
        assert "\r" not in result

    def test_no_control_characters(self, middleware: ToolCallLoggingMiddleware):
        args = {"data": "has\ttab\x00null\x01soh\x1fus"}
        result = middleware._serialize_body(args)
        for ch in result:
            assert ch >= " " and ch != "\x7f", f"Control character found: {repr(ch)}"


class TestSerializeBodyTruncation:
    """Tests for body truncation behavior."""

    def test_no_truncation_within_threshold(
        self, middleware: ToolCallLoggingMiddleware
    ):
        args = {"key": "short value"}
        result = middleware._serialize_body(args)
        assert "...truncated" not in result

    def test_truncation_when_exceeds_threshold(
        self, middleware_short: ToolCallLoggingMiddleware
    ):
        # Create arguments whose str() representation exceeds 64 chars
        args = {"data": "x" * 100}
        result = middleware_short._serialize_body(args)
        assert result.endswith("...truncated")

    def test_truncated_body_length(self, middleware_short: ToolCallLoggingMiddleware):
        # Create arguments whose str() representation exceeds 64 chars
        args = {"data": "x" * 100}
        result = middleware_short._serialize_body(args)
        # The serialized portion should be exactly max_body_length chars
        # plus the "...truncated" suffix
        body_part = result[: -len("...truncated")]
        assert len(body_part) == 64

    def test_original_content_length_measured_before_json(
        self, middleware: ToolCallLoggingMiddleware
    ):
        # str({"k": "v"}) = "{'k': 'v'}" which is shorter than 2048
        # so no truncation should happen even if JSON is longer
        args = {"key": "value"}
        result = middleware._serialize_body(args)
        assert "...truncated" not in result

    def test_original_content_length_can_include_masked_values(
        self, middleware_short: ToolCallLoggingMiddleware
    ):
        """Truncation can use the incoming length after masking a secret."""
        masked_args = {"api_token": "abcd********wxyz"}

        result = middleware_short._serialize_body(
            masked_args,
            original_length=100,
        )

        assert result.endswith("...truncated")


class TestSerializeBodyNonSerializable:
    """Tests for non-serializable values using default=repr."""

    def test_non_serializable_value(self, middleware: ToolCallLoggingMiddleware):
        class Custom:
            def __repr__(self):
                return "Custom()"

        args = {"obj": Custom()}
        result = middleware._serialize_body(args)
        assert "Custom()" in result

    def test_set_value(self, middleware: ToolCallLoggingMiddleware):
        args = {"items": {1, 2, 3}}
        result = middleware._serialize_body(args)
        # Should not raise, set is serialized via repr
        assert result  # non-empty result
