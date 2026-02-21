"""Schema compatibility tests for AI platform integration.

Validates that all MCP tool schemas conform to constraints required by
Vertex AI, Google ADK, LiteLLM, OpenAI gateways, and other AI platforms.

These tests run against the *raw* tool schemas (before server-level sanitization)
and the *sanitized* schemas (after ``_sanitize_schema_for_compatibility``), ensuring
the sanitizer correctly removes ``anyOf`` patterns that break Vertex AI while
keeping schemas valid.
"""

import json

import pytest
from mcp.types import Tool as MCPTool

from mcp_atlassian.servers.main import _sanitize_schema_for_compatibility, main_mcp

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def all_tool_schemas() -> dict[str, dict]:
    """Load and sanitize all tool schemas from both Jira and Confluence servers.

    Uses ``main_mcp.get_tools()`` to get prefixed tool names (e.g.,
    ``jira_get_issue``, ``confluence_get_page``) and applies the same
    ``_sanitize_schema_for_compatibility`` transform that the production
    ``_list_tools_mcp`` method uses.  No Atlassian credentials are needed
    since we only inspect schemas, not invoke tools.
    """
    import asyncio

    async def _load() -> dict[str, dict]:
        tools = await main_mcp.get_tools()
        schemas: dict[str, dict] = {}
        for name, tool_obj in tools.items():
            mcp_tool = tool_obj.to_mcp_tool(name=name)
            _sanitize_schema_for_compatibility(mcp_tool)
            schemas[name] = mcp_tool.inputSchema
        return schemas

    try:
        return asyncio.run(_load())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_load())
        finally:
            loop.close()


@pytest.fixture(scope="module")
def all_tool_names(all_tool_schemas: dict[str, dict]) -> list[str]:
    """Sorted list of all tool names for parametrization."""
    return sorted(all_tool_schemas.keys())


def _get_tool_names() -> list[str]:
    """Helper to get tool names for parametrize (runs at collection time)."""
    import asyncio

    async def _load() -> list[str]:
        tools = await main_mcp.get_tools()
        return sorted(tools.keys())

    # Use asyncio.run() which creates a fresh event loop
    # This is safe at collection time (before any test event loop exists)
    try:
        return asyncio.run(_load())
    except RuntimeError:
        # Fallback: create a new loop explicitly if needed
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_load())
        finally:
            loop.close()


ALL_TOOL_NAMES = _get_tool_names()


# ---------------------------------------------------------------------------
# Schema constraint tests (parametrized over every tool)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
def test_no_anyof_in_schema(tool_name: str, all_tool_schemas: dict[str, dict]) -> None:
    """Vertex AI / Google ADK reject ``anyOf`` alongside ``default``/``description``.

    After sanitization, no tool schema should contain ``anyOf`` anywhere.
    """
    schema_json = json.dumps(all_tool_schemas[tool_name])
    assert "anyOf" not in schema_json, (
        f"Tool '{tool_name}' schema still contains 'anyOf' after sanitization"
    )


@pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
def test_has_parameters(tool_name: str, all_tool_schemas: dict[str, dict]) -> None:
    """OpenAI gateways / LiteLLM choke on zero-argument tools.

    Every tool must have at least one property in its input schema.
    """
    schema = all_tool_schemas[tool_name]
    properties = schema.get("properties", {})
    assert properties, f"Tool '{tool_name}' has no properties (zero-arg tool)"


@pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
def test_all_properties_have_type(
    tool_name: str, all_tool_schemas: dict[str, dict]
) -> None:
    """Vertex AI requires every property to have a ``type`` field.

    After sanitization, all properties must have an explicit ``type``.
    """
    schema = all_tool_schemas[tool_name]
    properties = schema.get("properties", {})
    for prop_name, prop_def in properties.items():
        if not isinstance(prop_def, dict):
            continue
        assert "type" in prop_def, (
            f"Tool '{tool_name}', property '{prop_name}' missing 'type' field"
        )


@pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
def test_no_defs(tool_name: str, all_tool_schemas: dict[str, dict]) -> None:
    """Some AI clients don't dereference ``$defs``.

    Ensure no tool schema contains ``$defs`` or ``$ref`` at top level.
    """
    schema = all_tool_schemas[tool_name]
    assert "$defs" not in schema, f"Tool '{tool_name}' schema contains '$defs'"


@pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
def test_schema_is_object(tool_name: str, all_tool_schemas: dict[str, dict]) -> None:
    """All input schemas must be of type ``object``."""
    schema = all_tool_schemas[tool_name]
    assert schema.get("type") == "object", (
        f"Tool '{tool_name}' schema type is '{schema.get('type')}', expected 'object'"
    )


# ---------------------------------------------------------------------------
# Sanitizer unit tests
# ---------------------------------------------------------------------------


class TestSanitizeSchemaForCompatibility:
    """Unit tests for ``_sanitize_schema_for_compatibility``."""

    def _make_tool(self, properties: dict) -> MCPTool:
        """Create a minimal MCPTool-like object with the given properties."""
        return MCPTool(
            name="test_tool",
            description="test",
            inputSchema={
                "type": "object",
                "properties": properties,
            },
        )

    def test_flattens_simple_nullable_string(self) -> None:
        """``str | None`` → ``{"type": "string"}``."""
        tool = self._make_tool(
            {
                "foo": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "description": "test",
                }
            }
        )
        _sanitize_schema_for_compatibility(tool)
        prop = tool.inputSchema["properties"]["foo"]
        assert prop["type"] == "string"
        assert "anyOf" not in prop
        assert prop["default"] is None
        assert prop["description"] == "test"

    def test_flattens_simple_nullable_integer(self) -> None:
        """``int | None`` → ``{"type": "integer"}``."""
        tool = self._make_tool(
            {
                "bar": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                    "default": None,
                }
            }
        )
        _sanitize_schema_for_compatibility(tool)
        prop = tool.inputSchema["properties"]["bar"]
        assert prop["type"] == "integer"
        assert "anyOf" not in prop

    def test_flattens_simple_nullable_boolean(self) -> None:
        """``bool | None`` → ``{"type": "boolean"}``."""
        tool = self._make_tool(
            {
                "flag": {
                    "anyOf": [{"type": "boolean"}, {"type": "null"}],
                }
            }
        )
        _sanitize_schema_for_compatibility(tool)
        prop = tool.inputSchema["properties"]["flag"]
        assert prop["type"] == "boolean"
        assert "anyOf" not in prop

    def test_preserves_non_nullable_property(self) -> None:
        """Properties without ``anyOf`` are untouched."""
        tool = self._make_tool(
            {"name": {"type": "string", "description": "required name"}}
        )
        _sanitize_schema_for_compatibility(tool)
        prop = tool.inputSchema["properties"]["name"]
        assert prop == {"type": "string", "description": "required name"}

    def test_preserves_complex_anyof(self) -> None:
        """Complex ``anyOf`` with multiple non-null types is NOT flattened."""
        tool = self._make_tool(
            {
                "data": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                        {"type": "null"},
                    ],
                }
            }
        )
        _sanitize_schema_for_compatibility(tool)
        prop = tool.inputSchema["properties"]["data"]
        # Should remain untouched since there are 2 non-null types
        assert "anyOf" in prop

    def test_handles_empty_schema(self) -> None:
        """Empty inputSchema doesn't crash."""
        tool = MCPTool(name="empty", description="test", inputSchema={})
        result = _sanitize_schema_for_compatibility(tool)
        assert result is tool  # Returns same object

    def test_handles_no_properties(self) -> None:
        """Schema with no properties key doesn't crash."""
        tool = MCPTool(
            name="no_props",
            description="test",
            inputSchema={"type": "object"},
        )
        result = _sanitize_schema_for_compatibility(tool)
        assert result is tool

    def test_returns_same_tool_instance(self) -> None:
        """Sanitizer mutates and returns the same MCPTool instance."""
        tool = self._make_tool({"x": {"anyOf": [{"type": "string"}, {"type": "null"}]}})
        result = _sanitize_schema_for_compatibility(tool)
        assert result is tool


# ---------------------------------------------------------------------------
# Regression tests for narrowed parameter types
# ---------------------------------------------------------------------------


class TestNarrowedParameterRegression:
    """Verify that tools with narrowed parameter types accept both
    old-style (dict/list) and new-style (string) inputs correctly.

    These tests use ``_parse_additional_fields`` and the CSV parsing
    patterns directly, not the MCP server layer.
    """

    def test_parse_additional_fields_accepts_dict(self) -> None:
        """Backward compat: ``_parse_additional_fields`` still handles dict."""
        from mcp_atlassian.servers.jira import _parse_additional_fields

        result = _parse_additional_fields({"priority": {"name": "High"}})
        assert result == {"priority": {"name": "High"}}

    def test_parse_additional_fields_accepts_string(self) -> None:
        """New path: ``_parse_additional_fields`` handles JSON string."""
        from mcp_atlassian.servers.jira import _parse_additional_fields

        result = _parse_additional_fields('{"labels": ["ai", "test"]}')
        assert result == {"labels": ["ai", "test"]}

    def test_parse_additional_fields_accepts_none(self) -> None:
        """``None`` returns empty dict."""
        from mcp_atlassian.servers.jira import _parse_additional_fields

        result = _parse_additional_fields(None)
        assert result == {}

    def test_parse_additional_fields_rejects_invalid_json(self) -> None:
        """Invalid JSON string raises ``ValueError``."""
        from mcp_atlassian.servers.jira import _parse_additional_fields

        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_additional_fields("{invalid")

    def test_parse_additional_fields_rejects_non_dict_json(self) -> None:
        """JSON array raises ``ValueError``."""
        from mcp_atlassian.servers.jira import _parse_additional_fields

        with pytest.raises(ValueError, match="not a JSON object"):
            _parse_additional_fields('["a", "b"]')

    def test_csv_split_issue_keys(self) -> None:
        """CSV string splitting for issue keys works correctly."""
        csv = "PROJ-123, PROJ-456 , PROJ-789"
        result = [k.strip() for k in csv.split(",") if k.strip()]
        assert result == ["PROJ-123", "PROJ-456", "PROJ-789"]

    def test_csv_split_fields(self) -> None:
        """CSV string splitting for field names works correctly."""
        csv = "status, assignee, priority"
        result = [f.strip() for f in csv.split(",") if f.strip()]
        assert result == ["status", "assignee", "priority"]

    def test_csv_split_single_value(self) -> None:
        """Single value without commas still works."""
        csv = "PROJ-123"
        result = [k.strip() for k in csv.split(",") if k.strip()]
        assert result == ["PROJ-123"]

    def test_visibility_json_parse(self) -> None:
        """Visibility JSON string parsing works correctly."""
        import json

        visibility_str = '{"type":"group","value":"jira-users"}'
        parsed = json.loads(visibility_str)
        assert parsed == {"type": "group", "value": "jira-users"}

    def test_visibility_invalid_json_raises(self) -> None:
        """Invalid visibility JSON raises ``JSONDecodeError``."""
        import json

        with pytest.raises(json.JSONDecodeError):
            json.loads("{not valid}")

    def test_file_paths_csv_split(self) -> None:
        """CSV file paths splitting works correctly."""
        csv = "./file1.pdf, ./file2.png"
        result = [p.strip() for p in csv.split(",") if p.strip()]
        assert result == ["./file1.pdf", "./file2.png"]
