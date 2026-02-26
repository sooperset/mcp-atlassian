#!/usr/bin/env python3
"""Generate MDX documentation for all MCP tools.

Introspects the FastMCP server instances (jira_mcp, confluence_mcp) to extract
tool metadata, then renders per-category MDX pages via a Jinja2 template.

Usage:
    python scripts/generate_tool_docs.py           # generate docs/tools/*.mdx
    python scripts/generate_tool_docs.py --check   # verify all tools are mapped

CI usage:
    python scripts/generate_tool_docs.py --check   # exits 1 if any tool is undocumented
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

CATEGORY_TOOLS: dict[str, list[str]] = {
    "jira-issues": [
        "jira_get_issue",
        "jira_create_issue",
        "jira_update_issue",
        "jira_delete_issue",
        "jira_batch_create_issues",
        "jira_transition_issue",
        "jira_get_transitions",
        "jira_get_all_projects",
        "jira_get_project_issues",
    ],
    "jira-search-fields": [
        "jira_search",
        "jira_search_fields",
        "jira_get_field_options",
    ],
    "jira-agile": [
        "jira_get_agile_boards",
        "jira_get_board_issues",
        "jira_get_sprints_from_board",
        "jira_get_sprint_issues",
        "jira_create_sprint",
        "jira_update_sprint",
    ],
    "jira-comments-worklogs": [
        "jira_add_comment",
        "jira_edit_comment",
        "jira_get_worklog",
        "jira_add_worklog",
        "jira_batch_get_changelogs",
        "jira_get_user_profile",
    ],
    "jira-links-versions": [
        "jira_get_link_types",
        "jira_create_issue_link",
        "jira_remove_issue_link",
        "jira_link_to_epic",
        "jira_create_remote_issue_link",
        "jira_get_project_versions",
        "jira_get_project_components",
        "jira_create_version",
        "jira_batch_create_versions",
    ],
    "jira-attachments": [
        "jira_download_attachments",
        "jira_get_issue_images",
    ],
    "jira-service-desk": [
        "jira_get_service_desk_for_project",
        "jira_get_service_desk_queues",
        "jira_get_queue_issues",
    ],
    "jira-forms-metrics": [
        "jira_get_issue_proforma_forms",
        "jira_get_proforma_form_details",
        "jira_update_proforma_form_answers",
        "jira_get_issue_dates",
        "jira_get_issue_sla",
        "jira_get_issue_development_info",
        "jira_get_issues_development_info",
    ],
    "confluence-pages": [
        "confluence_get_page",
        "confluence_create_page",
        "confluence_update_page",
        "confluence_delete_page",
        "confluence_get_page_children",
        "confluence_get_page_history",
    ],
    "confluence-search": [
        "confluence_search",
        "confluence_search_user",
    ],
    "confluence-attachments": [
        "confluence_upload_attachment",
        "confluence_upload_attachments",
        "confluence_get_attachments",
        "confluence_download_attachment",
        "confluence_download_content_attachments",
        "confluence_delete_attachment",
        "confluence_get_page_images",
    ],
    "confluence-comments": [
        "confluence_add_comment",
        "confluence_get_comments",
        "confluence_get_labels",
        "confluence_add_label",
        "confluence_get_page_views",
    ],
}

CATEGORY_META: dict[str, dict[str, str]] = {
    "jira-issues": {
        "title": "Jira Issues",
        "description": ("Create, read, update, delete, and transition Jira issues"),
    },
    "jira-search-fields": {
        "title": "Jira Search & Fields",
        "description": ("Search issues with JQL, explore fields and field options"),
    },
    "jira-agile": {
        "title": "Jira Agile",
        "description": "Boards, sprints, and agile project management",
    },
    "jira-comments-worklogs": {
        "title": "Jira Comments & Worklogs",
        "description": ("Comments, worklogs, changelogs, and user profiles"),
    },
    "jira-links-versions": {
        "title": "Jira Links & Versions",
        "description": (
            "Issue links, epic links, remote links, versions, and components"
        ),
    },
    "jira-attachments": {
        "title": "Jira Attachments",
        "description": "Download attachments and render issue images",
    },
    "jira-service-desk": {
        "title": "Jira Service Desk",
        "description": "Service desk queues and queue issues",
    },
    "jira-forms-metrics": {
        "title": "Jira Forms & Metrics",
        "description": ("ProForma forms, SLA metrics, dates, and development info"),
    },
    "confluence-pages": {
        "title": "Confluence Pages",
        "description": ("Create, read, update, delete pages, and navigate page trees"),
    },
    "confluence-search": {
        "title": "Confluence Search",
        "description": "Search content with CQL and find users",
    },
    "confluence-attachments": {
        "title": "Confluence Attachments",
        "description": ("Upload, download, list, and manage page attachments"),
    },
    "confluence-comments": {
        "title": "Confluence Comments & Labels",
        "description": "Comments, labels, and page analytics",
    },
}

# Build reverse lookup: tool_name -> category (with duplicate detection)
_TOOL_TO_CATEGORY: dict[str, str] = {}
for _cat, _tools in CATEGORY_TOOLS.items():
    for _t in _tools:
        if _t in _TOOL_TO_CATEGORY:
            raise ValueError(
                f"Tool '{_t}' is mapped to both '{_TOOL_TO_CATEGORY[_t]}' and '{_cat}'"
            )
        _TOOL_TO_CATEGORY[_t] = _cat


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolParam:
    """A single tool parameter."""

    name: str
    type: str
    required: bool
    description: str


@dataclass
class ToolOverride:
    """Optional YAML sidecar overrides for a tool."""

    example: str | None = None
    tips: str | None = None
    platform_notes: str | None = None


@dataclass
class ToolDoc:
    """Processed documentation for a single tool."""

    name: str
    display_name: str
    description: str
    is_write: bool
    parameters: list[ToolParam] = field(default_factory=list)
    override: ToolOverride | None = None


# ---------------------------------------------------------------------------
# Tool introspection
# ---------------------------------------------------------------------------


def _resolve_type(schema: dict[str, Any]) -> str:
    """Extract a human-readable type string from a JSON Schema property."""
    if "anyOf" in schema:
        types = [
            t.get("type", "object") for t in schema["anyOf"] if t.get("type") != "null"
        ]
        return types[0] if types else "any"
    return schema.get("type", "object")


def _first_line(text: str | None) -> str:
    """Return the first non-empty line of a docstring."""
    if not text:
        return ""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _make_display_name(tool_name: str, annotations: Any) -> str:
    """Build a human-readable display name for a tool.

    Prefers the ``title`` from ToolAnnotations when available.
    Falls back to converting the prefixed tool name to title case.
    """
    title: str | None = None
    if annotations is not None:
        if hasattr(annotations, "title"):
            title = annotations.title
        elif isinstance(annotations, dict):
            title = annotations.get("title")
    if title:
        return title
    # Fallback: jira_get_issue -> Get Issue
    parts = tool_name.split("_")
    # Drop service prefix
    if parts and parts[0] in ("jira", "confluence"):
        parts = parts[1:]
    return " ".join(p.capitalize() for p in parts)


async def get_all_tools() -> dict[str, dict[str, Any]]:
    """Extract tools from both FastMCP server instances."""
    from mcp_atlassian.servers.confluence import confluence_mcp
    from mcp_atlassian.servers.jira import jira_mcp

    jira_tools = await jira_mcp.get_tools()
    confluence_tools = await confluence_mcp.get_tools()

    all_tools: dict[str, dict[str, Any]] = {}

    for name, tool in jira_tools.items():
        prefixed = f"jira_{name}"
        mcp_tool = tool.to_mcp_tool(name=prefixed)
        all_tools[prefixed] = {
            "mcp_tool": mcp_tool,
            "tags": tool.tags if hasattr(tool, "tags") else set(),
            "annotations": getattr(tool, "annotations", None),
            "is_write": "write" in (tool.tags if hasattr(tool, "tags") else set()),
        }

    for name, tool in confluence_tools.items():
        prefixed = f"confluence_{name}"
        mcp_tool = tool.to_mcp_tool(name=prefixed)
        all_tools[prefixed] = {
            "mcp_tool": mcp_tool,
            "tags": tool.tags if hasattr(tool, "tags") else set(),
            "annotations": getattr(tool, "annotations", None),
            "is_write": "write" in (tool.tags if hasattr(tool, "tags") else set()),
        }

    return all_tools


# ---------------------------------------------------------------------------
# Override loading
# ---------------------------------------------------------------------------


def load_overrides(overrides_dir: Path) -> dict[str, ToolOverride]:
    """Load YAML sidecar overrides from a directory."""
    overrides: dict[str, ToolOverride] = {}
    if not overrides_dir.is_dir():
        return overrides

    for yaml_file in sorted(overrides_dir.glob("*.yaml")):
        tool_name = yaml_file.stem
        with open(yaml_file) as f:
            data = yaml.safe_load(f) or {}
        overrides[tool_name] = ToolOverride(
            example=data.get("example"),
            tips=data.get("tips"),
            platform_notes=data.get("platform_notes"),
        )

    return overrides


# ---------------------------------------------------------------------------
# Tool processing
# ---------------------------------------------------------------------------


def build_tool_docs(
    tools: dict[str, dict[str, Any]],
    overrides: dict[str, ToolOverride],
) -> dict[str, list[ToolDoc]]:
    """Build per-category lists of ToolDoc objects."""
    category_docs: dict[str, list[ToolDoc]] = {cat: [] for cat in CATEGORY_TOOLS}

    for cat, tool_names in CATEGORY_TOOLS.items():
        for tool_name in tool_names:
            if tool_name not in tools:
                print(
                    f"WARNING: {tool_name} listed in category "
                    f"'{cat}' but not found in server",
                    file=sys.stderr,
                )
                continue

            info = tools[tool_name]
            mcp_tool = info["mcp_tool"]
            schema = mcp_tool.inputSchema or {}
            properties = schema.get("properties", {})
            required_set = set(schema.get("required", []))

            params: list[ToolParam] = []
            for pname, pschema in properties.items():
                desc = pschema.get("description", "")
                # Collapse multiline descriptions for table rendering
                desc = " ".join(desc.split())
                params.append(
                    ToolParam(
                        name=pname,
                        type=_resolve_type(pschema),
                        required=pname in required_set,
                        description=desc,
                    )
                )

            description = _first_line(mcp_tool.description)
            display_name = _make_display_name(tool_name, info["annotations"])

            doc = ToolDoc(
                name=tool_name,
                display_name=display_name,
                description=description,
                is_write=info["is_write"],
                parameters=params,
                override=overrides.get(tool_name),
            )
            category_docs[cat].append(doc)

    return category_docs


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------


def generate_pages(
    category_docs: dict[str, list[ToolDoc]],
    template_dir: Path,
    output_dir: Path,
) -> None:
    """Render MDX pages from tool docs and Jinja2 template."""
    env = Environment(  # noqa: S701 — MDX output, not HTML; autoescape not needed
        loader=FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["escape_pipe"] = lambda s: s.replace("|", "\\|") if s else s
    template = env.get_template("tool_category.mdx.j2")

    output_dir.mkdir(parents=True, exist_ok=True)

    for cat, tool_docs in category_docs.items():
        meta = CATEGORY_META[cat]
        rendered = template.render(
            category=meta,
            tools=tool_docs,
        )
        out_path = output_dir / f"{cat}.mdx"
        out_path.write_text(rendered)
        print(f"  wrote {out_path}")


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------


def check_coverage(tools: dict[str, dict[str, Any]]) -> bool:
    """Verify every registered tool is mapped to a category.

    Returns True if all tools are covered.
    """
    mapped_tools = set(_TOOL_TO_CATEGORY.keys())
    registered_tools = set(tools.keys())

    unmapped = registered_tools - mapped_tools
    stale = mapped_tools - registered_tools

    ok = True
    if unmapped:
        print(
            f"ERROR: {len(unmapped)} tool(s) not mapped to any category:",
            file=sys.stderr,
        )
        for t in sorted(unmapped):
            print(f"  - {t}", file=sys.stderr)
        ok = False

    if stale:
        print(
            f"WARNING: {len(stale)} tool(s) in category map but not registered:",
            file=sys.stderr,
        )
        for t in sorted(stale):
            print(f"  - {t}", file=sys.stderr)
        ok = False

    if ok:
        print(
            f"OK: all {len(registered_tools)} tools are mapped "
            f"across {len(CATEGORY_TOOLS)} categories."
        )

    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
OUTPUT_DIR = ROOT / "docs" / "tools"
OVERRIDES_DIR = ROOT / "docs" / "_overrides"


def main() -> None:
    """Entry point for tool documentation generation."""
    parser = argparse.ArgumentParser(
        description="Generate MDX tool reference documentation."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify all tools are mapped (no files written).",
    )
    args = parser.parse_args()

    tools = asyncio.run(get_all_tools())

    if args.check:
        sys.exit(0 if check_coverage(tools) else 1)

    overrides = load_overrides(OVERRIDES_DIR)
    category_docs = build_tool_docs(tools, overrides)

    total = sum(len(docs) for docs in category_docs.values())
    print(f"Generating {len(category_docs)} pages for {total} tools...")
    generate_pages(category_docs, TEMPLATE_DIR, OUTPUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
