"""Unit tests for generated tool documentation helpers."""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

import scripts.generate_tool_docs as generator
from scripts.generate_tool_docs import (
    CATEGORY_META,
    TEMPLATE_DIR,
    ToolCounts,
    ToolDoc,
    ToolOverride,
    ToolParam,
    ToolsetDoc,
    _escape_mdx_in_table,
    check_counts,
    check_generated_pages,
    load_overrides,
    render_pages,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            'Example: {"priority": {"name": "High"}}',
            'Example: `{"priority": {"name": "High"}}`',
        ),
        (
            'Already inline `{"key": {"nested": true}}`.',
            'Already inline `{"key": {"nested": true}}`.',
        ),
        (
            "Unmatched { brace.",
            "Unmatched &#123; brace.",
        ),
        (
            "Unmatched }.",
            "Unmatched &#125;.",
        ),
    ],
)
def test_escape_mdx_in_table_handles_json_braces(
    text: str,
    expected: str,
) -> None:
    """Escape nested JSON without creating malformed Markdown code spans."""
    assert _escape_mdx_in_table(text) == expected


def test_upload_attachment_override_matches_tool_parameter() -> None:
    """The upload examples must use the registered content ID parameter."""
    overrides = load_overrides(Path("docs/_overrides"))
    examples = overrides["confluence_upload_attachment"].examples

    assert len(examples) == 2
    assert all('"content_id"' in example for example in examples)
    assert all('"page_id"' not in example for example in examples)


def test_tool_override_preserves_legacy_positional_fields() -> None:
    """Adding list examples must not reorder the existing dataclass API."""
    override = ToolOverride(
        "legacy example",
        "legacy tips",
        "legacy platform notes",
        notes="legacy notes",
        examples=["additional example"],
    )

    assert override.example == "legacy example"
    assert override.tips == "legacy tips"
    assert override.notes == "legacy notes"
    assert override.platform_notes == "legacy platform notes"
    assert override.all_examples == ["legacy example", "additional example"]


def test_attachment_and_jira_guidance_are_preserved_in_overrides() -> None:
    """Important manual guidance survives documentation regeneration."""
    overrides = load_overrides(Path("docs/_overrides"))

    download_notes = overrides["confluence_download_attachment"].notes
    image_notes = overrides["confluence_get_page_images"].notes
    assert download_notes is not None
    assert image_notes is not None
    assert "CONFLUENCE_ATTACHMENT_DOWNLOAD_USE_V1" in download_notes
    assert "CONFLUENCE_ATTACHMENT_DOWNLOAD_USE_V1" in image_notes

    jira_tips = overrides["jira_update_issue"].tips
    assert jira_tips is not None
    assert "return_fields" in jira_tips


def _render_override_category(
    tmp_path: Path,
    category: str,
    tool_names: list[str],
) -> str:
    """Render one category using its checked-in overrides."""
    overrides = load_overrides(Path("docs/_overrides"))
    category_docs = {
        category: [
            ToolDoc(
                name=tool_name,
                display_name=tool_name,
                description="Tool description.",
                is_write=False,
                override=overrides[tool_name],
            )
            for tool_name in tool_names
        ]
    }
    counts = ToolCounts(
        total_tools=len(tool_names),
        jira_tools=len(tool_names) if category.startswith("jira-") else 0,
        confluence_tools=(len(tool_names) if category.startswith("confluence-") else 0),
        core_tools=0,
        total_toolsets=0,
        jira_toolsets=0,
        confluence_toolsets=0,
        core_toolsets=0,
    )
    output_dir = tmp_path / "docs" / "tools"
    rendered = render_pages(
        category_docs,
        {"jira": [], "confluence": []},
        counts,
        TEMPLATE_DIR,
        output_dir,
        tmp_path / "docs" / "tools-reference.mdx",
    )
    return rendered[output_dir / f"{category}.mdx"]


def test_jira_create_metadata_guidance_survives_page_regeneration(
    tmp_path: Path,
) -> None:
    """Generated Jira docs retain response fields, workflow, and examples."""
    output = _render_override_category(
        tmp_path,
        "jira-search-fields",
        ["jira_get_project_issue_types", "jira_get_create_fields"],
    )

    assert "ID, name, description, subtask flag" in output
    assert "untranslated name when Jira provides one" in output
    assert "field ID, name, required flag, and schema" in output
    assert "`jira_get_field_options`" in output
    assert "allowed values for a custom field" in output
    assert '{"project_key": "PROJ"}' in output
    assert '{"project_key": "PROJ", "issue_type_id": "10002"}' in output


def test_upload_attachment_examples_survive_page_regeneration(
    tmp_path: Path,
) -> None:
    """Generated Confluence docs retain both supported upload input forms."""
    output = _render_override_category(
        tmp_path,
        "confluence-attachments",
        ["confluence_upload_attachment"],
    )

    assert '"file_path": "/path/to/diagram.png"' in output
    assert '"content_base64": "SGVsbG8="' in output
    assert '"filename": "hello.txt"' in output


@pytest.mark.parametrize(
    ("category", "tool_name", "expected_example"),
    [
        (
            "confluence-comments",
            "confluence_reply_to_comment",
            '{"comment_id": "67890", "body": "Thanks for the feedback! '
            "I've updated the section.\"}",
        ),
        (
            "confluence-pages",
            "confluence_update_page_section",
            '{"page_id": "12345678", "heading_text": "Weekly Update", '
            '"new_content": "- Shipped v2.1\\n- Started v2.2 planning", '
            '"version_comment": "Weekly sync"}',
        ),
        (
            "confluence-pages",
            "confluence_move_page",
            '{"page_id": "12345678", "target_parent_id": "98765432"}',
        ),
        (
            "confluence-pages",
            "confluence_copy_page",
            '{"source_page_id": "12345678", "destination_space_key": "DOCS", '
            '"new_title": "Copied Runbook", "destination_parent_id": '
            '"98765432"}',
        ),
        (
            "confluence-pages",
            "confluence_get_page_diff",
            '{"page_id": "12345678", "from_version": 1, "to_version": 3}',
        ),
        (
            "confluence-permissions",
            "confluence_check_content_permissions",
            '{"content_id": "12345678", "user_identifier": '
            '"5b10a2844c20165700ede21g", "operation": "read"}',
        ),
        (
            "confluence-permissions",
            "confluence_get_space_permissions",
            '{"space_id": "98304", "limit": 50}',
        ),
        (
            "jira-issues",
            "jira_move_issue",
            '{"issue_key": "PROJ-123", "target_project_key": "OTHERPROJ"}',
        ),
        (
            "jira-issues",
            "jira_get_issue",
            '{"issue_key": "PROJ-123", "fields": "summary,status,assignee", '
            '"comment_limit": 5, "include": "remote_links,transitions"}',
        ),
    ],
)
def test_restored_examples_survive_page_regeneration(
    tmp_path: Path,
    category: str,
    tool_name: str,
    expected_example: str,
) -> None:
    """Regenerated pages retain every restored runnable JSON example."""
    output = _render_override_category(tmp_path, category, [tool_name])

    assert expected_example in output


@pytest.mark.parametrize(
    ("category", "tool_names"),
    [
        (
            "confluence-permissions",
            [
                "confluence_check_content_permissions",
                "confluence_get_space_permissions",
            ],
        ),
        (
            "confluence-templates",
            [
                "confluence_list_page_templates",
                "confluence_get_page_template",
                "confluence_create_page_from_template",
            ],
        ),
    ],
)
def test_cloud_only_guidance_survives_page_regeneration(
    tmp_path: Path,
    category: str,
    tool_names: list[str],
) -> None:
    """Generated pages retain Cloud-only and Server/Data Center guidance."""
    overrides = load_overrides(Path("docs/_overrides"))
    category_docs = {
        category: [
            ToolDoc(
                name=tool_name,
                display_name=tool_name,
                description="Tool description.",
                is_write=tool_name == "confluence_create_page_from_template",
                override=overrides[tool_name],
            )
            for tool_name in tool_names
        ]
    }
    counts = ToolCounts(
        total_tools=5,
        jira_tools=0,
        confluence_tools=5,
        core_tools=0,
        total_toolsets=2,
        jira_toolsets=0,
        confluence_toolsets=2,
        core_toolsets=0,
    )

    rendered = render_pages(
        category_docs,
        {"jira": [], "confluence": []},
        counts,
        TEMPLATE_DIR,
        tmp_path / "docs" / "tools",
        tmp_path / "docs" / "tools-reference.mdx",
    )
    output = rendered[tmp_path / "docs" / "tools" / f"{category}.mdx"]

    assert output.count("This tool is only available for Confluence Cloud.") == len(
        tool_names
    )
    assert output.count("raises `ValueError`") == len(tool_names)


def test_category_template_renders_notes_and_safe_nested_json() -> None:
    """Generated tables and note overrides remain valid MDX."""
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["escape_pipe"] = lambda value: (
        value.replace("|", "\\|") if value else value
    )
    environment.filters["escape_mdx"] = _escape_mdx_in_table
    tool = ToolDoc(
        name="example_tool",
        display_name="Example Tool",
        description="Example description.",
        is_write=False,
        parameters=[
            ToolParam(
                name="payload",
                type="string",
                required=True,
                description='Nested JSON: {"outer": {"inner": "value"}}',
            )
        ],
        override=ToolOverride(
            example='{"legacy": true}\n',
            examples=['{"list": true}\n'],
            notes="Cloud-specific guidance.",
        ),
    )

    rendered = environment.get_template("tool_category.mdx.j2").render(
        category=CATEGORY_META["jira-issues"],
        tools=[tool],
    )

    assert 'Nested JSON: `{"outer": {"inner": "value"}}`' in rendered
    assert '{"legacy": true}' in rendered
    assert '{"list": true}' in rendered
    assert "<Note>\nCloud-specific guidance.\n</Note>" in rendered


def _write_count_documents(root: Path, counts: ToolCounts) -> None:
    """Write count-bearing documents with the supplied registry values."""
    (root / "docs").mkdir()
    (root / "README.md").write_text(f"**{counts.total_tools} tools total**\n")
    (root / ".env.example").write_text(
        f"# Only core tools (~{counts.core_tools} tools)\n"
        f"# All {counts.total_toolsets} toolsets ({counts.total_tools} tools)\n"
        f"# If unset, all toolsets are enabled ({counts.total_tools} tools).\n"
    )
    (root / "docs.json").write_text(
        f'{{"description": "all {counts.total_tools} tools enabled by default"}}\n'
    )
    (root / "docs" / "tools-reference.mdx").write_text(
        f'---\ndescription: "Overview of all {counts.total_tools} MCP tools"\n---\n'
        f"MCP Atlassian provides **{counts.total_tools} tools**.\n"
        f"**Jira Toolsets ({counts.jira_toolsets}):**\n"
        f"**Confluence Toolsets ({counts.confluence_toolsets}):**\n"
        f"# Enable all toolsets ({counts.total_tools} tools)\n"
    )
    (root / "docs" / "configuration.mdx").write_text(
        f"# Restrict to core tools only (~{counts.core_tools} tools across "
        f"{counts.core_toolsets} core toolsets)\n"
        f"In v0.22.0, the default will change from all toolsets to "
        f"{counts.core_toolsets} core toolsets only.\n"
    )


@pytest.mark.parametrize(
    ("relative_path", "old_text", "new_text", "metric"),
    [
        ("README.md", "**100 tools total**", "**60 tools total**", "total_tools"),
        (
            ".env.example",
            "Only core tools (~20 tools)",
            "Only core tools (~100 tools)",
            "core_tools",
        ),
        (
            "docs/tools-reference.mdx",
            "**Jira Toolsets (18):**",
            "**Jira Toolsets (30):**",
            "jira_toolsets",
        ),
        (
            "docs/configuration.mdx",
            "6 core toolsets",
            "30 core toolsets",
            "core_toolsets",
        ),
        (
            "docs/configuration.mdx",
            "to 6 core toolsets only",
            "to 30 core toolsets only",
            "core_toolsets",
        ),
    ],
)
def test_check_counts_rejects_valid_number_in_wrong_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    relative_path: str,
    old_text: str,
    new_text: str,
    metric: str,
) -> None:
    """A valid registry count must still fail when used for another metric."""
    counts = ToolCounts(
        total_tools=100,
        jira_tools=60,
        confluence_tools=40,
        core_tools=20,
        total_toolsets=30,
        jira_toolsets=18,
        confluence_toolsets=12,
        core_toolsets=6,
    )
    _write_count_documents(tmp_path, counts)
    path = tmp_path / relative_path
    path.write_text(path.read_text().replace(old_text, new_text))

    monkeypatch.setattr(generator, "ROOT", tmp_path)
    monkeypatch.setattr(generator, "get_tool_counts", lambda tools: counts)

    assert not check_counts({})
    error = capsys.readouterr().err
    assert relative_path in error
    assert f"for {metric}" in error


def test_check_mode_rejects_stale_warning_core_toolset_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI check must validate the second core-toolset count as well."""
    counts = ToolCounts(
        total_tools=100,
        jira_tools=60,
        confluence_tools=40,
        core_tools=20,
        total_toolsets=30,
        jira_toolsets=18,
        confluence_toolsets=12,
        core_toolsets=6,
    )
    _write_count_documents(tmp_path, counts)
    path = tmp_path / "docs" / "configuration.mdx"
    path.write_text(
        path.read_text().replace(
            "to 6 core toolsets only",
            "to 30 core toolsets only",
        )
    )

    async def fake_get_all_tools() -> dict[str, dict[str, object]]:
        return {}

    monkeypatch.setattr(generator, "ROOT", tmp_path)
    monkeypatch.setattr(generator, "OVERRIDES_DIR", tmp_path / "overrides")
    monkeypatch.setattr(generator, "get_all_tools", fake_get_all_tools)
    monkeypatch.setattr(generator, "get_tool_counts", lambda tools: counts)
    monkeypatch.setattr(generator, "check_coverage", lambda tools: True)
    monkeypatch.setattr(generator, "build_tool_docs", lambda tools, overrides: {})
    monkeypatch.setattr(generator, "build_toolset_docs", lambda tools: {})
    monkeypatch.setattr(generator, "check_generated_pages", lambda *args: True)
    monkeypatch.setattr(generator.sys, "argv", ["generate_tool_docs.py", "--check"])

    with pytest.raises(SystemExit) as exc_info:
        generator.main()

    assert exc_info.value.code == 1
    assert "docs/configuration.mdx" in capsys.readouterr().err


def test_check_generated_pages_detects_stale_toolset_membership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freshness checks catch stale membership even when all counts are unchanged."""
    counts = ToolCounts(
        total_tools=1,
        jira_tools=1,
        confluence_tools=0,
        core_tools=1,
        total_toolsets=2,
        jira_toolsets=1,
        confluence_toolsets=1,
        core_toolsets=2,
    )
    category_docs = {
        "jira-issues": [
            ToolDoc(
                name="jira_example_tool",
                display_name="Example Tool",
                description="An example tool.",
                is_write=False,
            )
        ]
    }
    toolset_docs = {
        "jira": [
            ToolsetDoc(
                name="jira_issues",
                core=True,
                tools=["jira_example_tool"],
            )
        ],
        "confluence": [
            ToolsetDoc(name="confluence_pages", core=True),
        ],
    }
    output_dir = tmp_path / "docs" / "tools"
    reference_output = tmp_path / "docs" / "tools-reference.mdx"
    monkeypatch.setattr(generator, "ROOT", tmp_path)

    rendered = render_pages(
        category_docs,
        toolset_docs,
        counts,
        TEMPLATE_DIR,
        output_dir,
        reference_output,
    )
    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    reference_output.write_text(
        reference_output.read_text().replace("`jira_example_tool`", "`stale_jira_tool`")
    )

    assert not check_generated_pages(
        category_docs,
        toolset_docs,
        counts,
        TEMPLATE_DIR,
        output_dir,
        reference_output,
    )
