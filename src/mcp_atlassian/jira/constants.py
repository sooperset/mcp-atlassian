"""Constants specific to Jira operations."""

import logging
import os

# Based on https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/
# "Reserved words" section — verified 2026-02-23
# Using lowercase for case-insensitive matching
RESERVED_JQL_WORDS = {
    "a",
    "an",
    "abort",
    "access",
    "add",
    "after",
    "alias",
    "all",
    "alter",
    "and",
    "any",
    "are",
    "as",
    "asc",
    "at",
    "audit",
    "avg",
    "be",
    "before",
    "begin",
    "between",
    "boolean",
    "break",
    "but",
    "by",
    "byte",
    "catch",
    "cf",
    "char",
    "character",
    "check",
    "checkpoint",
    "collate",
    "collation",
    "column",
    "commit",
    "connect",
    "continue",
    "count",
    "create",
    "current",
    "date",
    "decimal",
    "declare",
    "decrement",
    "default",
    "defaults",
    "define",
    "delete",
    "delimiter",
    "desc",
    "difference",
    "distinct",
    "divide",
    "do",
    "double",
    "drop",
    "else",
    "empty",
    "encoding",
    "end",
    "equals",
    "escape",
    "exclusive",
    "exec",
    "execute",
    "exists",
    "explain",
    "false",
    "fetch",
    "field",
    "file",
    "first",
    "float",
    "for",
    "from",
    "function",
    "go",
    "goto",
    "grant",
    "greater",
    "group",
    "having",
    "identified",
    "if",
    "immediate",
    "in",
    "increment",
    "index",
    "initial",
    "inner",
    "inout",
    "input",
    "insert",
    "int",
    "integer",
    "intersect",
    "intersection",
    "into",
    "is",
    "isempty",
    "isnull",
    "it",
    "join",
    "last",
    "left",
    "less",
    "like",
    "limit",
    "lock",
    "long",
    "max",
    "min",
    "minus",
    "mode",
    "modify",
    "modulo",
    "more",
    "multiply",
    "next",
    "no",
    "noaudit",
    "not",
    "notin",
    "nowait",
    "null",
    "number",
    "object",
    "of",
    "on",
    "option",
    "or",
    "order",
    "outer",
    "output",
    "power",
    "previous",
    "prior",
    "privileges",
    "public",
    "raise",
    "raw",
    "remainder",
    "rename",
    "resource",
    "return",
    "returns",
    "revoke",
    "right",
    "row",
    "rowid",
    "rownum",
    "rows",
    "select",
    "session",
    "set",
    "share",
    "size",
    "sqrt",
    "start",
    "strict",
    "string",
    "subtract",
    "such",
    "sum",
    "synonym",
    "table",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "trans",
    "transaction",
    "trigger",
    "true",
    "uid",
    "union",
    "unique",
    "update",
    "user",
    "validate",
    "values",
    "view",
    "was",
    "when",
    "whenever",
    "where",
    "while",
    "will",
    "with",
}

# ---------------------------------------------------------------------------
# Hierarchy link classification
# ---------------------------------------------------------------------------
#
# How it works:
#   When traversing issue links, the label for the direction being
#   evaluated tells us the current issue's role:
#
#     outward_issue + outward_label "is parent of"  → target is CHILD
#     inward_issue  + inward_label  "is child of"   → target is PARENT
#
# Built-in phrases (cover all standard Jira link types):
#
#   PARENT-OF (target is child)     CHILD-OF (target is parent)
#   ─────────────────────────────   ─────────────────────────────
#   is parent of                    is child of
#   parent                          is contained by
#   contains                        split from
#   split to
#   epic
#
# Custom phrases — extend via env var:
#
#   HIERARCHY_LINK_PHRASES="parent:rolls up to,child:is part of"
#
#   Format: comma-separated, each entry is  parent:<phrase>
#                                        or child:<phrase>
# ---------------------------------------------------------------------------

_hierarchy_logger = logging.getLogger("mcp-jira")

_BUILTIN_PARENT_OF: set[str] = {
    "is parent of",
    "parent",
    "contains",
    "split to",
    "epic",
}

_BUILTIN_CHILD_OF: set[str] = {
    "is child of",
    "is contained by",
    "split from",
}


def _load_custom_hierarchy_phrases() -> tuple[set[str], set[str]]:
    """Parse ``HIERARCHY_LINK_PHRASES`` into parent-of and child-of sets."""
    raw = os.getenv("HIERARCHY_LINK_PHRASES", "")
    parent_extra: set[str] = set()
    child_extra: set[str] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" not in token:
            _hierarchy_logger.warning(
                "HIERARCHY_LINK_PHRASES: ignoring malformed entry '%s' "
                "(expected 'parent:<phrase>' or 'child:<phrase>')",
                token,
            )
            continue
        role, phrase = token.split(":", 1)
        role = role.strip().lower()
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        if role == "parent":
            parent_extra.add(phrase)
        elif role == "child":
            child_extra.add(phrase)
        else:
            _hierarchy_logger.warning(
                "HIERARCHY_LINK_PHRASES: unknown role '%s' in '%s' "
                "(expected 'parent' or 'child')",
                role,
                token,
            )
    if parent_extra or child_extra:
        _hierarchy_logger.info(
            "HIERARCHY_LINK_PHRASES: added %d parent-of and %d child-of phrases",
            len(parent_extra),
            len(child_extra),
        )
    return parent_extra, child_extra


_custom_parent, _custom_child = _load_custom_hierarchy_phrases()

PARENT_OF_PHRASES: frozenset[str] = frozenset(_BUILTIN_PARENT_OF | _custom_parent)
CHILD_OF_PHRASES: frozenset[str] = frozenset(_BUILTIN_CHILD_OF | _custom_child)
HIERARCHY_LINK_PHRASES: frozenset[str] = PARENT_OF_PHRASES | CHILD_OF_PHRASES


# Set of default fields returned by Jira read operations when no specific fields are requested.
DEFAULT_READ_JIRA_FIELDS: set[str] = {
    "summary",
    "description",
    "status",
    "assignee",
    "reporter",
    "labels",
    "priority",
    "created",
    "updated",
    "issuetype",
}
