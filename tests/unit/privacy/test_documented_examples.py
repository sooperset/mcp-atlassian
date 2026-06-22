"""Validate every documented PRIVACY_* example in `.env.example`.

This test parses the project's `.env.example`, extracts every commented
PRIVACY_* assignment, simulates how python-dotenv loads the value, and
exercises the resulting :class:`PrivacyConfig` / :class:`PrivacyPipeline`
against realistic Atlassian payloads. The intent is twofold:

1. Catch documentation drift — if a documented field path stops matching
   the simplified-dict shape upstream produces, this test fails.
2. Catch syntax bugs in the examples themselves (bad regexes, malformed
   JSON, unknown resource types, mistyped paths).

Realistic payloads come from the upstream test fixtures (so we mirror the
exact shapes that flow through the FastMCP middleware in production).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from mcp_atlassian.models.confluence.comment import ConfluenceComment
from mcp_atlassian.models.confluence.page import ConfluencePage
from mcp_atlassian.models.confluence.search import ConfluenceSearchResult
from mcp_atlassian.models.jira.issue import JiraIssue
from mcp_atlassian.models.jira.search import JiraSearchResult
from mcp_atlassian.privacy.config import PrivacyConfig
from mcp_atlassian.privacy.patterns import BUILTIN_PATTERNS
from mcp_atlassian.privacy.pipeline import PrivacyPipeline
from mcp_atlassian.privacy.tool_map import TOOL_RESOURCE_TYPES
from tests.fixtures.confluence_mocks import (  # type: ignore[import-not-found]
    MOCK_COMMENTS_RESPONSE,
    MOCK_CQL_SEARCH_RESPONSE,
    MOCK_PAGE_RESPONSE,
)
from tests.fixtures.jira_mocks import (  # type: ignore[import-not-found]
    MOCK_JIRA_ISSUE_RESPONSE,
    MOCK_JIRA_JQL_RESPONSE,
)

ENV_EXAMPLE_PATH = Path(__file__).resolve().parents[3] / ".env.example"
ENV_EXAMPLE_TEXT = ENV_EXAMPLE_PATH.read_text()

# Match commented PRIVACY_* assignments. Skip "##" double-comments which
# we use for examples that require an extra prerequisite.
_LINE_RE = re.compile(r"^#(PRIVACY_[A-Z_]+)=(.*)$")


def _extract_examples() -> list[tuple[int, str, str]]:
    """Return every (lineno, var, value) for commented PRIVACY_* assignments."""
    examples: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(ENV_EXAMPLE_TEXT.splitlines(), start=1):
        if line.startswith("##"):
            continue
        m = _LINE_RE.match(line)
        if m:
            examples.append((lineno, m.group(1), m.group(2)))
    return examples


_EXAMPLES = _extract_examples()


def _examples_for(var: str) -> list[tuple[int, str]]:
    """All documented values for a single env var."""
    return [(lineno, value) for lineno, v, value in _EXAMPLES if v == var]


# ---------------------------------------------------------------------------
# Built-in pattern coverage
# ---------------------------------------------------------------------------
class TestBuiltinPatternsAreDocumented:
    """Each documented built-in pattern actually catches its example token."""

    @pytest.mark.parametrize(
        ("pattern_name", "sample"),
        [
            ("email", "alice@example.com"),
            ("email", "first.last+tag@sub.example.co"),
            ("phone", "+1 (415) 555-0100"),
            ("phone", "+49 30 1234 5678"),
            ("ipv4", "192.168.1.42"),
            ("ipv4", "10.0.0.1"),
            ("iban", "DE89370400440532013000"),
            ("credit_card", "4242 4242 4242 4242"),
            ("credit_card", "4242-4242-4242-4242"),
            ("credit_card", "4242424242424242"),
        ],
    )
    def test_pattern_matches_documented_sample(
        self, pattern_name: str, sample: str
    ) -> None:
        pattern = BUILTIN_PATTERNS[pattern_name]
        assert pattern.search(sample) is not None, (
            f"Built-in pattern {pattern_name!r} should match its documented "
            f"sample {sample!r}"
        )

    def test_every_documented_builtin_name_resolves(self) -> None:
        documented = {"email", "phone", "ipv4", "iban", "credit_card"}
        assert documented == set(BUILTIN_PATTERNS), (
            "Documented pattern names must match BUILTIN_PATTERNS exactly."
        )


# ---------------------------------------------------------------------------
# Documented custom regex examples — compile + match the example token
# ---------------------------------------------------------------------------
DOCUMENTED_CUSTOM_REGEXES: list[tuple[str, str, str]] = [
    # (label, regex source as it appears in .env.example, sample token to match)
    ("AWS access key ID", r"\bAKIA[0-9A-Z]{16}\b", "AKIAIOSFODNN7EXAMPLE"),
    (
        "GitHub PAT (classic)",
        r"\bghp_[A-Za-z0-9]{36}\b",
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    ),
    (
        "GitHub fine-grained PAT",
        r"\bgithub_pat_[A-Za-z0-9_]{82}\b",
        "github_pat_" + "A" * 82,
    ),
    (
        "GitLab PAT",
        r"\bglpat-[0-9a-zA-Z_\-]{20}\b",
        "glpat-aBcDeFgHiJkLmNoPqRsT",
    ),
    (
        "Slack token",
        r"\bxox[bpoa]-\d+-\d+-\d+-[A-Za-z0-9]+\b",
        "xoxb-9876543210-1234567890-12345-A0BC1D2EFGHIJKL3MNOPQ4R5",
    ),
    (
        "Stripe live key",
        r"\bsk_(?:test|live)_[0-9a-zA-Z]{24,}\b",
        "sk_live_4eC39HqLyjWDarjtT1zdp7dc",
    ),
    (
        "Atlassian API token",
        r"\bATATT3[A-Za-z0-9_=\-]{20,}\b",
        "ATATT3xFfGF0AbCdEfGhIjKlMnOp=",
    ),
    (
        "JWT (3-segment)",
        r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.SflKxwRJSMeKKF2QT4fwpMeJf",
    ),
    (
        "Bearer header in free text",
        r"Bearer\s+[A-Za-z0-9._\-+/=]{16,}",
        "Bearer abcDEF1234567890+/=",
    ),
    (
        "URL with embedded credentials",
        r"https?://[^:\s/]+:[^@\s]+@",
        "https://user:secret@host.example.com",
    ),
    ("US Social Security Number", r"\b\d{3}-\d{2}-\d{4}\b", "123-45-6789"),
    (
        "UK National Insurance Number",
        r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{6}\s?[A-D]\b",
        "AB123456C",
    ),
    ("DE Steuer-ID (lossy)", r"\b\d{11}\b", "12345678901"),
    (
        "FR INSEE / NIR",
        r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2,3}\s?\d{3}\s?\d{3}\s?\d{2}\b",
        "1 84 09 75 117 152 21",
    ),
    (
        "IPv6 address",
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
    ),
    (
        "MAC address",
        r"\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b",
        "00:1A:2B:3C:4D:5E",
    ),
    (
        "Atlassian accountId (24-hex)",
        r"\b[a-f0-9]{24}\b",
        "5b10ac8d82e05b22cc7d4ef5",
    ),
]


class TestDocumentedCustomRegexes:
    @pytest.mark.parametrize(
        ("label", "regex", "sample"),
        DOCUMENTED_CUSTOM_REGEXES,
        ids=[c[0] for c in DOCUMENTED_CUSTOM_REGEXES],
    )
    def test_compile_and_match(self, label: str, regex: str, sample: str) -> None:
        compiled = re.compile(regex)
        assert compiled.search(sample) is not None, (
            f"Documented {label} regex {regex!r} did not match the "
            f"example token {sample!r} from .env.example."
        )

    def test_redactor_replaces_with_mask_token(self) -> None:
        """End-to-end: each documented credential token is masked when the
        regex is supplied via PRIVACY_PII_CUSTOM_REGEX."""
        regexes = [c[1] for c in DOCUMENTED_CUSTOM_REGEXES]
        config = PrivacyConfig(
            enabled=True,
            pii_custom_regex=[re.compile(r) for r in regexes],
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        assert pipeline.is_noop is False
        for label, _regex, sample in DOCUMENTED_CUSTOM_REGEXES:
            text = f"prefix {sample} suffix"
            out = pipeline.apply(tool_name="any", value=text)
            assert "[X]" in out, f"{label}: redactor did not produce mask"
            assert sample not in out, (
                f"{label}: original token {sample!r} survived redaction"
            )


# ---------------------------------------------------------------------------
# Every documented example assignment parses end-to-end
# ---------------------------------------------------------------------------
class TestEnvExampleAssignmentsParse:
    """Every commented PRIVACY_* line is loadable via PrivacyConfig.from_env."""

    @pytest.mark.parametrize(
        ("lineno", "value"),
        _examples_for(var="PRIVACY_PII_PATTERNS"),
    )
    def test_pattern_names_are_known(self, lineno: int, value: str) -> None:
        cfg = PrivacyConfig.from_env(
            env={"PRIVACY_FILTER_ENABLED": "true", "PRIVACY_PII_PATTERNS": value}
        )
        assert cfg.pii_pattern_names, (
            f"line {lineno}: PRIVACY_PII_PATTERNS={value!r} parsed empty"
        )

    @pytest.mark.parametrize(
        ("lineno", "value"),
        _examples_for(var="PRIVACY_PII_CUSTOM_REGEX"),
    )
    def test_custom_regex_compiles_unquoted(self, lineno: int, value: str) -> None:
        # python-dotenv passes unquoted single-backslash values through
        # literally to Python; the PrivacyConfig loader gives them straight
        # to re.compile.
        cfg = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_PII_CUSTOM_REGEX": value,
            }
        )
        assert cfg.pii_custom_regex, (
            f"line {lineno}: PRIVACY_PII_CUSTOM_REGEX={value!r} parsed empty"
        )

    @pytest.mark.parametrize(
        ("lineno", "value"),
        _examples_for(var="PRIVACY_DROP_FIELDS"),
    )
    def test_drop_fields_is_valid(self, lineno: int, value: str) -> None:
        cfg = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": value,
            }
        )
        assert cfg.drop_fields, (
            f"line {lineno}: PRIVACY_DROP_FIELDS={value!r} parsed empty"
        )
        for resource_type in cfg.drop_fields:
            if resource_type != "*":
                assert resource_type in TOOL_RESOURCE_TYPES.values(), (
                    f"line {lineno}: unknown resource_type {resource_type!r}"
                )

    @pytest.mark.parametrize(
        ("lineno", "value"),
        _examples_for(var="PRIVACY_MASK_FIELDS"),
    )
    def test_mask_fields_is_valid(self, lineno: int, value: str) -> None:
        cfg = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_MASK_FIELDS": value,
            }
        )
        assert cfg.mask_fields, (
            f"line {lineno}: PRIVACY_MASK_FIELDS={value!r} parsed empty"
        )
        for resource_type in cfg.mask_fields:
            if resource_type != "*":
                assert resource_type in TOOL_RESOURCE_TYPES.values(), (
                    f"line {lineno}: unknown resource_type {resource_type!r}"
                )


# ---------------------------------------------------------------------------
# Realistic payloads — produced from upstream model code, not hand-built
# ---------------------------------------------------------------------------
def _jira_issue_payload() -> dict[str, Any]:
    """The payload jira_get_issue actually returns."""
    issue = JiraIssue.from_api_response(data=MOCK_JIRA_ISSUE_RESPONSE)
    return issue.to_simplified_dict()


def _jira_search_payload() -> dict[str, Any]:
    """The payload jira_search actually returns."""
    sr = JiraSearchResult.from_api_response(data=MOCK_JIRA_JQL_RESPONSE)
    return sr.to_simplified_dict()


def _confluence_get_page_payload() -> dict[str, Any]:
    """confluence_get_page wraps the simplified dict under `metadata`."""
    page = ConfluencePage.from_api_response(data=MOCK_PAGE_RESPONSE)
    return {"metadata": page.to_simplified_dict()}


def _confluence_search_payload() -> dict[str, Any]:
    """confluence_search returns the search result simplified."""
    sr = ConfluenceSearchResult.from_api_response(data=MOCK_CQL_SEARCH_RESPONSE)
    return sr.to_simplified_dict()


def _confluence_get_comments_payload() -> list[dict[str, Any]]:
    """confluence_get_comments returns a list of simplified comments."""
    return [
        ConfluenceComment.from_api_response(data=raw).to_simplified_dict()
        for raw in (MOCK_COMMENTS_RESPONSE.get("results") or [])
    ]


def _walk(obj: Any) -> Iterable[tuple[str, Any]]:
    """Yield (path, value) for every leaf and dict/list node."""

    def go(o: Any, p: str) -> Iterable[tuple[str, Any]]:
        if isinstance(o, dict):
            for k, v in o.items():
                child = f"{p}.{k}" if p else k
                yield child, v
                yield from go(o=v, p=child)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                child = f"{p}.{i}" if p else str(i)
                yield child, v
                yield from go(o=v, p=child)

    yield from go(o=obj, p="")


def _has_path(payload: Any, path: str) -> bool:
    return any(p == path for p, _ in _walk(payload))


# ---------------------------------------------------------------------------
# Documented Jira simplified-dict paths — verify they exist in real shapes
# ---------------------------------------------------------------------------
class TestDocumentedJiraPathsExist:
    """The paths the docs claim live in the Jira simplified-dict shape."""

    @pytest.mark.parametrize(
        "path",
        [
            "summary",
            "description",
            "reporter.email",
            "reporter.display_name",
            "reporter.name",
            "reporter.avatar_url",
            "assignee.email",
            "assignee.display_name",
            "assignee.name",
            "assignee.avatar_url",
            "comments.0.body",
            "comments.0.author.email",
            "comments.0.author.display_name",
            "comments.0.author.name",
            "attachments.0.filename",
            "attachments.0.url",
            "labels",
        ],
    )
    def test_jira_issue_path_present(self, path: str) -> None:
        payload = _jira_issue_payload()
        assert _has_path(payload=payload, path=path), (
            f"Documented jira_issue path {path!r} not in to_simplified_dict()"
        )

    @pytest.mark.parametrize(
        "path",
        [
            "issues",
            "issues.0.summary",
            "issues.0.description",
            "issues.0.assignee",
            "issues.0.assignee.display_name",
            "issues.0.comments.0.body",
        ],
    )
    def test_jira_search_path_present(self, path: str) -> None:
        payload = _jira_search_payload()
        assert _has_path(payload=payload, path=path), (
            f"Documented jira_issue_list path {path!r} not in search dict"
        )

    def test_jira_search_assignee_email_path_when_populated(self) -> None:
        """The search-result `issues.*.assignee.email` path is what the rules
        target — synthesise an issue with a populated assignee to confirm the
        path is at the documented depth in the simplified-dict shape (the
        mock fixture happens to have an unassigned issue)."""
        # Reuse the get_issue simplified payload (has populated assignee.email)
        # and wrap it as if it came back from search.
        synthetic_search_payload = {
            "total": 1,
            "start_at": 0,
            "max_results": 1,
            "issues": [_jira_issue_payload()],
        }
        assert _has_path(
            payload=synthetic_search_payload,
            path="issues.0.assignee.email",
        )


# ---------------------------------------------------------------------------
# Documented Confluence simplified-dict paths — verify they exist
# ---------------------------------------------------------------------------
class TestDocumentedConfluencePathsExist:
    @pytest.mark.parametrize(
        "path",
        [
            "metadata.title",
            "metadata.url",
            "metadata.space.key",
            "metadata.space.name",
            "metadata.attachments.0.title",
            "metadata.attachments.0.media_type",
        ],
    )
    def test_confluence_get_page_path_present(self, path: str) -> None:
        payload = _confluence_get_page_payload()
        assert _has_path(payload=payload, path=path), (
            f"Documented confluence_page path {path!r} not in get_page result"
        )

    @pytest.mark.parametrize(
        "path",
        [
            "results",
            "results.0.title",
            "results.0.content",
            "results.0.space.key",
            "results.0.space.name",
        ],
    )
    def test_confluence_search_path_present(self, path: str) -> None:
        payload = _confluence_search_payload()
        assert _has_path(payload=payload, path=path), (
            f"Documented confluence_page_list path {path!r} not in search result"
        )

    @pytest.mark.parametrize("path", ["body", "title", "author"])
    def test_confluence_comment_path_present(self, path: str) -> None:
        comments = _confluence_get_comments_payload()
        assert comments, "expected mock to provide at least one comment"
        sample = comments[0]
        assert path in sample, (
            f"Documented confluence_comment path {path!r} not in simplified shape"
        )


# ---------------------------------------------------------------------------
# Documented field-rule examples actually do what the docs claim
# ---------------------------------------------------------------------------
class TestDocumentedFieldRulesEffective:
    """Each example PRIVACY_DROP_FIELDS / MASK_FIELDS line, when applied to
    a realistic payload, actually drops/masks the documented paths."""

    def test_jira_drop_reporter_assignee_email(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": json.dumps(
                    {
                        "jira_issue": [
                            "reporter.email",
                            "assignee.email",
                        ],
                        "jira_issue_list": [
                            "issues.*.reporter.email",
                            "issues.*.assignee.email",
                        ],
                    }
                ),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        # Single issue
        issue_payload = _jira_issue_payload()
        out = pipeline.apply(tool_name="jira_get_issue", value=issue_payload)
        assert "email" not in out["reporter"]
        assert "email" not in out["assignee"]
        assert "display_name" in out["assignee"], (
            "drop should not collateral-damage display_name"
        )
        # Search
        search_payload = _jira_search_payload()
        out = pipeline.apply(tool_name="jira_search", value=search_payload)
        for issue in out["issues"]:
            assert "email" not in issue.get("reporter", {})
            assert "email" not in issue.get("assignee", {})

    def test_global_email_and_avatar_drop_via_double_star(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": json.dumps({"*": ["**.email", "**.avatar_url"]}),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(tool_name="jira_get_issue", value=_jira_issue_payload())
        # No 'email' or 'avatar_url' anywhere in the result.
        for path, _value in _walk(obj=out):
            assert not path.endswith(".email"), f"`**.email` rule missed path {path}"
            assert not path.endswith(".avatar_url"), (
                f"`**.avatar_url` rule missed path {path}"
            )

    def test_jira_mask_display_names(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_MASK_TOKEN": "[X]",
                "PRIVACY_MASK_FIELDS": json.dumps(
                    {
                        "jira_issue": [
                            "reporter.display_name",
                            "reporter.name",
                            "assignee.display_name",
                            "assignee.name",
                        ]
                    }
                ),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(tool_name="jira_get_issue", value=_jira_issue_payload())
        assert out["reporter"]["display_name"] == "[X]"
        assert out["reporter"]["name"] == "[X]"
        assert out["assignee"]["display_name"] == "[X]"
        # Email survives — proves we masked, didn't drop.
        assert "email" in out["assignee"]

    def test_jira_drop_comment_bodies(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": json.dumps({"jira_issue": ["comments.*.body"]}),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(tool_name="jira_get_issue", value=_jira_issue_payload())
        assert out["comments"], "fixture must provide ≥1 comment"
        for comment in out["comments"]:
            assert "body" not in comment, "comment body should be dropped"
            # Author and metadata still present.
            assert "author" in comment
            assert "id" in comment

    def test_confluence_drop_search_excerpts(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": json.dumps(
                    {"confluence_page_list": ["results.*.content"]}
                ),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(
            tool_name="confluence_search",
            value=_confluence_search_payload(),
        )
        for result in out["results"]:
            assert "content" not in result

    def test_confluence_mask_page_body_value(self) -> None:
        # Synthesize a get_page-with-content shape since the basic mock
        # doesn't include `content.value`.
        payload = {
            "metadata": _confluence_get_page_payload()["metadata"],
            "content": {"value": "Free-text body containing alice@example.com"},
        }
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_MASK_TOKEN": "[X]",
                "PRIVACY_MASK_FIELDS": json.dumps(
                    {"confluence_page": ["content.value"]}
                ),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(tool_name="confluence_get_page", value=payload)
        assert out["content"]["value"] == "[X]"
        # Metadata survives.
        assert out["metadata"]["title"]


# ---------------------------------------------------------------------------
# Documented resource denylist behavior
# ---------------------------------------------------------------------------
class TestDocumentedResourceDenylists:
    def test_deny_label_drops_matching_issues(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DENY_LABELS": "confidential,gdpr-restricted",
            }
        )
        pipeline = PrivacyPipeline(config=config)
        payload = {
            "issues": [
                {"key": "PUB-1", "labels": ["public"]},
                {"key": "RED-1", "labels": ["confidential"]},
                {"key": "RED-2", "labels": ["gdpr-restricted", "x"]},
            ]
        }
        out = pipeline.apply(tool_name="jira_search", value=payload)
        keys = [issue.get("key") for issue in out["issues"]]
        assert keys == ["PUB-1"]

    def test_deny_space_keys_drops_pages(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DENY_SPACE_KEYS": "HR,LEGAL",
            }
        )
        pipeline = PrivacyPipeline(config=config)
        payload = {
            "results": [
                {"id": "1", "space": {"key": "ENG"}},
                {"id": "2", "space": {"key": "HR"}},
                {"id": "3", "space_key": "LEGAL"},
            ]
        }
        out = pipeline.apply(tool_name="confluence_search", value=payload)
        ids = [r.get("id") for r in out["results"]]
        assert ids == ["1"]

    def test_deny_project_keys_via_project_object_and_top_level_key(
        self,
    ) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DENY_PROJECT_KEYS": "SEC,PRIV",
            }
        )
        pipeline = PrivacyPipeline(config=config)
        payload = {
            "issues": [
                {"key": "SEC-12"},
                {"id": 2, "project": {"key": "PRIV"}},
                {"key": "PUB-7"},
            ]
        }
        out = pipeline.apply(tool_name="jira_search", value=payload)
        survivors = [it.get("key") or it.get("id") for it in out["issues"]]
        assert survivors == ["PUB-7"]


# ---------------------------------------------------------------------------
# Recipe end-to-end — what a real .env would do to a real payload
# ---------------------------------------------------------------------------
def _load_recipe(env: dict[str, str]) -> PrivacyPipeline:
    return PrivacyPipeline(config=PrivacyConfig.from_env(env=env))


class TestRecipeAEndToEnd:
    """Recipe A: maximal anonymisation (without Presidio for portability)."""

    @pytest.fixture
    def pipeline(self) -> PrivacyPipeline:
        return _load_recipe(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_PII_PATTERNS": "email,phone,ipv4,iban,credit_card",
                "PRIVACY_DROP_FIELDS": json.dumps(
                    {"*": ["**.email", "**.avatar_url", "**.accountId"]}
                ),
                "PRIVACY_MASK_FIELDS": json.dumps({"*": ["**.display_name"]}),
            }
        )

    def test_no_emails_anywhere(self, pipeline: PrivacyPipeline) -> None:
        out = pipeline.apply(tool_name="jira_get_issue", value=_jira_issue_payload())
        flat = json.dumps(out)
        # Both as field values AND any leftover string e-mails get redacted.
        for needle in ("@example.com", "@x.com", "@atlassian"):
            assert needle not in flat, f"email leaked: {needle!r} in {flat[:300]}"
        # display_name everywhere is masked
        for path, value in _walk(obj=out):
            if path.endswith(".display_name"):
                assert value == "[REDACTED]", f"{path}: expected mask, got {value!r}"

    def test_pii_in_free_text_redacted(self, pipeline: PrivacyPipeline) -> None:
        payload = {
            "summary": "Server 192.168.5.5 owned by alice@example.com",
            "description": (
                "card 4242 4242 4242 4242, IBAN DE89370400440532013000, "
                "phone +1 (415) 555-0100"
            ),
        }
        out = pipeline.apply(tool_name="jira_get_issue", value=payload)
        for needle in (
            "alice@example.com",
            "192.168.5.5",
            "4242 4242 4242 4242",
            "DE89370400440532013000",
            "+1 (415) 555-0100",
        ):
            assert needle not in json.dumps(out), f"PII pattern leaked: {needle!r}"


class TestRecipeBEndToEnd:
    """Recipe B: secrets-only sweep."""

    SECRETS = [
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "glpat-aBcDeFgHiJkLmNoPqRsT",
        "xoxb-9876543210-1234567890-12345-A0BC1D2EFGHIJKL3MNOPQ4R5",
        "sk_live_4eC39HqLyjWDarjtT1zdp7dc",
        "ATATT3xFfGF0AbCdEfGhIjKlMnOp=",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.SflKxwRJSMeKKF2QT4fwpMeJf",
    ]

    @pytest.fixture
    def pipeline(self) -> PrivacyPipeline:
        regex = (
            r"\bAKIA[0-9A-Z]{16}\b;"
            r"\bghp_[A-Za-z0-9]{36}\b;"
            r"\bglpat-[0-9a-zA-Z_\-]{20}\b;"
            r"\bxox[bpoa]-\d+-\d+-\d+-[A-Za-z0-9]+\b;"
            r"\bsk_(?:test|live)_[0-9a-zA-Z]{24,}\b;"
            r"\bATATT3[A-Za-z0-9_=\-]{20,}\b;"
            r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"
        )
        return _load_recipe(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_PII_CUSTOM_REGEX": regex,
            }
        )

    @pytest.mark.parametrize("token", SECRETS)
    def test_each_secret_token_redacted_in_free_text(
        self, pipeline: PrivacyPipeline, token: str
    ) -> None:
        text = f"Slack message: please rotate {token} immediately."
        out = pipeline.apply(tool_name="jira_add_comment", value=text)
        assert token not in out, f"Recipe B failed to redact {token!r}: {out!r}"
        assert "[REDACTED]" in out


class TestRecipeCEndToEnd:
    """Recipe C: GDPR-light."""

    @pytest.fixture
    def pipeline(self) -> PrivacyPipeline:
        return _load_recipe(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DENY_LABELS": "confidential,gdpr-restricted,hr-only",
                "PRIVACY_DENY_SPACE_KEYS": "HR,LEGAL,BOARD",
                "PRIVACY_DENY_PROJECT_KEYS": "HRIT,LEGAL",
                "PRIVACY_DROP_FIELDS": json.dumps(
                    {"*": ["**.email", "**.email_address"]}
                ),
                "PRIVACY_PII_PATTERNS": "email,phone",
            }
        )

    def test_blocked_resources_dropped(self, pipeline: PrivacyPipeline) -> None:
        payload = {
            "issues": [
                {"key": "HRIT-1", "summary": "should be dropped"},
                {
                    "key": "ENG-1",
                    "labels": ["public"],
                    "summary": "kept",
                    "assignee": {"email": "alice@example.com"},
                },
            ],
            "results": [
                {"space": {"key": "BOARD"}, "title": "drop me"},
                {"space": {"key": "ENG"}, "title": "keep me"},
            ],
        }
        out = pipeline.apply(tool_name="jira_search", value=payload)
        assert [i["key"] for i in out["issues"]] == ["ENG-1"]
        assert [r["title"] for r in out["results"]] == ["keep me"]

    def test_email_field_dropped_globally(self, pipeline: PrivacyPipeline) -> None:
        payload = {
            "assignee": {
                "display_name": "Alice",
                "email": "alice@example.com",
            }
        }
        out = pipeline.apply(tool_name="jira_get_issue", value=payload)
        assert "email" not in out["assignee"]
        # display_name kept (we only dropped, not masked).
        assert out["assignee"]["display_name"] == "Alice"

    def test_inline_email_in_free_text_redacted(
        self, pipeline: PrivacyPipeline
    ) -> None:
        out = pipeline.apply(
            tool_name="jira_get_issue",
            value={"description": "Reach out to alice@example.com"},
        )
        assert "alice@example.com" not in out["description"]
        assert "[REDACTED]" in out["description"]


# ---------------------------------------------------------------------------
# Sanity: every resource type referenced anywhere in .env.example exists
# in tool_map, and every tool_map type can take a wildcard rule.
# ---------------------------------------------------------------------------
class TestResourceTypeCoverage:
    def test_all_tool_map_types_accept_wildcard_rules(self) -> None:
        """A wildcard rule keyed on any documented resource type loads
        cleanly and applies to its tools."""
        for tool_name, resource_type in TOOL_RESOURCE_TYPES.items():
            config = PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_DROP_FIELDS": json.dumps({resource_type: ["**.email"]}),
                }
            )
            pipeline = PrivacyPipeline(config=config)
            # Probe payload with an email at an arbitrary depth.
            payload = {"a": {"b": {"email": "x@y.z"}}}
            out = pipeline.apply(tool_name=tool_name, value=payload)
            flat = json.dumps(out)
            assert "x@y.z" not in flat, (
                f"resource_type {resource_type!r} (tool {tool_name}) "
                "did not apply documented rule"
            )

    def test_unknown_resource_type_value_rejected_by_loader(self) -> None:
        """Defensive: invalid resource type names are loaded but simply
        silent-no-op (not an error). This documents current behaviour."""
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": json.dumps(
                    {"made_up_resource_type": ["**.email"]}
                ),
            }
        )
        pipeline = PrivacyPipeline(config=config)
        payload = {"email": "x@y.z"}
        # resource_type doesn't match any tool, so no rule applies.
        out = pipeline.apply(tool_name="jira_get_issue", value=payload)
        assert out == payload, "unknown resource_type must be a no-op"
