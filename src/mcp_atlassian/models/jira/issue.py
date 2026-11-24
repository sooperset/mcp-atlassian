"""
Jira issue models.

This module provides Pydantic models for Jira issues.
"""

import logging
import re
from collections.abc import Callable, Collection, Iterable, Mapping
from html import escape
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field

from ...utils.ssrf_adapter import url_origin
from ..base import ApiModel, TimestampMixin
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    JIRA_DEFAULT_KEY,
)
from .adf import adf_to_text
from .comment import JiraComment
from .common import (
    JiraAttachment,
    JiraChangelog,
    JiraIssueType,
    JiraPriority,
    JiraResolution,
    JiraStatus,
    JiraTimetracking,
    JiraUser,
)
from .link import JiraIssueLink
from .project import JiraProject

logger = logging.getLogger(__name__)

# Extended epic field name patterns to support more variations
EPIC_NAME_PATTERNS = [
    r"epic\s*name",
    r"epic[._-]?name",
    r"epicname",
]

EPIC_LINK_PATTERNS = [
    r"epic\s*link",
    r"epic[._-]?link",
    r"Parent Link",
    r"parent\s*link",
    r"epiclink",
]


# How a changelog item is checked against the allowlist. "issue": its old and
# new values name issues, each of which must be in the allowlist. "drop": it
# names a project or sprint that cannot be matched to the allowlist. "plain":
# a built-in value type (text, select, number, date, user...) that never holds
# an issue reference, so a key-shaped value is user data.
FieldKind = Literal["issue", "drop", "plain"]
ChangelogFieldKinds = Mapping[str, FieldKind]

# System fields, by fieldId and by the field name Jira writes (Server/DC
# changelog items carry only the name).
_CHANGELOG_SYSTEM_FIELDS: dict[str, Literal["issue", "drop"]] = {
    "issuelinks": "issue",
    "link": "issue",
    "parent": "issue",
    "issueparentassociation": "issue",
    "issuekey": "issue",
    "key": "issue",
    "epic link": "issue",
    "parent link": "issue",
    "epic child": "issue",
    "project": "drop",
    "sprint": "drop",
}
# Custom field types that reference issues or sprints.
_CHANGELOG_CUSTOM_TYPES: dict[str, Literal["issue", "drop"]] = {
    "com.pyxis.greenhopper.jira:gh-epic-link": "issue",
    "com.atlassian.jpo:jpo-custom-field-parent": "issue",
    "com.pyxis.greenhopper.jira:gh-sprint": "drop",
}
_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+)-\d+\b")


# Built-in Jira custom field types whose values are never issue references.
_PLAIN_CUSTOM_TYPE_PREFIX = "com.atlassian.jira.plugin.system.customfieldtypes:"
_PLAIN_CUSTOM_TYPES = frozenset(
    {
        "textfield",
        "textarea",
        "readonlyfield",
        "select",
        "multiselect",
        "radiobuttons",
        "multicheckboxes",
        "cascadingselect",
        "float",
        "datepicker",
        "datetime",
        "userpicker",
        "multiuserpicker",
        "grouppicker",
        "multigrouppicker",
        "labels",
        "url",
        "version",
        "multiversion",
        "project",
    }
)


def _custom_type_is_plain(custom: str) -> bool:
    if not custom.startswith(_PLAIN_CUSTOM_TYPE_PREFIX):
        return False
    return custom[len(_PLAIN_CUSTOM_TYPE_PREFIX) :] in _PLAIN_CUSTOM_TYPES


def normalize_field_name(name: str) -> str:
    """Lower-case a field id or name and collapse its whitespace.

    The field metadata index, the output filters and the JQL check all look
    names up through this, so "Epic  Link" and "epic link" match everywhere.
    """
    return " ".join(name.lower().split())


def field_metadata_kinds(fields: Iterable[Any]) -> dict[str, FieldKind]:
    """Map custom field ids and names to their changelog check, from field metadata.

    Args:
        fields: Field definitions from ``GET /rest/api/2/field``.

    Returns:
        Lower-cased field id and name to "issue", "drop" or "plain"; fields of
        app types that are not known are left out.
    """
    kinds: dict[str, FieldKind] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        schema = field.get("schema") or {}
        custom = str(schema.get("custom") or "")
        kind: FieldKind | None = _CHANGELOG_CUSTOM_TYPES.get(custom)
        if kind is None and schema.get("type") == "issuelinks":
            kind = "issue"
        if kind is None and _custom_type_is_plain(custom):
            kind = "plain"
        if kind is None:
            continue
        for key in (field.get("id"), field.get("name")):
            if isinstance(key, str) and key.strip():
                kinds[normalize_field_name(key)] = kind
    return kinds


def _changelog_item_kind(item: Any, kinds: ChangelogFieldKinds) -> str | None:
    for key in (item.field_id, item.field):
        key = normalize_field_name(key or "")
        if key and key in kinds:
            return kinds[key]
    for key in (item.field_id, item.field):
        key = (key or "").strip().lower()
        if key in _CHANGELOG_SYSTEM_FIELDS:
            return _CHANGELOG_SYSTEM_FIELDS[key]
    return None


def _changelog_side_allowed(values: tuple[Any, ...], allowed: set[str]) -> bool:
    """One side (old or new) of an item: every value must name allowed issues."""
    present = [str(v) for v in values if v]
    if not present:
        return True
    projects = {m.group(1) for v in present for m in _ISSUE_KEY_RE.finditer(v)}
    # A side that names no issue key (a bare numeric ID) cannot be verified.
    return bool(projects) and projects <= allowed


def _names_other_issue(values: Iterable[Any], allowed: Collection[str]) -> bool:
    """Guess whether an app field value names an out-of-scope issue.

    Used only for fields whose type the metadata does not describe. App issue
    pickers write bare keys (``SECRET-8`` or ``[A-1, B-2]``) or a key followed
    by the summary (``SECRET-8 - summary``). Other text that mentions a key
    later on is left alone.
    """
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip().lstrip("[")
        tokens = [t for t in re.split(r"[\s,\[\]]+", text) if t]
        matches = [_ISSUE_KEY_RE.fullmatch(t.upper()) for t in tokens]
        if tokens and all(matches):
            if any(m.group(1) not in allowed for m in matches if m):
                return True
            continue
        first = _ISSUE_KEY_RE.match(text.upper())
        if first and first.group(1) not in allowed:
            return True
    return False


def _value_references_other_issue(value: Any, allowed: Collection[str]) -> bool:
    """Return True if a custom field value holds an out-of-scope issue key.

    Issue references sit in a ``key`` entry at any depth (Parent Link keeps it
    under ``data``) or as a bare key string (app issue pickers). Free text
    that merely mentions a key is not a reference.
    """
    if isinstance(value, str):
        match = _ISSUE_KEY_RE.fullmatch(value.strip())
        return match is not None and match.group(1) not in allowed
    if isinstance(value, list):
        return any(_value_references_other_issue(v, allowed) for v in value)
    if isinstance(value, dict):
        key = value.get("key")
        if isinstance(key, str) and _value_references_other_issue(key, allowed):
            return True
        return any(
            _value_references_other_issue(v, allowed)
            for k, v in value.items()
            if k != "key" and isinstance(v, dict | list)
        )
    return False


def _strings(value: Any) -> list[str]:
    """Return the strings in a custom field value, at any depth."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []


_BROWSE_PATH_RE = re.compile(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)/?$")
_ISSUE_LINK_CLASSES = frozenset({"issue-link", "jira-issue-macro-key"})


def _decoded(text: str, rounds: int = 4) -> str:
    for _ in range(rounds):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _jira_issue_link(
    attrs: dict[str, str], jira_origin: Any
) -> tuple[bool, str | None]:
    """Classify an anchor by its attributes.

    Returns ``(is_issue_link, key)``. An issue link is a ``/browse/<key>`` or
    ``ViewIssue.jspa?id=`` link on the Jira origin (or relative), or an anchor
    Jira marked as an issue link. ``key`` is its upper-cased issue key, or
    None when the link names the issue only by ID. Anything that cannot be
    parsed is not an issue link.
    """
    href = (attrs.get("href") or "").strip()
    classes = {c.lower() for c in (attrs.get("class") or "").split()}
    marked = bool(classes & _ISSUE_LINK_CLASSES) or "data-issue-key" in attrs
    try:
        parts = urlsplit(href)
        relative = not parts.scheme and not parts.netloc and href.startswith("/")
        on_jira = relative or (
            jira_origin is not None and url_origin(href) == jira_origin
        )
    except ValueError:
        return False, None
    path = _decoded(parts.path)
    key = (attrs.get("data-issue-key") or "").strip()
    match = _BROWSE_PATH_RE.search(path) if on_jira or marked else None
    if not key and match:
        key = match.group(1)
    if key:
        return True, key.upper()
    by_id = on_jira and path.lower().endswith("/viewissue.jspa")
    return marked or by_id, None


class _AnchorSpans(HTMLParser):
    """Find each ``<a>`` in HTML with its exact source span and text.

    A closed anchor spans ``<a ...>...</a>``. An anchor left open, because
    the document ends or another anchor starts first, spans only its start
    tag and has no text.
    """

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self._html = html
        self._line_starts = [0]
        self._line_starts.extend(i + 1 for i, c in enumerate(html) if c == "\n")
        self.anchors: list[tuple[int, int, dict[str, str], str | None]] = []
        self._open: tuple[int, int, dict[str, str], list[str]] | None = None

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def _close_open_tag(self) -> None:
        if self._open is not None:
            start, tag_end, attrs, _ = self._open
            self.anchors.append((start, tag_end, attrs, None))
            self._open = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._close_open_tag()
            start = self._offset()
            tag_end = start + len(self.get_starttag_text() or "")
            self._open = (start, tag_end, {k: v or "" for k, v in attrs}, [])

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open[3].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._open is None:
            return
        start, tag_end, attrs, text = self._open
        self._open = None
        close = self._html.find(">", self._offset())
        if close == -1:
            self.anchors.append((start, tag_end, attrs, None))
        else:
            self.anchors.append((start, close + 1, attrs, "".join(text)))

    def close(self) -> None:
        super().close()
        self._close_open_tag()


def _issue_refs_confirmed(value: Any, allowed: Collection[str]) -> bool:
    """Return True if every issue a reference field value names is in scope.

    A reference must carry an upper-case issue key (as Jira returns it) of an
    allowed project: a bare key string, or a ``key`` at any depth (Parent Link
    keeps it under ``data``). A value with only an ID, a lower-case key or a
    key with text around it cannot be confirmed.
    """
    if isinstance(value, list):
        return all(_issue_refs_confirmed(v, allowed) for v in value)
    if isinstance(value, str):
        match = _ISSUE_KEY_RE.fullmatch(value.strip())
        return match is not None and match.group(1) in allowed
    if isinstance(value, dict):
        if "key" in value:
            return _issue_refs_confirmed(value["key"], allowed) and all(
                _issue_refs_confirmed(v, allowed)
                for k, v in value.items()
                if k == "data" and v is not None
            )
        if isinstance(value.get("data"), dict | list):
            return _issue_refs_confirmed(value["data"], allowed)
        return False
    return False


def custom_value_allowed(
    field_id: str,
    name: str,
    value: Any,
    kinds: ChangelogFieldKinds | None,
    allowed: Collection[str],
) -> bool:
    """Decide whether a custom field value may be returned under the allowlist.

    The field metadata decides: built-in value types (text, select, number,
    date, user...) are kept whatever their value looks like; Sprint fields are
    dropped (a sprint's board cannot be matched to the allowlist); issue
    reference fields keep only values confirmed in scope. Only fields of
    unknown app types are judged by how their value looks.
    """
    if value is None:
        return True
    known = kinds or {}
    lowered = normalize_field_name(name)
    kind = known.get(normalize_field_name(field_id)) or known.get(lowered)
    if kind == "plain":
        return True
    if kind == "drop" or (kind is None and lowered == "sprint"):
        return False
    if kind == "issue":
        # An issue ID (an integer) cannot be matched to a project.
        return _issue_refs_confirmed(value, allowed)
    if isinstance(value, int | float | bool):
        return True
    return not (
        _value_references_other_issue(value, allowed)
        or _names_other_issue(_strings(value), allowed)
    )


def _field_is_plain(
    field_id: str, name: str, kinds: ChangelogFieldKinds | None
) -> bool:
    known = kinds or {}
    kind = known.get(normalize_field_name(field_id)) or known.get(
        normalize_field_name(name)
    )
    return kind == "plain"


def _restrict_rendered_html(
    html: str, allowed: Collection[str], jira_origin: Any = None
) -> str:
    """Replace Jira issue links not confirmed in scope with their text.

    Jira renders a mentioned issue as an anchor whose attributes (title,
    data-*) carry the linked issue's summary, read with the server's
    credential. An issue link to another project, or one that names its issue
    only by ID, becomes the anchor's text with no attributes. In-scope issue
    links and links to other sites stay as they are. Only the replaced
    anchors change; the rest of the HTML is kept byte for byte.
    """
    if "<a" not in html.lower():
        return html
    parser = _AnchorSpans(html)
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError):
        return html
    pieces: list[str] = []
    last = 0
    for start, end, attrs, text in parser.anchors:
        is_issue_link, key = _jira_issue_link(attrs, jira_origin)
        if not is_issue_link:
            continue
        if key is not None and _ISSUE_KEY_RE.fullmatch(key):
            if key.rsplit("-", 1)[0] in allowed:
                continue
        pieces.append(html[last:start])
        # An unclosed anchor loses only its start tag; what follows stays.
        pieces.append(escape(text, quote=False) if text is not None else "")
        last = end
    if not pieces:
        return html
    pieces.append(html[last:])
    return "".join(pieces)


def _is_custom_field_item(item: Any) -> bool:
    field_id = (item.field_id or "").strip().lower()
    return field_id.startswith("customfield_") or item.fieldtype == "custom"


def _changelog_item_allowed(
    item: Any, allowed: set[str], kinds: ChangelogFieldKinds | None
) -> bool:
    """Return True if a changelog item names nothing outside ``allowed``.

    ``kinds`` is None when the field metadata could not be read: a custom
    field change then cannot be classified and is dropped.
    """
    kind = _changelog_item_kind(item, kinds or {})
    if kind == "drop":
        return False
    if kind == "plain":
        return True
    if kind is None:
        if not _is_custom_field_item(item):
            return True
        # An app field of unknown type: keep it unless a value looks like a
        # reference to an issue outside the allowlist.
        return kinds is not None and not _names_other_issue(
            (item.from_string, item.to_string), allowed
        )
    old = (item.from_string, item.from_id)
    new = (item.to_string, item.to_id)
    if not any(old) and not any(new):
        return False
    return _changelog_side_allowed(old, allowed) and _changelog_side_allowed(
        new, allowed
    )


def restrict_changelogs(
    changelogs: list[JiraChangelog],
    allowed_projects: Collection[str],
    field_kinds: ChangelogFieldKinds | None = None,
) -> None:
    """Drop changelog items that name issues, projects or sprints out of scope.

    Reference fields are found by fieldId, by name, and through custom field
    metadata (``field_kinds``), so a renamed Epic Link or Sprint field is still
    recognised. For issue references the old and the new value are checked
    separately, and an item with a value that names no issue key is dropped.
    Other items (status, summary, ...) describe the issue itself.

    Args:
        changelogs: Changelogs to filter in place.
        allowed_projects: Upper-cased project keys (JIRA_PROJECTS_FILTER).
        field_kinds: Custom reference fields from :func:`changelog_field_kinds`,
            or None when the field metadata could not be read (custom field
            changes are then dropped).
    """
    allowed = {str(k).strip().upper() for k in allowed_projects}
    for changelog in changelogs:
        changelog.items = [
            item
            for item in changelog.items
            if _changelog_item_allowed(item, allowed, field_kinds)
        ]


def _reference_project(ref: Any) -> str | None:
    """Return the upper-cased project key of an issue reference, or None.

    Uses ``fields.project.key`` when the reference carries it, otherwise the
    prefix of the issue key Jira returned (the current key of the issue).
    """
    if not isinstance(ref, dict):
        return None
    fields = ref.get("fields")
    project = fields.get("project") if isinstance(fields, dict) else None
    project_key = project.get("key") if isinstance(project, dict) else None
    if isinstance(project_key, str) and project_key.strip():
        return project_key.strip().upper()
    key = ref.get("key")
    if isinstance(key, str) and "-" in key:
        prefix = key.rsplit("-", 1)[0].strip()
        if prefix:
            return prefix.upper()
    return None


def restrict_raw_issue(
    raw: dict[str, Any],
    allowed_projects: Collection[str],
    field_kinds: ChangelogFieldKinds | None = None,
) -> dict[str, Any] | None:
    """Apply the project allowlist to an issue that is returned as raw JSON.

    Returns None for an issue outside ``allowed_projects``. Otherwise returns
    a copy without the parent, subtasks, issue links and custom reference
    values that point at issues outside it.

    Args:
        raw: Issue JSON as Jira returned it.
        allowed_projects: Upper-cased project keys (JIRA_PROJECTS_FILTER).
        field_kinds: Field metadata kinds (see ``custom_value_allowed``), or
            None when unknown.
    """
    allowed = {str(k).strip().upper() for k in allowed_projects}
    if _reference_project(raw) not in allowed:
        return None
    fields = raw.get("fields")
    if not isinstance(fields, dict):
        return raw
    names = raw.get("names") if isinstance(raw.get("names"), dict) else {}

    def ok(ref: Any) -> bool:
        return _reference_project(ref) in allowed

    kept: dict[str, Any] = {}
    for name, value in fields.items():
        if name == "parent" and value is not None and not ok(value):
            continue
        if name == "subtasks" and isinstance(value, list):
            value = [st for st in value if ok(st)]
        elif name == "issuelinks" and isinstance(value, list):
            value = [
                link
                for link in value
                if isinstance(link, dict)
                and any(side in link for side in ("inwardIssue", "outwardIssue"))
                and all(
                    ok(link[side])
                    for side in ("inwardIssue", "outwardIssue")
                    if side in link
                )
            ]
        elif name.startswith("customfield_") and not custom_value_allowed(
            name, str(names.get(name) or ""), value, field_kinds, allowed
        ):
            continue
        kept[name] = value
    return {**raw, "fields": kept}


class JiraIssue(ApiModel, TimestampMixin):
    """
    Model representing a Jira issue.

    This is a comprehensive model containing all the common fields
    for Jira issues and related metadata.
    """

    id: str = JIRA_DEFAULT_ID
    key: str = JIRA_DEFAULT_KEY
    summary: str = EMPTY_STRING
    description: str | None = None
    environment: str | None = None
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    status: JiraStatus | None = None
    issue_type: JiraIssueType | None = None
    priority: JiraPriority | None = None
    assignee: JiraUser | None = None
    reporter: JiraUser | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    comments: list[JiraComment] = Field(default_factory=list)
    attachments: list[JiraAttachment] = Field(default_factory=list)
    timetracking: JiraTimetracking | None = None
    url: str | None = None
    browse_url: str | None = None
    epic_key: str | None = None
    epic_name: str | None = None
    fix_versions: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    requested_fields: Literal["*all"] | list[str] | None = None
    project: JiraProject | None = None
    resolution: JiraResolution | None = None
    duedate: str | None = None
    resolutiondate: str | None = None
    parent: dict | None = None
    subtasks: list[dict] = Field(default_factory=list)
    security: dict | None = None
    worklog: dict | None = None
    changelogs: list[JiraChangelog] = Field(default_factory=list)
    issuelinks: list[JiraIssueLink] = Field(default_factory=list)
    rendered_fields: dict[str, Any] = Field(default_factory=dict)

    def __getattribute__(self, name: str) -> Any:
        """
        Custom attribute access to handle custom field access.

        This allows accessing custom fields by their name as if they were
        regular attributes of the JiraIssue class.

        Args:
            name: The attribute name to access

        Returns:
            The attribute value or custom field value
        """
        # First try to get the attribute normally
        try:
            return super().__getattribute__(name)
        except AttributeError:
            # If the attribute doesn't exist, check if it's a custom field
            try:
                custom_fields = super().__getattribute__("custom_fields")
                if name in custom_fields:
                    return custom_fields[name]
            except AttributeError:
                pass
            # Re-raise the original AttributeError
            raise

    @property
    def page_content(self) -> str | None:
        """
        Get the page content from the description.

        This is a convenience property for treating Jira issues as documentation pages.

        Returns:
            The description text or None
        """
        # Return description without modification for now
        # In the future, we could parse ADF content here
        return self.description

    @staticmethod
    def _find_custom_field_in_api_response(
        fields: dict[str, Any], name_patterns: list[str]
    ) -> Any:
        """
        Find a custom field by name patterns in the raw API response.

        Used during object creation from API response to extract fields
        before the JiraIssue object is instantiated.

        Args:
            fields: The fields dictionary from the Jira API
            name_patterns: List of field name patterns to search for

        Returns:
            The custom field value or None
        """
        if not fields or not isinstance(fields, dict):
            return None

        # Normalize all patterns for easier matching
        normalized_patterns = []
        for pattern in name_patterns:
            norm_pattern = pattern.lower()
            norm_pattern = re.sub(r"[_\-\s]", "", norm_pattern)
            normalized_patterns.append(norm_pattern)

        custom_field_id = None

        # Check if fields has a names fields
        names_dict = fields.get("names", {})
        if isinstance(names_dict, dict):
            for field_id, field_name in names_dict.items():
                field_name_norm = re.sub(r"[_\-\s]", "", field_name.lower())
                for norm_pattern in normalized_patterns:
                    if norm_pattern in field_name_norm:
                        custom_field_id = field_id
                        break
                if custom_field_id:
                    break
        else:
            logger.debug("No names dict found in fields", exc_info=True)

        # Look at field metadata if name method didn't work
        if not custom_field_id:
            schema = fields.get("schema", {})
            if schema and isinstance(schema, dict) and "fields" in schema:
                schema_fields = schema["fields"]
                if isinstance(schema_fields, dict):
                    for field_id, field_info in schema_fields.items():
                        if not field_id.startswith("customfield_"):
                            continue

                        if isinstance(field_info, dict) and "name" in field_info:
                            field_name = field_info["name"].lower()
                            field_name_norm = re.sub(r"[_\-\s]", "", field_name)
                            for norm_pattern in normalized_patterns:
                                if norm_pattern in field_name_norm:
                                    custom_field_id = field_id
                                    break

                        if custom_field_id:
                            break

        # Try direct matching of field IDs for common epic fields
        if not custom_field_id:
            has_epic_link_pattern = any("epiclink" in p for p in normalized_patterns)
            has_epic_name_pattern = any("epicname" in p for p in normalized_patterns)

            if has_epic_link_pattern:
                for field_id in fields:
                    if field_id.startswith("customfield_") and field_id.endswith("14"):
                        custom_field_id = field_id
                        break
            elif has_epic_name_pattern:
                for field_id in fields:
                    if field_id.startswith("customfield_") and field_id.endswith("11"):
                        custom_field_id = field_id
                        break

        # Last attempt - look through all custom fields for names in their values
        if not custom_field_id:
            for field_id, field_value in fields.items():
                if not field_id.startswith("customfield_"):
                    continue

                field_name = None
                if isinstance(field_value, dict) and "name" in field_value:
                    field_name = field_value.get("name", "").lower()
                elif isinstance(field_value, dict) and "key" in field_value:
                    field_name = field_value.get("key", "").lower()

                if not field_name:
                    continue

                field_name_norm = re.sub(r"[_\-\s]", "", field_name)
                for norm_pattern in normalized_patterns:
                    if norm_pattern in field_name_norm:
                        custom_field_id = field_id
                        break

                if custom_field_id:
                    break

        if custom_field_id and custom_field_id in fields:
            return fields[custom_field_id]

        return None

    @staticmethod
    def _build_browse_url(base_url: Any, key: str) -> str | None:
        if not isinstance(base_url, str) or not base_url.strip():
            return None
        if key == JIRA_DEFAULT_KEY:
            return None
        return f"{base_url.strip().rstrip('/')}/browse/{key}"

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssue":
        """
        Create a JiraIssue from a Jira API response.

        Args:
            data: The issue data from the Jira API
            **kwargs: Additional arguments to pass to the constructor

        Returns:
            A JiraIssue instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}

        # Get required simple fields
        issue_id = str(data.get("id", JIRA_DEFAULT_ID))
        key = str(data.get("key", JIRA_DEFAULT_KEY))
        summary = str(fields.get("summary", EMPTY_STRING))

        # Handle description - can be string (legacy) or ADF dict (Jira Cloud new editor)
        raw_description = fields.get("description")
        if isinstance(raw_description, dict):
            # Convert ADF to plain text
            description = adf_to_text(raw_description)
        else:
            description = raw_description

        # Handle environment - like description, it can be a string (Server/DC,
        # classic editor) or an ADF dict (Jira Cloud new editor)
        raw_environment = fields.get("environment")
        if isinstance(raw_environment, dict):
            environment = adf_to_text(raw_environment)
        else:
            environment = raw_environment

        # Timestamps
        created = str(fields.get("created", EMPTY_STRING))
        updated = str(fields.get("updated", EMPTY_STRING))

        # Extract assignee data
        assignee = None
        assignee_data = fields.get("assignee")
        if assignee_data:
            assignee = JiraUser.from_api_response(assignee_data)

        # Extract reporter data
        reporter = None
        reporter_data = fields.get("reporter")
        if reporter_data:
            reporter = JiraUser.from_api_response(reporter_data)

        # Extract status data
        status = None
        status_data = fields.get("status")
        if status_data:
            status = JiraStatus.from_api_response(status_data)

        # Extract issue type data
        issue_type = None
        issue_type_data = fields.get("issuetype")
        if issue_type_data:
            issue_type = JiraIssueType.from_api_response(issue_type_data)

        # Extract priority data
        priority = None
        priority_data = fields.get("priority")
        if priority_data:
            priority = JiraPriority.from_api_response(priority_data)

        # Extract project data
        project = None
        project_data = fields.get("project")
        if isinstance(project_data, dict):
            project = JiraProject.from_api_response(project_data)

        resolution = None
        resolution_data = fields.get("resolution")
        if isinstance(resolution_data, dict):
            resolution = JiraResolution.from_api_response(resolution_data)

        duedate = (
            fields.get("duedate") if isinstance(fields.get("duedate"), str) else None
        )
        resolutiondate = (
            fields.get("resolutiondate")
            if isinstance(fields.get("resolutiondate"), str)
            else None
        )
        parent = (
            fields.get("parent") if isinstance(fields.get("parent"), dict) else None
        )
        # Ensure subtasks is a list of dicts
        subtasks_raw = fields.get("subtasks", [])
        subtasks = (
            [st for st in subtasks_raw if isinstance(st, dict)]
            if isinstance(subtasks_raw, list)
            else []
        )
        security = (
            fields.get("security") if isinstance(fields.get("security"), dict) else None
        )
        worklog = (
            fields.get("worklog") if isinstance(fields.get("worklog"), dict) else None
        )

        # Lists of strings
        labels = []
        if labels_data := fields.get("labels"):
            if isinstance(labels_data, list):
                labels = [str(label) for label in labels_data if label]

        components = []
        if components_data := fields.get("components"):
            if isinstance(components_data, list):
                components = [
                    str(comp.get("name", "")) if isinstance(comp, dict) else str(comp)
                    for comp in components_data
                    if comp
                ]

        fix_versions = []
        if fix_versions_data := fields.get("fixVersions"):
            if isinstance(fix_versions_data, list):
                fix_versions = [
                    str(version.get("name", ""))
                    if isinstance(version, dict)
                    else str(version)
                    for version in fix_versions_data
                    if version
                ]

        versions = []
        if versions_data := fields.get("versions"):
            if isinstance(versions_data, list):
                versions = [
                    str(version.get("name", ""))
                    if isinstance(version, dict)
                    else str(version)
                    for version in versions_data
                    if version
                ]

        # Handling comments
        comments = []
        comments_field = fields.get("comment", {})
        if isinstance(comments_field, dict) and "comments" in comments_field:
            comments_data = comments_field["comments"]
            if isinstance(comments_data, list):
                comments = [
                    JiraComment.from_api_response(comment)
                    for comment in comments_data
                    if comment
                ]

        # Handling changelogs
        changelogs = []
        changelogs_data = data.get("changelog", {})
        if isinstance(changelogs_data, dict) and "histories" in changelogs_data:
            changelogs = [
                JiraChangelog.from_api_response(history)
                for history in changelogs_data["histories"]
            ]

        # Handling attachments
        attachments = []
        attachments_data = fields.get("attachment", [])
        if isinstance(attachments_data, list):
            attachments = [
                JiraAttachment.from_api_response(attachment)
                for attachment in attachments_data
                if attachment
            ]

        # Timetracking
        timetracking = None
        timetracking_data = fields.get("timetracking")
        if timetracking_data:
            timetracking = JiraTimetracking.from_api_response(timetracking_data)

        # URL
        url = data.get("self")  # API URL for the issue
        browse_url = cls._build_browse_url(kwargs.get("base_url"), key)

        # Try to find epic fields (varies by Jira instance)
        epic_key = None
        epic_name = None

        # Check for "Epic Link" field
        epic_link = cls._find_custom_field_in_api_response(
            fields, ["epic link", "parent epic"]
        )
        if isinstance(epic_link, str):
            epic_key = epic_link

        # Check for "Epic Name" field
        epic_name_value = cls._find_custom_field_in_api_response(fields, ["epic name"])
        if isinstance(epic_name_value, str):
            epic_name = epic_name_value

        # Store custom fields
        custom_fields = {}
        fields_name_map = data.get("names", {})
        for orig_field_id, orig_field_value in fields.items():
            if orig_field_id.startswith("customfield_"):
                value_obj_to_store = {"value": orig_field_value}
                human_readable_name = fields_name_map.get(orig_field_id)
                if human_readable_name:
                    value_obj_to_store["name"] = human_readable_name
                custom_fields[orig_field_id] = value_obj_to_store

        # Handle requested_fields parameter
        requested_fields_param = kwargs.get("requested_fields")

        # Convert string requested_fields to list (except "*all")
        if isinstance(requested_fields_param, str) and requested_fields_param != "*all":
            requested_fields_param = requested_fields_param.split(",")
            # Strip whitespace from each field name
            requested_fields_param = [field.strip() for field in requested_fields_param]

        # Create the issue instance with all the extracted data
        issue = cls(
            id=issue_id,
            key=key,
            summary=summary,
            description=description,
            environment=environment,
            created=created,
            updated=updated,
            status=status,
            issue_type=issue_type,
            priority=priority,
            assignee=assignee,
            reporter=reporter,
            project=project,
            resolution=resolution,
            duedate=duedate,
            resolutiondate=resolutiondate,
            parent=parent,
            subtasks=subtasks,
            security=security,
            worklog=worklog,
            labels=labels,
            components=components,
            comments=comments,
            attachments=attachments,
            timetracking=timetracking,
            url=url,
            browse_url=browse_url,
            epic_key=epic_key,
            epic_name=epic_name,
            fix_versions=fix_versions,
            versions=versions,
            custom_fields=custom_fields,
            requested_fields=requested_fields_param,
            changelogs=changelogs,
            issuelinks=cls._extract_issue_links(fields),
            rendered_fields=cls._extract_rendered_fields(data.get("renderedFields")),
        )
        allowed_projects = kwargs.get("allowed_projects")
        if allowed_projects:
            issue.restrict_references(
                allowed_projects, kwargs.get("changelog_field_kinds")
            )
        return issue

    def restrict_references(
        self,
        allowed_projects: Collection[str],
        changelog_field_kinds: Callable[[], ChangelogFieldKinds | None] | None = None,
    ) -> None:
        """Drop references to issues outside ``allowed_projects``.

        An issue inside the project allowlist can point at issues outside it
        through its parent, subtasks, issue links and epic link. Those
        references carry the other issue's key and summary, so they are
        removed rather than returned. A reference whose project cannot be
        determined is removed as well.

        Args:
            allowed_projects: Upper-cased project keys (JIRA_PROJECTS_FILTER).
            changelog_field_kinds: Returns the custom reference fields for the
                changelog filter; called only when there are changelogs.
        """
        allowed = {str(k).strip().upper() for k in allowed_projects}

        def ok(ref: Any) -> bool:
            return _reference_project(ref) in allowed

        if self.parent is not None and not ok(self.parent):
            self.parent = None
        self.subtasks = [st for st in self.subtasks if ok(st)]
        self.issuelinks = [
            link
            for link in self.issuelinks
            if all(
                side is None or ok({"key": side.key})
                for side in (link.inward_issue, link.outward_issue)
            )
            and (link.inward_issue is not None or link.outward_issue is not None)
        ]
        kinds_cache: list[ChangelogFieldKinds | None] = []

        def kinds() -> ChangelogFieldKinds | None:
            if not kinds_cache:
                kinds_cache.append(
                    changelog_field_kinds() if changelog_field_kinds else None
                )
            return kinds_cache[0]

        self._restrict_epic_references(ok, kinds)
        self._restrict_custom_references(allowed, kinds)
        self._restrict_rendered_references(allowed)
        if self.changelogs:
            restrict_changelogs(self.changelogs, allowed, kinds())

    def _restrict_custom_references(
        self,
        allowed: set[str],
        kinds: Callable[[], ChangelogFieldKinds | None],
    ) -> None:
        """Drop custom fields whose value is not allowed (see custom_value_allowed)."""
        for field_id, field in list(self.custom_fields.items()):
            if not field_id.startswith("customfield_") or not isinstance(field, dict):
                continue
            value = field.get("value")
            name = str(field.get("name") or "")
            if not custom_value_allowed(field_id, name, value, kinds(), allowed):
                del self.custom_fields[field_id]

    def _restrict_rendered_references(self, allowed: set[str]) -> None:
        origin = url_origin(self.browse_url) if self.browse_url else None
        for field_id, value in list(self.rendered_fields.items()):
            if isinstance(value, str):
                self.rendered_fields[field_id] = _restrict_rendered_html(
                    value, allowed, origin
                )
            elif field_id == "comment" and isinstance(value, list):
                self.rendered_fields[field_id] = [
                    {
                        **c,
                        "body": _restrict_rendered_html(
                            str(c["body"]), allowed, origin
                        ),
                    }
                    for c in value
                ]

    def _restrict_epic_references(
        self,
        ok: Any,
        kinds: Callable[[], ChangelogFieldKinds | None] = lambda: None,
    ) -> None:
        """Drop the epic link, and the epic name copied with it, when out of scope.

        The epic link can also sit in a custom field (Epic Link on Server/DC,
        Parent Link). Such a field is removed when it names an issue outside
        the allowlist or holds the dropped epic key. When an epic is dropped,
        its name is removed as well: ``epic_name`` and any Epic Name custom
        field. An epic's own Epic Name is kept, since it has no epic link.
        Fields the metadata types as built-in values (text, select...) are user
        data and are never removed here.
        """
        dropped_keys: set[str] = set()
        if self.epic_key and not ok({"key": self.epic_key}):
            dropped_keys.add(self.epic_key)
            self.epic_key = None

        def referenced_key(value: Any) -> str | None:
            if isinstance(value, dict):
                value = value.get("key") or value.get("value")
            return value if isinstance(value, str) and value else None

        def has_name(field: Any, patterns: list[str]) -> bool:
            name = field.get("name") if isinstance(field, dict) else None
            return isinstance(name, str) and any(
                re.search(p, name, re.IGNORECASE) for p in patterns
            )

        def plain(field_id: str, field: dict[str, Any]) -> bool:
            if not self.custom_fields:
                return False
            return _field_is_plain(field_id, str(field.get("name") or ""), kinds())

        for field_id, field in list(self.custom_fields.items()):
            if not field_id.startswith("customfield_") or not isinstance(field, dict):
                continue
            if plain(field_id, field):
                continue
            key = referenced_key(field.get("value"))
            if key is None:
                continue
            if key in dropped_keys or (
                has_name(field, EPIC_LINK_PATTERNS) and not ok({"key": key})
            ):
                dropped_keys.add(key)
                del self.custom_fields[field_id]

        if not dropped_keys:
            return
        dropped_name = self.epic_name
        self.epic_name = None
        for field_id, field in list(self.custom_fields.items()):
            if not field_id.startswith("customfield_") or not isinstance(field, dict):
                continue
            if plain(field_id, field):
                continue
            value = field.get("value")
            if has_name(field, EPIC_NAME_PATTERNS) or (
                dropped_name is not None and value == dropped_name
            ):
                del self.custom_fields[field_id]

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "key": self.key,
        }

        # Helper method to check if a field should be included
        def should_include_field(field_name: str) -> bool:
            return (
                self.requested_fields == "*all"
                or not isinstance(self.requested_fields, list)
                or field_name in self.requested_fields
            )

        # Add summary if requested
        if should_include_field("summary"):
            result["summary"] = self.summary

        # Add URL if available and requested
        if self.url and should_include_field("url"):
            result["url"] = self.url

        if self.browse_url:
            result["browse_url"] = self.browse_url

        # Add description if available and requested
        if self.description and should_include_field("description"):
            result["description"] = self.description

        # Add environment if available and requested
        if self.environment and should_include_field("environment"):
            result["environment"] = self.environment

        # Add status if available and requested
        if self.status and should_include_field("status"):
            result["status"] = self.status.to_simplified_dict()

        # Add issue type if available and requested
        if self.issue_type and should_include_field("issuetype"):
            result["issue_type"] = self.issue_type.to_simplified_dict()

        # Add priority if available and requested
        if self.priority and should_include_field("priority"):
            result["priority"] = self.priority.to_simplified_dict()

        # Add project info if available and requested
        if self.project and should_include_field("project"):
            result["project"] = self.project.to_simplified_dict()

        # Add resolution if available and requested
        if self.resolution and should_include_field("resolution"):
            result["resolution"] = self.resolution.to_simplified_dict()

        # Add dates if available and requested
        if self.duedate and should_include_field("duedate"):
            result["duedate"] = self.duedate

        if self.resolutiondate and should_include_field("resolutiondate"):
            result["resolutiondate"] = self.resolutiondate

        # Add parent and subtasks if available and requested
        if self.parent and should_include_field("parent"):
            result["parent"] = self.parent

        if self.subtasks and should_include_field("subtasks"):
            result["subtasks"] = self.subtasks

        # Add security and worklog if available and requested
        if self.security and should_include_field("security"):
            result["security"] = self.security

        if self.worklog and should_include_field("worklog"):
            result["worklog"] = self.worklog

        # Add assignee if requested
        if should_include_field("assignee"):
            if self.assignee:
                result["assignee"] = self.assignee.to_simplified_dict()
            else:
                result["assignee"] = {"display_name": "Unassigned"}

        # Add reporter if available and requested
        if self.reporter and should_include_field("reporter"):
            result["reporter"] = self.reporter.to_simplified_dict()

        # Add lists if available and requested
        if self.labels and should_include_field("labels"):
            result["labels"] = self.labels

        if self.components and should_include_field("components"):
            result["components"] = self.components

        if self.fix_versions and should_include_field("fixVersions"):
            result["fix_versions"] = self.fix_versions

        # Affects Version/s
        if self.versions and should_include_field("versions"):
            result["versions"] = self.versions

        # Add epic fields if available and requested
        if self.epic_key and should_include_field("epic_key"):
            result["epic_key"] = self.epic_key

        if self.epic_name and should_include_field("epic_name"):
            result["epic_name"] = self.epic_name

        # Add time tracking if available and requested
        if self.timetracking and should_include_field("timetracking"):
            result["timetracking"] = self.timetracking.to_simplified_dict()

        # Add created and updated timestamps if available and requested
        if self.created and should_include_field("created"):
            result["created"] = self.format_timestamp(self.created)

        if self.updated and should_include_field("updated"):
            result["updated"] = self.format_timestamp(self.updated)

        # Add comments if available and requested
        if self.comments and should_include_field("comment"):
            result["comments"] = [
                comment.to_simplified_dict() for comment in self.comments
            ]

        # Add attachments if available and requested
        if self.attachments and should_include_field("attachment"):
            result["attachments"] = [
                attachment.to_simplified_dict() for attachment in self.attachments
            ]

        # Not use should_include_field since you won't get changelogs
        # if you don't ask for them
        if self.changelogs:
            result["changelogs"] = [
                changelog.to_simplified_dict() for changelog in self.changelogs
            ]

        # Add issue links if available and requested
        if self.issuelinks and should_include_field("issuelinks"):
            result["issuelinks"] = [
                link.to_simplified_dict() for link in self.issuelinks
            ]

        # Rendered HTML is only present when expand=renderedFields was requested
        if self.rendered_fields:
            rendered = self._simplify_rendered_fields(should_include_field)
            if rendered:
                result["rendered_fields"] = rendered

        # Process custom fields
        if self.custom_fields:
            if self.requested_fields == "*all":
                for internal_id, field_data_obj in self.custom_fields.items():
                    processed_value = self._process_custom_field_value(
                        field_data_obj.get("value")
                    )
                    output_value_obj = {"value": processed_value}
                    if "name" in field_data_obj:
                        output_value_obj["name"] = field_data_obj["name"]
                    result[internal_id] = output_value_obj
            elif isinstance(self.requested_fields, list):
                for requested_key_or_name in self.requested_fields:
                    found_by_id_or_name = False
                    if (
                        requested_key_or_name.startswith("customfield_")
                        and requested_key_or_name in self.custom_fields
                    ):
                        field_data_obj = self.custom_fields[requested_key_or_name]
                        output_value_obj = {
                            "value": self._process_custom_field_value(
                                field_data_obj.get("value")
                            )
                        }
                        if "name" in field_data_obj:
                            output_value_obj["name"] = field_data_obj["name"]
                        result[requested_key_or_name] = output_value_obj
                        found_by_id_or_name = True
                    else:
                        for internal_id, field_data_obj in self.custom_fields.items():
                            if (
                                field_data_obj.get("name", "").lower()
                                == requested_key_or_name.lower()
                            ):
                                output_value_obj = {
                                    "value": self._process_custom_field_value(
                                        field_data_obj.get("value")
                                    )
                                }
                                output_value_obj["name"] = field_data_obj["name"]
                                result[internal_id] = output_value_obj
                                found_by_id_or_name = True
                                break
                    if not found_by_id_or_name and requested_key_or_name.startswith(
                        "cf_"
                    ):
                        full_id = "customfield_" + requested_key_or_name[3:]
                        if full_id in self.custom_fields:
                            field_data_obj = self.custom_fields[full_id]
                            output_value_obj = {
                                "value": self._process_custom_field_value(
                                    field_data_obj.get("value")
                                )
                            }
                            if "name" in field_data_obj:
                                output_value_obj["name"] = field_data_obj["name"]
                            result[full_id] = output_value_obj

        return {k: v for k, v in result.items() if v is not None}

    def _process_custom_field_value(self, field_value: Any) -> Any:
        """
        Process a custom field value for simplified dict output.

        Args:
            field_value: The value to process

        Returns:
            Processed value suitable for API response
        """
        if field_value is None or isinstance(field_value, str | int | float | bool):
            return field_value

        if isinstance(field_value, dict):
            # For single-select, user pickers, etc., try to extract 'value' or 'name'
            if "value" in field_value:
                return field_value["value"]
            elif "name" in field_value:
                # Standard Jira reference objects (priority, user, group) have a
                # "self" URL key — simplify those to just the name. Plugin data
                # objects (e.g. Okapya checklist items) don't have "self" and
                # should be preserved in full to retain metadata like "checked".
                if "self" in field_value:
                    return field_value["name"]
                return field_value
            return field_value

        if isinstance(field_value, list):
            return [self._process_custom_field_value(item) for item in field_value]

        return str(field_value)

    def _find_custom_field_in_issue(
        self, name: str, pattern: bool = False
    ) -> tuple[str | None, Any]:
        """
        Find a custom field by name or pattern in an instantiated JiraIssue.

        Used by instance methods like _get_epic_name and _get_epic_link
        to search through the custom_fields dictionary of an existing issue.

        Args:
            name: The name to search for
            pattern: If True, use regex pattern matching

        Returns:
            A tuple of (field_id, field_value) or (None, None) if not found
        """
        if not self.custom_fields:
            return None, None

        # Check if fields has a names() method (some implementations have this)
        names_dict = self.custom_fields.get("names", {})
        if isinstance(names_dict, dict):
            for field_id, field_name in names_dict.items():
                if (pattern and re.search(name, field_name, re.IGNORECASE)) or (
                    not pattern and field_name.lower() == name.lower()
                ):
                    return field_id, self.custom_fields.get(field_id)
        else:
            logger.debug("No names dict found in custom fields", exc_info=True)

        # Check field metadata for name (custom fields usually have a name)
        for field_id, field_value in self.custom_fields.items():
            if not field_id.startswith("customfield_"):
                continue

            # Custom fields can have a schema with a name
            if isinstance(field_value, dict) and field_value.get("name"):
                field_name = field_value.get("name")
                if field_name and (
                    (pattern and re.search(name, field_name, re.IGNORECASE))
                    or (not pattern and field_name.lower() == name.lower())
                ):
                    return field_id, field_value

        # Fallback: Directly look for keys that match the pattern
        if pattern:
            for field_id, field_value in self.custom_fields.items():
                if re.search(name, field_id, re.IGNORECASE):
                    return field_id, field_value

        return None, None

    def get_custom_field_by_name(
        self, display_name: str, *, case_sensitive: bool = False
    ) -> Any:
        """Look up a custom field value by its human-readable display name.

        This is a convenience wrapper over the internal ``custom_fields`` dict
        (which is keyed by ``customfield_XXXXX``).  It searches the ``name``
        entry stored inside each value object, so the underlying data structure
        is completely untouched.

        Args:
            display_name: The human-readable name of the field
                (e.g. ``"Story Points"``, ``"Severity"``).
            case_sensitive: If *False* (default) the comparison is
                case-insensitive.

        Returns:
            The processed field value if found, or *None*.
        """
        target = display_name if case_sensitive else display_name.lower()
        for field_data in self.custom_fields.values():
            if not isinstance(field_data, dict):
                continue
            stored_name = field_data.get("name")
            if stored_name is None:
                continue
            candidate = stored_name if case_sensitive else stored_name.lower()
            if candidate == target:
                return self._process_custom_field_value(field_data.get("value"))
        return None

    @staticmethod
    def _get_display_key(
        field_id: str,
        field_data: Any,
        *,
        reserved_keys: set[str],
        used_keys: set[str],
    ) -> str:
        """Choose a display key without overwriting another field."""
        if not isinstance(field_data, dict):
            return field_id

        display_name = field_data.get("name")
        if (
            not isinstance(display_name, str)
            or not display_name
            or display_name in reserved_keys
            or display_name in used_keys
        ):
            return field_id
        return display_name

    @property
    def custom_fields_by_display_name(self) -> dict[str, Any]:
        """Return ``custom_fields`` re-keyed by display name.

        Fields that do not carry a ``name`` entry keep their original
        ``customfield_XXXXX`` key so nothing is silently dropped.

        Each value retains the upstream structure
        (``{"value": …}``) with an additional ``"field_id"`` key
        for reverse-lookup convenience.  The redundant ``"name"`` entry is
        stripped since the display name is already used as the dict key.

        Returns:
            A **new** dict — the original ``custom_fields`` is never mutated.
        """
        result: dict[str, Any] = {}
        reserved_keys = set(self.custom_fields)
        for field_id, field_data in self.custom_fields.items():
            if not isinstance(field_data, dict):
                result[field_id] = field_data
                continue
            display_key = self._get_display_key(
                field_id,
                field_data,
                reserved_keys=reserved_keys,
                used_keys=set(result),
            )
            entry = {**field_data, "field_id": field_id}
            entry.pop("name", None)
            result[display_key] = entry
        return result

    def to_display_name_dict(
        self, extra_reserved_keys: set[str] | None = None
    ) -> dict[str, Any]:
        """Like ``to_simplified_dict`` but with custom fields keyed by display name.

        Standard fields (summary, status, etc.) are identical to
        ``to_simplified_dict()``.  Only the custom-field section changes:
        each ``customfield_XXXXX`` key is replaced by its human-readable
        name when one is available.

        Args:
            extra_reserved_keys: Additional keys that must not be claimed by
                custom fields (e.g. enrichment section output keys like
                ``"comments"``, ``"watchers"``).

        Returns:
            A simplified dict suitable for tool / API output where custom
            fields use human-friendly keys.
        """
        base = self.to_simplified_dict()

        custom_items = [
            (key, value)
            for key, value in base.items()
            if key.startswith("customfield_")
        ]
        custom_field_ids = {key for key, _ in custom_items}
        reserved_keys = set(base).difference(custom_field_ids) | custom_field_ids
        if extra_reserved_keys:
            reserved_keys |= extra_reserved_keys
        rekeyed_customs: dict[str, Any] = {}

        for key, value in custom_items:
            display_key = self._get_display_key(
                key,
                value,
                reserved_keys=reserved_keys,
                used_keys=set(rekeyed_customs),
            )
            if isinstance(value, dict):
                value = {**value, "field_id": key}
                value.pop("name", None)
            rekeyed_customs[display_key] = value

        for key in custom_field_ids:
            del base[key]

        base.update(rekeyed_customs)
        return base

    def _get_epic_name(self) -> str | None:
        """Get the epic name from custom fields if available."""
        # Try each pattern in order
        for pattern in EPIC_NAME_PATTERNS:
            field_id, field_value = self._find_custom_field_in_issue(
                pattern, pattern=True
            )
            if field_id and field_value:
                if isinstance(field_value, dict):
                    return field_value.get("value") or field_value.get("name")
                return str(field_value)
        return None

    def _get_epic_link(self) -> str | None:
        """Get the epic link from custom fields if available."""
        # Try each pattern in order
        for pattern in EPIC_LINK_PATTERNS:
            field_id, field_value = self._find_custom_field_in_issue(
                pattern, pattern=True
            )
            if field_id and field_value:
                # Handle different possible value types
                if isinstance(field_value, dict):
                    return field_value.get("key") or field_value.get("value")
                return str(field_value)
        return None

    @staticmethod
    def _extract_rendered_fields(rendered_data: Any) -> dict[str, Any]:
        """
        Extract non-empty rendered values from ``renderedFields``.

        Jira returns ``renderedFields`` beside ``fields`` when the request
        expands it, with an HTML value (or ``None``) for each returned field.
        Rendered comments are reduced to their id and HTML body.

        Args:
            rendered_data: The ``renderedFields`` object from the Jira API

        Returns:
            Rendered values keyed by Jira field id
        """
        if not isinstance(rendered_data, dict):
            return {}

        rendered_fields: dict[str, Any] = {}
        for field_id, value in rendered_data.items():
            if field_id == "comment":
                comments_data = (
                    value.get("comments") if isinstance(value, dict) else None
                )
                value = (
                    [
                        {"id": str(comment.get("id")), "body": comment["body"]}
                        for comment in comments_data
                        if isinstance(comment, dict) and comment.get("body")
                    ]
                    if isinstance(comments_data, list)
                    else None
                )
            if value:
                rendered_fields[field_id] = value
        return rendered_fields

    def _simplify_rendered_fields(
        self, should_include_field: Callable[[str], bool]
    ) -> dict[str, Any]:
        """
        Select the rendered values to emit in ``to_simplified_dict``.

        Only requested fields are kept. Rendered comments are limited to the
        comments present on the issue, so ``comment_limit`` still applies.

        Args:
            should_include_field: Predicate deciding whether a field is requested

        Returns:
            Rendered values keyed by Jira field id
        """
        rendered: dict[str, Any] = {}
        for field_id, value in self.rendered_fields.items():
            if not should_include_field(field_id):
                continue
            if field_id == "comment":
                comment_ids = {comment.id for comment in self.comments}
                value = [c for c in value if c["id"] in comment_ids]
                if not value:
                    continue
            rendered[field_id] = value
        return rendered

    @staticmethod
    def _extract_issue_links(fields: dict[str, Any]) -> list[JiraIssueLink]:
        """
        Extract issue links from fields.

        Args:
            fields: The fields dictionary from the Jira API

        Returns:
            List of JiraIssueLink objects
        """
        if not fields or not isinstance(fields, dict):
            return []

        issuelinks_data = fields.get("issuelinks", [])
        if not isinstance(issuelinks_data, list):
            return []

        return [
            JiraIssueLink.from_api_response(link_data)
            for link_data in issuelinks_data
            if link_data
        ]
