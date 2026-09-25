"""
Atlassian Document Format (ADF) utilities.

This module provides utilities for converting between ADF and other formats.
Supports both ADF → plain text (for reading) and Markdown → ADF (for writing).
"""

import copy
import json
import re
from datetime import datetime, timezone
from typing import Any

_MEDIA_NODE_TYPES = frozenset({"media", "mediaSingle", "mediaGroup"})
_JIRA_ISSUE_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_/-])"
    r"([A-Z][A-Z0-9_]+-\d+(?:-\d+)*)"
    r"(?![A-Za-z0-9_/-])"
)
_VALID_STATUS_COLORS = frozenset(
    {"neutral", "purple", "blue", "red", "yellow", "green"}
)


def _append_text_nodes(
    nodes: list[dict[str, Any]],
    text: str,
    jira_base_url: str = "",
    marks: list[dict[str, Any]] | None = None,
) -> None:
    """Append text nodes, linking Jira issue keys when a base URL is known."""
    if not text:
        return

    normalized_base_url = jira_base_url.rstrip("/")
    if not normalized_base_url:
        node: dict[str, Any] = {"type": "text", "text": text}
        if marks:
            node["marks"] = marks
        nodes.append(node)
        return

    pos = 0
    for match in _JIRA_ISSUE_KEY_RE.finditer(text):
        if match.start() > pos:
            node = {"type": "text", "text": text[pos : match.start()]}
            if marks:
                node["marks"] = marks
            nodes.append(node)

        issue_key = match.group(1)
        link_marks = [
            *(marks or []),
            {
                "type": "link",
                "attrs": {"href": f"{normalized_base_url}/browse/{issue_key}"},
            },
        ]
        nodes.append({"type": "text", "text": issue_key, "marks": link_marks})
        pos = match.end()

    if pos < len(text):
        node = {"type": "text", "text": text[pos:]}
        if marks:
            node["marks"] = marks
        nodes.append(node)


# ADF's "code" mark excludes these per Atlassian's schema (subsup and
# textColor/underline aren't produced by this converter at all, so only
# the three actually reachable here are listed).
_CODE_INCOMPATIBLE_MARKS = frozenset({"em", "strong", "strike"})


def _apply_mark(
    nodes: list[dict[str, Any]], mark: dict[str, Any]
) -> list[dict[str, Any]]:
    """Add ``mark`` to every text node in ``nodes``, in place.

    Node types that don't carry marks in the ADF schema (``mention``,
    ``status``) are left untouched rather than getting an invalid marks
    array. Skips adding a duplicate if the node already has a mark of the
    same type (can happen when recursively nesting the same style twice).

    Also skips adding ``em``/``strong``/``strike`` to a node that already
    has a ``code`` mark: ADF's schema declares those mutually exclusive
    with ``code`` on the same text node, and Jira Cloud's API rejects the
    whole request with ``INVALID_INPUT`` if they're combined -- not a
    silent rendering glitch, a hard failure. This can only happen through
    recursive nesting (e.g. bold wrapping a code span, ``**foo `bar`
    baz**``): the outer ``strong`` mark gets layered on top of whatever
    the recursive parse produced, including the code-marked node for
    `` `bar` ``. Dropping the incompatible mark on just that node (while
    the surrounding plain-text segments still get it) is the correct
    outcome anyway -- Jira renders code spans in fixed monospace regardless
    of any emphasis mark, so there was never a visual difference to lose.
    """
    for node in nodes:
        if node.get("type") != "text":
            continue
        existing_marks = node.get("marks") or []
        if mark["type"] in _CODE_INCOMPATIBLE_MARKS and any(
            m.get("type") == "code" for m in existing_marks
        ):
            continue
        marks = node.setdefault("marks", [])
        if not any(m.get("type") == mark["type"] for m in marks):
            marks.append(mark)
    return nodes


def _apply_marks(
    nodes: list[dict[str, Any]], marks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply multiple marks (see :func:`_apply_mark`) to every text node."""
    for mark in marks:
        _apply_mark(nodes, mark)
    return nodes


_WORD_FLANKED_UNDERSCORE_RE = re.compile(r"[A-Za-z0-9]_[A-Za-z0-9]")


def _looks_like_embedded_identifier(text: str) -> bool:
    """True if ``text`` contains an underscore sandwiched between two word
    characters, e.g. ``some_variable``.

    Used to reject a single-underscore italic match whose captured span
    accidentally bridged over an unrelated identifier instead of wrapping a
    short, intentional phrase. This happens when some other token on the
    same line has a genuinely word-boundary-safe underscore (a leading
    underscore like ``_todo``, or a trailing one like ``rename_it_``) that
    the lazy ``.+?`` quantifier can pair up with across everything in
    between, e.g. ``Set _todo for later, then call some_helper_func, then
    rename it_ tomorrow.`` would otherwise italicize the entire middle
    span and eat the trailing underscore off an unrelated identifier. A
    real intentional italic phrase is virtually never going to contain
    what looks like its own embedded identifier, so this is a safe,
    narrow reject condition.
    """
    return bool(_WORD_FLANKED_UNDERSCORE_RE.search(text))


def _parse_nested(
    text: str, jira_base_url: str, marks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Recursively parse ``text`` for inline formatting, then add ``marks``
    on top of whatever the recursion produced.

    This is what lets emphasis nest -- e.g. the italic inside
    ``**_bold italic_**`` is recognized by the recursive call, and the
    outer ``strong`` mark is then layered onto that result, instead of the
    outer match swallowing the inner markers as literal text. Issue-key
    autolinking and any other inline pattern inside the span still runs
    normally since it goes through the same ``_parse_inline_formatting``
    entry point.
    """
    return _apply_marks(_parse_inline_formatting(text, jira_base_url), marks)


def _parse_inline_formatting(
    text: str, jira_base_url: str = ""
) -> list[dict[str, Any]]:
    """Parse inline Markdown formatting into ADF inline nodes.

    Handles: bold (**), italic (* or single _), combined bold+italic (***
    or ___), inline code (`), links ([text](url)), strikethrough (~~),
    Jira-flavored user mentions ([~accountid:ACCOUNT_ID] or
    @[Display Name](accountid:ACCOUNT_ID)), and status lozenges
    ({status:color=green|title=Done}). Emphasis nests recursively, so
    `**_bold italic_**` (or any other combination of the above) applies
    both marks correctly instead of the outer match swallowing the inner
    markers as literal text.

    Single-underscore italic requires a CommonMark-style word boundary on
    both sides (the `_` cannot be directly adjacent to a letter, digit, or
    another `_`), so `my_variable_name` stays fully literal instead of
    partially italicizing -- this is what makes plain identifiers safe
    without needing a code span. Double-underscore bold (`__text__`) is
    deliberately not supported: `**` already covers bold, and adding a
    second bold syntax would only add another way to get the boundary
    rule subtly wrong for no real benefit.

    Bare Jira issue keys are converted to links when ``jira_base_url`` is set.

    The [~accountid:...] mention syntax mirrors what Jira's v2 wiki text
    returns when a real ADF mention is read back, so the read and write paths
    are symmetric. The display-name syntax also includes the mention text in
    the ADF node.

    The {status:...} syntax follows Jira wiki markup conventions. ``color`` is
    optional and falls back to "neutral" when omitted or unrecognized.

    Args:
        text: Raw text potentially containing inline Markdown formatting.
        jira_base_url: Jira base URL used to link bare issue keys.

    Returns:
        List of ADF inline nodes (text nodes with optional marks, plus
        mention nodes when [~accountid:...] or
        @[Display Name](accountid:...) is present, plus status nodes when
        {status:...} is present).
    """
    if not text:
        return []

    nodes: list[dict[str, Any]] = []
    # Pattern order matters: mention before link, bold before italic,
    # code before others. Status sits after code so a backticked
    # `{status:...}` stays literal. The triple-marker bold+italic
    # alternatives sit before the plain bold pattern so "***x***"/"___x___"
    # are consumed whole instead of bold eating two of the three markers
    # and leaking the third one as literal text. Code sitting before the
    # underscore-italic pattern is also what keeps underscores inside a
    # code span (`my_code_here`) untouched: the code alternative consumes
    # the whole backticked span in one match, so the scanner never visits
    # those underscores as candidate emphasis delimiters -- the
    # word-boundary guards on the underscore-italic pattern itself are
    # what protect plain-text identifiers like my_var_name that are NOT
    # inside a code span.
    inline_re = re.compile(
        r"\[~accountid:(?P<wiki_mention_id>[^\]]+)\]"
        r"|@\[(?P<display_mention_text>[^\]]+)\]"
        r"\(accountid:(?P<display_mention_id>[^)]+)\)"
        r"|`(?P<code_inner>[^`]+)`"
        r"|\{status:(?:color=(?P<status_color>\w+)\|)?"
        r"title=(?P<status_title>[^}]+)\}"
        r"|\*\*\*(?P<bolditalic_star_inner>.+?)\*\*\*"
        r"|___(?P<bolditalic_us_inner>.+?)___"
        r"|\*\*(?P<bold_inner>.+?)\*\*"
        r"|~~(?P<strike_inner>.+?)~~"
        r"|\[(?P<link_text>[^\]]+)\]\((?P<link_href>[^)]+)\)"
        r"|(?<!\*)\*(?!\*)(?P<italic_inner>.+?)(?<!\*)\*(?!\*)"
        r"|(?<![A-Za-z0-9_])_(?!_)(?P<italic_us_inner>.+?)(?<!_)_(?![A-Za-z0-9_])"
    )

    pos = 0
    for m in inline_re.finditer(text):
        # Add any plain text before this match
        if m.start() > pos:
            plain = text[pos : m.start()]
            _append_text_nodes(nodes, plain, jira_base_url)

        if m.group("wiki_mention_id") is not None:
            nodes.append(
                {
                    "type": "mention",
                    "attrs": {"id": m.group("wiki_mention_id")},
                }
            )
        elif m.group("display_mention_id") is not None:
            nodes.append(
                {
                    "type": "mention",
                    "attrs": {
                        "id": m.group("display_mention_id"),
                        "text": f"@{m.group('display_mention_text')}",
                    },
                }
            )
        elif m.group("code_inner") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("code_inner"),
                    "marks": [{"type": "code"}],
                }
            )
        elif m.group("status_title") is not None:
            color = (m.group("status_color") or "neutral").lower()
            if color not in _VALID_STATUS_COLORS:
                color = "neutral"
            nodes.append(
                {
                    "type": "status",
                    "attrs": {
                        "text": m.group("status_title"),
                        "color": color,
                        "style": "",
                    },
                }
            )
        elif m.group("bolditalic_star_inner") is not None:
            nodes.extend(
                _parse_nested(
                    m.group("bolditalic_star_inner"),
                    jira_base_url,
                    [{"type": "strong"}, {"type": "em"}],
                )
            )
        elif m.group("bolditalic_us_inner") is not None:
            nodes.extend(
                _parse_nested(
                    m.group("bolditalic_us_inner"),
                    jira_base_url,
                    [{"type": "strong"}, {"type": "em"}],
                )
            )
        elif m.group("bold_inner") is not None:
            nodes.extend(
                _parse_nested(
                    m.group("bold_inner"), jira_base_url, [{"type": "strong"}]
                )
            )
        elif m.group("strike_inner") is not None:
            nodes.extend(
                _parse_nested(
                    m.group("strike_inner"), jira_base_url, [{"type": "strike"}]
                )
            )
        elif m.group("link_text") is not None:
            nodes.append(
                {
                    "type": "text",
                    "text": m.group("link_text"),
                    "marks": [
                        {
                            "type": "link",
                            "attrs": {"href": m.group("link_href")},
                        }
                    ],
                }
            )
        elif m.group("italic_inner") is not None:
            nodes.extend(
                _parse_nested(m.group("italic_inner"), jira_base_url, [{"type": "em"}])
            )
        elif m.group("italic_us_inner") is not None:
            inner = m.group("italic_us_inner")
            if _looks_like_embedded_identifier(inner):
                # This span's own delimiters are individually valid (each
                # passed the word-boundary guard), but the middle contains
                # what looks like an unrelated identifier's underscore --
                # almost certainly an accidental bridge across two
                # unconnected tokens rather than an intentional italic
                # phrase. Preserve the two delimiter underscores literally,
                # but still recurse into the swallowed span for its own
                # inline formatting -- it can easily contain a genuine
                # markdown construct (a real link, bold text, etc.) that
                # must not be flattened to plain text just because the
                # outer italic guess was wrong. Recursing on `inner` alone
                # (not the full match, which still has the delimiters
                # attached) keeps this from re-triggering the same
                # rejection forever.
                _append_text_nodes(nodes, "_", jira_base_url)
                nodes.extend(_parse_inline_formatting(inner, jira_base_url))
                _append_text_nodes(nodes, "_", jira_base_url)
            else:
                nodes.extend(_parse_nested(inner, jira_base_url, [{"type": "em"}]))

        pos = m.end()

    # Remaining plain text after last match
    if pos < len(text):
        remaining = text[pos:]
        _append_text_nodes(nodes, remaining, jira_base_url)

    # If no patterns matched, return the whole thing as plain text
    if not nodes and text:
        _append_text_nodes(nodes, text, jira_base_url)

    return nodes


def _make_paragraph(text: str, jira_base_url: str = "") -> dict[str, Any]:
    """Create an ADF paragraph node from text with inline formatting."""
    content = _parse_inline_formatting(text, jira_base_url)
    if not content:
        content = [{"type": "text", "text": ""}]
    return {"type": "paragraph", "content": content}


def _make_list_item(text: str, jira_base_url: str = "") -> dict[str, Any]:
    """Create an ADF listItem node wrapping a paragraph."""
    return {"type": "listItem", "content": [_make_paragraph(text, jira_base_url)]}


def _make_task_item(
    text: str,
    checked: bool,
    local_id: str,
    jira_base_url: str = "",
) -> dict[str, Any]:
    """Create an ADF taskItem node."""
    return {
        "type": "taskItem",
        "attrs": {"localId": local_id, "state": "DONE" if checked else "TODO"},
        "content": _parse_inline_formatting(text, jira_base_url)
        or [{"type": "text", "text": text}],
    }


def markdown_to_adf(markdown_text: str, jira_base_url: str = "") -> dict[str, Any]:
    """Convert Markdown text to ADF (Atlassian Document Format) document.

    Implements a line-by-line parser that handles common Markdown constructs.
    Jira Cloud expand blocks can be written as
    ``{expand:Title}...{expand}``. No external dependencies required.

    Args:
        markdown_text: Markdown-formatted text to convert.
        jira_base_url: Jira base URL used to link bare issue keys.

    Returns:
        ADF document dict with version, type, and content keys.
    """
    doc: dict[str, Any] = {"version": 1, "type": "doc", "content": []}

    if not markdown_text:
        doc["content"].append({"type": "paragraph", "content": []})
        return doc

    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # --- Expand/collapse block ({expand:Title}...{expand}) ---
        expand_match = re.match(r"^\{expand(?::(.+?))?\}\s*$", line)
        if expand_match:
            expand_title = expand_match.group(1) or ""
            expand_lines: list[str] = []
            i += 1
            while i < len(lines) and not re.match(r"^\{expand\}\s*$", lines[i]):
                expand_lines.append(lines[i])
                i += 1
            # Skip closing {expand}
            if i < len(lines):
                i += 1
            # Recursively parse the inner content as ADF
            inner_markdown = "\n".join(expand_lines)
            inner_doc = markdown_to_adf(inner_markdown, jira_base_url)
            expand_node: dict[str, Any] = {
                "type": "expand",
                "attrs": {"title": expand_title},
                "content": inner_doc.get("content", []),
            }
            doc["content"].append(expand_node)
            continue

        # --- Fenced code block ---
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            # Skip closing ```
            if i < len(lines):
                i += 1
            cb: dict[str, Any] = {
                "type": "codeBlock",
                "attrs": {"language": lang} if lang else {},
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            }
            doc["content"].append(cb)
            continue

        # --- Horizontal rule ---
        stripped = line.strip()
        if stripped in ("---", "***", "___") or (
            len(stripped) >= 3
            and all(c == stripped[0] for c in stripped)
            and stripped[0] in "-*_"
        ):
            # Make sure it's not a list item like "- --"
            if not line.startswith("- ") and not line.startswith("* "):
                doc["content"].append({"type": "rule"})
                i += 1
                continue

        # --- Heading ---
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            heading_node: dict[str, Any] = {
                "type": "heading",
                "attrs": {"level": level},
                "content": _parse_inline_formatting(text, jira_base_url),
            }
            doc["content"].append(heading_node)
            i += 1
            continue

        # --- Blockquote ---
        if line.startswith("> "):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            bq_content = [_make_paragraph(ln, jira_base_url) for ln in quote_lines]
            doc["content"].append({"type": "blockquote", "content": bq_content})
            continue

        # --- Task list (- [ ] / - [x]) ---
        if re.match(r"^[-*]\s+\[[ xX]\]\s+", line):
            task_items: list[dict[str, Any]] = []
            task_counter = 0
            while i < len(lines) and re.match(r"^[-*]\s+\[[ xX]\]\s+", lines[i]):
                checked = bool(re.match(r"^[-*]\s+\[[xX]\]\s+", lines[i]))
                item_text = re.sub(r"^[-*]\s+\[[ xX]\]\s+", "", lines[i])
                task_counter += 1
                task_items.append(
                    _make_task_item(
                        item_text,
                        checked,
                        f"task-{id(doc)}-{task_counter}",
                        jira_base_url,
                    )
                )
                i += 1
            doc["content"].append(
                {
                    "type": "taskList",
                    "attrs": {"localId": f"tasklist-{id(doc)}-{i}"},
                    "content": task_items,
                }
            )
            continue

        # --- Panel block ---
        panel_match = re.match(r"^:::(\w+)\s*$", line)
        if panel_match:
            panel_type = panel_match.group(1).lower()
            valid_panel_types = {"note", "info", "warning", "success", "error"}
            if panel_type in valid_panel_types:
                panel_lines: list[str] = []
                i += 1
                while i < len(lines) and lines[i].strip() != ":::":
                    panel_lines.append(lines[i])
                    i += 1
                # Skip closing :::
                if i < len(lines):
                    i += 1
                # Recursively parse panel content
                inner_doc = markdown_to_adf("\n".join(panel_lines), jira_base_url)
                panel_node: dict[str, Any] = {
                    "type": "panel",
                    "attrs": {"panelType": panel_type},
                    "content": inner_doc["content"],
                }
                doc["content"].append(panel_node)
                continue

        # --- Unordered list ---
        if re.match(r"^[-*]\s+", line):
            items: list[dict[str, Any]] = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                item_text = re.sub(r"^[-*]\s+", "", lines[i])
                items.append(_make_list_item(item_text, jira_base_url))
                i += 1
            doc["content"].append({"type": "bulletList", "content": items})
            continue

        # --- Ordered list ---
        if re.match(r"^\d+\.\s+", line):
            items_ol: list[dict[str, Any]] = []
            while i < len(lines):
                if re.match(r"^\d+\.\s+", lines[i]):
                    item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                    items_ol.append(_make_list_item(item_text, jira_base_url))
                    i += 1
                elif (
                    not lines[i].strip()
                    and i + 1 < len(lines)
                    and re.match(r"^\d+\.\s+", lines[i + 1])
                ):
                    i += 1
                else:
                    break
            doc["content"].append({"type": "orderedList", "content": items_ol})
            continue

        # --- Table ---
        if line.startswith("|") and "|" in line[1:]:
            table_rows: list[str] = []
            while i < len(lines) and lines[i].startswith("|"):
                table_rows.append(lines[i])
                i += 1

            # Parse rows, skip separator (|---|---|). The delimiter row is the
            # second line of a table by definition, so only that line is
            # eligible: a later row of dash-only cells is data, and a single
            # "-" is a common way to write "not applicable".
            data_rows: list[list[str]] = []
            for row_index, row_line in enumerate(table_rows):
                cells = [c.strip() for c in row_line.strip("|").split("|")]
                if row_index == 1 and all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    continue
                data_rows.append(cells)

            if data_rows:
                adf_rows: list[dict[str, Any]] = []
                for idx, cells in enumerate(data_rows):
                    cell_type = "tableHeader" if idx == 0 else "tableCell"
                    adf_cells = []
                    for cell_text in cells:
                        content = _parse_inline_formatting(cell_text, jira_base_url)
                        if not content:
                            content = [{"type": "text", "text": ""}]
                        adf_cells.append(
                            {
                                "type": cell_type,
                                "content": [{"type": "paragraph", "content": content}],
                            }
                        )
                    adf_rows.append({"type": "tableRow", "content": adf_cells})

                doc["content"].append(
                    {
                        "type": "table",
                        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
                        "content": adf_rows,
                    }
                )
            continue

        # --- Empty line (skip) ---
        if not stripped:
            i += 1
            continue

        # --- Paragraph (default) ---
        doc["content"].append(_make_paragraph(line, jira_base_url))
        i += 1

    # Ensure at least one content node
    if not doc["content"]:
        doc["content"].append({"type": "paragraph", "content": []})

    return doc


def _adf_node_contains_media(node: dict[str, Any]) -> bool:
    """Return True when an ADF node contains media content."""
    if node.get("type") in _MEDIA_NODE_TYPES:
        return True

    content = node.get("content")
    if isinstance(content, list):
        return any(
            _adf_node_contains_media(child)
            for child in content
            if isinstance(child, dict)
        )

    return False


def extract_top_level_media_nodes(
    adf_document: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract top-level ADF nodes that contain media content."""
    if not isinstance(adf_document, dict):
        return []

    content = adf_document.get("content")
    if not isinstance(content, list):
        return []

    return [
        copy.deepcopy(node)
        for node in content
        if isinstance(node, dict) and _adf_node_contains_media(node)
    ]


def merge_adf_with_preserved_media(
    target_adf: dict[str, Any],
    source_adf: dict[str, Any] | None,
) -> dict[str, Any]:
    """Append existing media nodes from one ADF document into another.

    This is intentionally narrow: it preserves existing media-bearing blocks
    when a caller rewrites the surrounding description text, without attempting
    to merge all prior formatting or layout.
    """
    preserved_media = extract_top_level_media_nodes(source_adf)
    if not preserved_media:
        return target_adf

    merged = copy.deepcopy(target_adf)
    content = merged.get("content")
    if not isinstance(content, list):
        content = []
        merged["content"] = content

    existing_signatures = {
        json.dumps(node, sort_keys=True, separators=(",", ":"))
        for node in extract_top_level_media_nodes(merged)
    }
    for media_node in preserved_media:
        signature = json.dumps(media_node, sort_keys=True, separators=(",", ":"))
        if signature in existing_signatures:
            continue
        content.append(media_node)
        existing_signatures.add(signature)

    return merged


def adf_to_text(adf_content: dict | list | str | None) -> str | None:
    """
    Convert Atlassian Document Format (ADF) content to plain text.

    ADF is Jira Cloud's rich text format returned for fields like description.
    This function recursively extracts text content from the ADF structure.

    Args:
        adf_content: ADF document (dict), content list, string, or None

    Returns:
        Plain text string or None if no content
    """
    if adf_content is None:
        return None

    if isinstance(adf_content, str):
        return adf_content

    if isinstance(adf_content, list):
        texts = []
        for item in adf_content:
            text = adf_to_text(item)
            if text:
                texts.append(text)
        return "\n".join(texts) if texts else None

    if isinstance(adf_content, dict):
        # Check if this is a text node
        if adf_content.get("type") == "text":
            return adf_content.get("text", "")

        # Check if this is a hardBreak node
        if adf_content.get("type") == "hardBreak":
            return "\n"

        # Check if this is a mention node
        if adf_content.get("type") == "mention":
            attrs = adf_content.get("attrs", {})
            return attrs.get("text") or f"@{attrs.get('id', 'unknown')}"

        # Check if this is an emoji node
        if adf_content.get("type") == "emoji":
            attrs = adf_content.get("attrs", {})
            return attrs.get("text") or attrs.get("shortName", "")

        # Check if this is a date node
        if adf_content.get("type") == "date":
            attrs = adf_content.get("attrs", {})
            timestamp = attrs.get("timestamp")
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
                    return dt.strftime("%Y-%m-%d")
                except (ValueError, OSError, TypeError, OverflowError):
                    return str(timestamp)
            return ""

        # Check if this is a status node
        if adf_content.get("type") == "status":
            attrs = adf_content.get("attrs", {})
            return f"[{attrs.get('text', '')}]"

        # Check if this is an inlineCard node
        if adf_content.get("type") == "inlineCard":
            attrs = adf_content.get("attrs", {})
            url = attrs.get("url")
            if url:
                return url
            data = attrs.get("data", {})
            return data.get("url") or data.get("name", "")

        # Check if this is a codeBlock node
        if adf_content.get("type") == "codeBlock":
            content = adf_content.get("content", [])
            code_text = adf_to_text(content) or ""
            return f"```\n{code_text}\n```"

        # Recursively process content
        content = adf_content.get("content")
        if content:
            return adf_to_text(content)

        return None

    return None
