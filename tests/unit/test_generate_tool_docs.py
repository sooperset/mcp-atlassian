"""Unit tests for generated tool documentation helpers."""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from scripts.generate_tool_docs import (
    CATEGORY_META,
    TEMPLATE_DIR,
    ToolDoc,
    ToolOverride,
    ToolParam,
    _escape_mdx_in_table,
    load_overrides,
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
    """The upload example must use the registered content ID parameter."""
    overrides = load_overrides(Path("docs/_overrides"))
    example = overrides["confluence_upload_attachment"].example

    assert example is not None
    assert '"content_id"' in example
    assert '"page_id"' not in example


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
        override=ToolOverride(notes="Cloud-specific guidance."),
    )

    rendered = environment.get_template("tool_category.mdx.j2").render(
        category=CATEGORY_META["jira-issues"],
        tools=[tool],
    )

    assert 'Nested JSON: `{"outer": {"inner": "value"}}`' in rendered
    assert "<Note>\nCloud-specific guidance.\n</Note>" in rendered
