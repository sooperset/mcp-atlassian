#!/usr/bin/env python3
"""Generate MDX documentation for all MCP tools.

Introspects the FastMCP server instances (jira_mcp, confluence_mcp) to extract
tool metadata, then renders per-category MDX pages via a Jinja2 template.

Usage:
    python scripts/generate_tool_docs.py           # generate docs/tools/*.mdx
    python scripts/generate_tool_docs.py --check   # verify mappings and counts

CI usage:
    python scripts/generate_tool_docs.py --check   # exits 1 on mapping/count drift
"""

from __future__ import annotations

import argparse
import asyncio
import re
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
        "jira_assign_issue",
        "jira_move_issue",
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
        "jira_get_project_issue_types",
        "jira_get_create_fields",
        "jira_get_project_fields",
        "jira_search_projects",
    ],
    "jira-agile": [
        "jira_get_agile_boards",
        "jira_get_board_issues",
        "jira_get_sprints_from_board",
        "jira_get_sprint_issues",
        "jira_create_sprint",
        "jira_update_sprint",
        "jira_add_issues_to_sprint",
        "jira_move_issues_to_backlog",
    ],
    "jira-comments-worklogs": [
        "jira_add_comment",
        "jira_edit_comment",
        "jira_get_worklog",
        "jira_add_worklog",
        "jira_batch_get_changelogs",
        "jira_get_user_profile",
        "jira_search_assignable_users",
        "jira_get_issue_watchers",
        "jira_add_watcher",
        "jira_remove_watcher",
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
        "jira_update_version",
        "jira_get_project_epic_hierarchy",
        "jira_get_cross_project_dependencies",
    ],
    "jira-attachments": [
        "jira_download_attachments",
        "jira_get_issue_images",
    ],
    "jira-service-desk": [
        "jira_get_service_desk_for_project",
        "jira_get_service_desk_queues",
        "jira_get_queue_issues",
        "jira_get_request_types",
        "jira_get_request_type_fields",
        "jira_create_customer_request",
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
        "confluence_get_space_page_tree",
        "confluence_get_page_history",
        "confluence_update_page_section",
        "confluence_move_page",
        "confluence_copy_page",
        "confluence_get_page_restrictions",
        "confluence_set_page_restrictions",
        "confluence_get_page_diff",
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
        "confluence_reply_to_comment",
        "confluence_get_inline_comments",
        "confluence_add_inline_comment",
        "confluence_get_labels",
        "confluence_add_label",
        "confluence_get_page_views",
    ],
    "confluence-permissions": [
        "confluence_check_content_permissions",
        "confluence_get_space_permissions",
    ],
    "confluence-templates": [
        "confluence_list_page_templates",
        "confluence_get_page_template",
        "confluence_create_page_from_template",
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
            "Issue links, epic links, remote links, versions, components, and "
            "cross-project and epic hierarchy analysis"
        ),
    },
    "jira-attachments": {
        "title": "Jira Attachments",
        "description": "Download attachments and render issue images",
    },
    "jira-service-desk": {
        "title": "Jira Service Desk",
        "description": "Customer requests, service desks, and queues",
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
    "confluence-permissions": {
        "title": "Confluence Permissions",
        "description": "Inspect content and space permissions",
    },
    "confluence-templates": {
        "title": "Confluence Templates",
        "description": "List page templates and create pages from them",
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
    notes: str | None = field(default=None, kw_only=True)
    examples: list[str] = field(default_factory=list, kw_only=True)

    @property
    def all_examples(self) -> list[str]:
        """Return legacy and list examples in rendering order."""
        return ([self.example] if self.example else []) + self.examples


@dataclass
class ToolDoc:
    """Processed documentation for a single tool."""

    name: str
    display_name: str
    description: str
    is_write: bool
    parameters: list[ToolParam] = field(default_factory=list)
    override: ToolOverride | None = None


@dataclass(frozen=True)
class ToolCounts:
    """Registered tool and toolset counts used in generated documentation."""

    total_tools: int
    jira_tools: int
    confluence_tools: int
    core_tools: int
    total_toolsets: int
    jira_toolsets: int
    confluence_toolsets: int
    core_toolsets: int


@dataclass
class ToolsetDoc:
    """A registered toolset and its introspected tools."""

    name: str
    core: bool
    description: str = ""
    tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CountRule:
    """A documented count expression and the registry metric it represents."""

    relative_path: str
    pattern: re.Pattern[str]
    metric: str
    group: int = 1


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

    jira_tools = await jira_mcp.list_tools()
    confluence_tools = await confluence_mcp.list_tools()

    all_tools: dict[str, dict[str, Any]] = {}

    for tool in jira_tools:
        prefixed = f"jira_{tool.name}"
        mcp_tool = tool.to_mcp_tool(name=prefixed)
        all_tools[prefixed] = {
            "mcp_tool": mcp_tool,
            "tags": tool.tags if hasattr(tool, "tags") else set(),
            "annotations": getattr(tool, "annotations", None),
            "is_write": "write" in (tool.tags if hasattr(tool, "tags") else set()),
        }

    for tool in confluence_tools:
        prefixed = f"confluence_{tool.name}"
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
            examples=data.get("examples") or [],
            tips=data.get("tips"),
            notes=data.get("notes"),
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


def get_tool_counts(tools: dict[str, dict[str, Any]]) -> ToolCounts:
    """Calculate tool and toolset counts from their live registries."""
    from mcp_atlassian.utils.toolsets import (
        ALL_TOOLSETS,
        CONFLUENCE_TOOLSETS,
        DEFAULT_TOOLSETS,
        JIRA_TOOLSETS,
        get_toolset_tag,
    )

    return ToolCounts(
        total_tools=len(tools),
        jira_tools=sum(name.startswith("jira_") for name in tools),
        confluence_tools=sum(name.startswith("confluence_") for name in tools),
        core_tools=sum(
            get_toolset_tag(info["tags"]) in DEFAULT_TOOLSETS for info in tools.values()
        ),
        total_toolsets=len(ALL_TOOLSETS),
        jira_toolsets=len(JIRA_TOOLSETS),
        confluence_toolsets=len(CONFLUENCE_TOOLSETS),
        core_toolsets=len(DEFAULT_TOOLSETS),
    )


def build_toolset_docs(
    tools: dict[str, dict[str, Any]],
) -> dict[str, list[ToolsetDoc]]:
    """Group introspected tools by the registered toolset definitions."""
    from mcp_atlassian.utils.toolsets import (
        ALL_TOOLSETS,
        CONFLUENCE_TOOLSETS,
        DEFAULT_TOOLSETS,
        JIRA_TOOLSETS,
        get_toolset_tag,
    )

    toolsets_by_name = {
        name: ToolsetDoc(
            name=name,
            core=name in DEFAULT_TOOLSETS,
            description=definition.description,
        )
        for name, definition in ALL_TOOLSETS.items()
    }
    for tool_name, info in tools.items():
        toolset_name = get_toolset_tag(info["tags"])
        if toolset_name not in toolsets_by_name:
            message = f"Tool '{tool_name}' references unknown toolset '{toolset_name}'"
            raise ValueError(message)
        toolsets_by_name[toolset_name].tools.append(tool_name)

    return {
        "jira": [toolsets_by_name[name] for name in JIRA_TOOLSETS],
        "confluence": [toolsets_by_name[name] for name in CONFLUENCE_TOOLSETS],
        "legacy": [toolsets_by_name["legacy"]],
    }


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------


def _escape_mdx_in_table(text: str) -> str:
    """Escape characters that break MDX parsing inside Markdown table cells.

    Curly braces are interpreted as JSX expressions by MDX. When they appear
    in table-cell descriptions (outside fenced code blocks), Mintlify silently
    fails to build the page. This wraps brace-containing segments in backticks
    so they render as inline code instead of being parsed as JSX.
    """
    if not text or ("{" not in text and "}" not in text):
        return text

    def find_matching_brace(start: int) -> int | None:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None

    escaped: list[str] = []
    in_code = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "`":
            in_code = not in_code
            escaped.append(char)
            index += 1
        elif char == "{" and not in_code:
            end = find_matching_brace(index)
            if end is None:
                escaped.append("&#123;")
                index += 1
            else:
                escaped.extend(("`", text[index : end + 1], "`"))
                index = end + 1
        elif char == "}" and not in_code:
            escaped.append("&#125;")
            index += 1
        else:
            escaped.append(char)
            index += 1

    return "".join(escaped)


def render_pages(
    category_docs: dict[str, list[ToolDoc]],
    toolset_docs: dict[str, list[ToolsetDoc]],
    counts: ToolCounts,
    template_dir: Path,
    output_dir: Path,
    reference_output: Path,
) -> dict[Path, str]:
    """Render category and tools-reference MDX pages without writing them."""
    env = Environment(  # noqa: S701 — MDX output, not HTML; autoescape not needed
        loader=FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["escape_pipe"] = lambda s: s.replace("|", "\\|") if s else s
    env.filters["escape_mdx"] = _escape_mdx_in_table
    category_template = env.get_template("tool_category.mdx.j2")
    reference_template = env.get_template("tools_reference.mdx.j2")

    rendered_pages: dict[Path, str] = {}

    for cat, tool_docs in category_docs.items():
        meta = CATEGORY_META[cat]
        rendered = category_template.render(
            category=meta,
            tools=tool_docs,
        )
        out_path = output_dir / f"{cat}.mdx"
        rendered_pages[out_path] = rendered

    rendered = reference_template.render(toolsets=toolset_docs, counts=counts)
    rendered_pages[reference_output] = rendered
    return rendered_pages


def generate_pages(
    category_docs: dict[str, list[ToolDoc]],
    toolset_docs: dict[str, list[ToolsetDoc]],
    counts: ToolCounts,
    template_dir: Path,
    output_dir: Path,
    reference_output: Path,
) -> None:
    """Render category and tools-reference MDX pages from Jinja2 templates."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for out_path, rendered in render_pages(
        category_docs,
        toolset_docs,
        counts,
        template_dir,
        output_dir,
        reference_output,
    ).items():
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


COUNT_RULES = (
    CountRule(
        "README.md",
        re.compile(r"\*\*(\d+)\s+tools?\s+total\*\*", re.IGNORECASE),
        "total_tools",
    ),
    CountRule(
        ".env.example",
        re.compile(r"Only core tools \(~?(\d+)\s+tools?\)", re.IGNORECASE),
        "core_tools",
    ),
    CountRule(
        ".env.example",
        re.compile(r"All (\d+)\s+toolsets? \((\d+)\s+tools?\)", re.IGNORECASE),
        "total_toolsets",
    ),
    CountRule(
        ".env.example",
        re.compile(r"All (\d+)\s+toolsets? \((\d+)\s+tools?\)", re.IGNORECASE),
        "total_tools",
        group=2,
    ),
    CountRule(
        ".env.example",
        re.compile(
            r"If unset, all toolsets are enabled \((\d+)\s+tools?\)",
            re.IGNORECASE,
        ),
        "total_tools",
    ),
    CountRule(
        "docs.json",
        re.compile(r"all (\d+)\s+tools? enabled by default", re.IGNORECASE),
        "total_tools",
    ),
    CountRule(
        "docs/tools-reference.mdx",
        re.compile(r'description: "Overview of all (\d+) MCP tools?', re.IGNORECASE),
        "total_tools",
    ),
    CountRule(
        "docs/tools-reference.mdx",
        re.compile(r"provides \*\*(\d+)\s+tools?\*\*", re.IGNORECASE),
        "total_tools",
    ),
    CountRule(
        "docs/tools-reference.mdx",
        re.compile(r"\*\*Jira Toolsets \((\d+)\):\*\*", re.IGNORECASE),
        "jira_toolsets",
    ),
    CountRule(
        "docs/tools-reference.mdx",
        re.compile(
            r"\*\*Confluence Toolsets \((\d+)\):\*\*",
            re.IGNORECASE,
        ),
        "confluence_toolsets",
    ),
    CountRule(
        "docs/tools-reference.mdx",
        re.compile(r"Enable all toolsets \((\d+)\s+tools?\)", re.IGNORECASE),
        "total_tools",
    ),
    CountRule(
        "docs/configuration.mdx",
        re.compile(
            r"core tools only \(~?(\d+)\s+tools? across (\d+)\s+core toolsets?\)",
            re.IGNORECASE,
        ),
        "core_tools",
    ),
    CountRule(
        "docs/configuration.mdx",
        re.compile(
            r"core tools only \(~?(\d+)\s+tools? across (\d+)\s+core toolsets?\)",
            re.IGNORECASE,
        ),
        "core_toolsets",
        group=2,
    ),
    CountRule(
        "docs/configuration.mdx",
        re.compile(
            r"default will change from all toolsets to (\d+)\s+core toolsets?"
            r"\s+only",
            re.IGNORECASE,
        ),
        "core_toolsets",
    ),
)

COUNT_FILES = tuple(dict.fromkeys(rule.relative_path for rule in COUNT_RULES))


def check_counts(tools: dict[str, dict[str, Any]]) -> bool:
    """Verify documented tool and toolset counts match live registries."""
    counts = get_tool_counts(tools)

    ok = True
    for rule in COUNT_RULES:
        path = ROOT / rule.relative_path
        text = path.read_text()
        matches = list(rule.pattern.finditer(text))
        if not matches:
            print(
                f"ERROR: {rule.relative_path}: no {rule.metric} count found",
                file=sys.stderr,
            )
            ok = False
            continue

        expected = getattr(counts, rule.metric)
        for match in matches:
            found = int(match.group(rule.group))
            line_number = text.count("\n", 0, match.start()) + 1
            if found != expected:
                print(
                    f"ERROR: {rule.relative_path}:{line_number}: found {found} "
                    f"for {rule.metric}, expected {expected}",
                    file=sys.stderr,
                )
                ok = False

    if ok:
        print(
            "OK: documented tool and toolset counts match the live registries "
            f"({counts.total_tools} tools, {counts.total_toolsets} toolsets)."
        )

    return ok


def _display_path(path: Path) -> str:
    """Return a repository-relative path when possible."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def check_generated_pages(
    category_docs: dict[str, list[ToolDoc]],
    toolset_docs: dict[str, list[ToolsetDoc]],
    counts: ToolCounts,
    template_dir: Path,
    output_dir: Path,
    reference_output: Path,
) -> bool:
    """Verify committed generated pages match a fresh render exactly."""
    rendered_pages = render_pages(
        category_docs,
        toolset_docs,
        counts,
        template_dir,
        output_dir,
        reference_output,
    )
    committed_paths = set(output_dir.glob("*.mdx"))
    committed_paths.add(reference_output)
    ok = True

    for path, rendered in rendered_pages.items():
        if not path.is_file():
            print(
                f"ERROR: generated documentation is missing: {_display_path(path)}",
                file=sys.stderr,
            )
        elif path.read_text() != rendered:
            print(
                f"ERROR: generated documentation is out of date: {_display_path(path)}",
                file=sys.stderr,
            )
        else:
            continue
        ok = False

    for path in sorted(committed_paths - set(rendered_pages)):
        print(
            f"ERROR: unexpected generated documentation file: {_display_path(path)}",
            file=sys.stderr,
        )
        ok = False

    if ok:
        print("OK: generated tool documentation is up to date.")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
OUTPUT_DIR = ROOT / "docs" / "tools"
OVERRIDES_DIR = ROOT / "docs" / "_overrides"
REFERENCE_OUTPUT = ROOT / "docs" / "tools-reference.mdx"


def main() -> None:
    """Entry point for tool documentation generation."""
    parser = argparse.ArgumentParser(
        description="Generate MDX tool reference documentation."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify tool mappings, counts, and generated pages (no files written).",
    )
    args = parser.parse_args()

    tools = asyncio.run(get_all_tools())

    if args.check:
        coverage_ok = check_coverage(tools)
        counts_ok = check_counts(tools)
        overrides = load_overrides(OVERRIDES_DIR)
        category_docs = build_tool_docs(tools, overrides)
        toolset_docs = build_toolset_docs(tools)
        counts = get_tool_counts(tools)
        generated_ok = check_generated_pages(
            category_docs,
            toolset_docs,
            counts,
            TEMPLATE_DIR,
            OUTPUT_DIR,
            REFERENCE_OUTPUT,
        )
        sys.exit(0 if coverage_ok and counts_ok and generated_ok else 1)

    overrides = load_overrides(OVERRIDES_DIR)
    category_docs = build_tool_docs(tools, overrides)
    toolset_docs = build_toolset_docs(tools)
    counts = get_tool_counts(tools)

    total = sum(len(docs) for docs in category_docs.values())
    print(
        f"Generating {len(category_docs)} category pages and tools reference "
        f"for {total} tools..."
    )
    generate_pages(
        category_docs,
        toolset_docs,
        counts,
        TEMPLATE_DIR,
        OUTPUT_DIR,
        REFERENCE_OUTPUT,
    )
    print("Done.")


if __name__ == "__main__":
    main()
