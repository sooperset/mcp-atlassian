"""Tests for privacy.pipeline."""

from __future__ import annotations

from mcp_atlassian.privacy.config import PrivacyConfig
from mcp_atlassian.privacy.pipeline import PrivacyPipeline


class TestPrivacyPipeline:
    def test_noop_when_no_rules(self) -> None:
        pipeline = PrivacyPipeline(config=PrivacyConfig(enabled=True))
        assert pipeline.is_noop is True
        assert pipeline.apply(tool_name="x", value={"a": 1}) == {"a": 1}

    def test_pii_only_redacts_strings(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        assert pipeline.is_noop is False
        assert (
            pipeline.apply(tool_name="t", value="ping alice@example.com") == "ping [X]"
        )

    def test_field_filter_runs_for_known_resource_type(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            drop_fields={"jira_issue": ["fields.reporter.emailAddress"]},
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(
            tool_name="jira_get_issue",
            value={
                "fields": {
                    "reporter": {
                        "displayName": "Alice",
                        "emailAddress": "a@example.com",
                    }
                }
            },
        )
        assert out == {"fields": {"reporter": {"displayName": "Alice"}}}

    def test_field_filter_skipped_for_unknown_tool_without_wildcard(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            drop_fields={"jira_issue": ["fields.x"]},
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(
            tool_name="totally_unknown_tool",
            value={"fields": {"x": "kept"}},
        )
        assert out == {"fields": {"x": "kept"}}

    def test_resource_filter_then_field_then_pii(self) -> None:
        config = PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            deny_labels=["secret"],
            drop_fields={"jira_issue_list": ["issues.*.assignee"]},
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(
            tool_name="jira_search",
            value={
                "issues": [
                    {
                        "key": "A-1",
                        "labels": ["secret"],
                        "assignee": "a@x.com",
                    },
                    {
                        "key": "A-2",
                        "labels": ["public"],
                        "assignee": "b@x.com",
                    },
                ]
            },
        )
        # Item 1 dropped by resource filter; item 2 keeps key+labels but
        # loses assignee, no email PII left to redact.
        assert out == {
            "issues": [
                {"key": "A-2", "labels": ["public"]},
            ]
        }

    def test_pii_redaction_applies_after_field_drop(self) -> None:
        # PII redaction should not see fields that were dropped.
        config = PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            drop_fields={"*": ["secret_field"]},
            mask_token="[X]",
        )
        pipeline = PrivacyPipeline(config=config)
        out = pipeline.apply(
            tool_name="any_tool",
            value={
                "secret_field": "drop me a@b.com",
                "kept": "see x@y.com",
            },
        )
        assert out == {"kept": "see [X]"}
