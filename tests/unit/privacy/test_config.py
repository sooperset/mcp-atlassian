"""Tests for privacy.config."""

from __future__ import annotations

import pytest

from mcp_atlassian.privacy.config import DEFAULT_MASK_TOKEN, PrivacyConfig


class TestPrivacyConfigFromEnv:
    def test_disabled_when_master_toggle_unset(self) -> None:
        config = PrivacyConfig.from_env(env={})
        assert config.enabled is False
        assert config.mask_token == DEFAULT_MASK_TOKEN

    def test_disabled_when_master_toggle_falsy(self) -> None:
        config = PrivacyConfig.from_env(env={"PRIVACY_FILTER_ENABLED": "false"})
        assert config.enabled is False

    def test_enabled_minimum(self) -> None:
        config = PrivacyConfig.from_env(env={"PRIVACY_FILTER_ENABLED": "true"})
        assert config.enabled is True
        assert config.pii_pattern_names == []
        assert config.deny_labels == []
        assert config.drop_fields == {}
        assert config.use_presidio is False

    @pytest.mark.parametrize(
        "value",
        ["1", "true", "TRUE", "yes", "on"],
    )
    def test_truthy_master_toggle_variants(self, value: str) -> None:
        config = PrivacyConfig.from_env(env={"PRIVACY_FILTER_ENABLED": value})
        assert config.enabled is True

    def test_pii_patterns_known_names(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_PII_PATTERNS": "email, phone , ipv4",
            }
        )
        assert config.pii_pattern_names == ["email", "phone", "ipv4"]

    def test_pii_patterns_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown PRIVACY_PII_PATTERNS"):
            PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_PII_PATTERNS": "email,not_a_pattern",
                }
            )

    def test_pii_custom_regex_compiled(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_PII_CUSTOM_REGEX": (
                    r"\bAKIA[0-9A-Z]{16}\b ; \bsk_live_[0-9a-zA-Z]{24}\b"
                ),
            }
        )
        assert len(config.pii_custom_regex) == 2

    def test_pii_custom_regex_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid PRIVACY_PII_CUSTOM_REGEX"):
            PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_PII_CUSTOM_REGEX": r"[unclosed",
                }
            )

    def test_pii_custom_regex_empty_entries_dropped(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_PII_CUSTOM_REGEX": ";; \\bx\\b ;",
            }
        )
        assert len(config.pii_custom_regex) == 1

    def test_csv_lists(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DENY_LABELS": "secret,confidential",
                "PRIVACY_DENY_SPACE_KEYS": "HR, LEGAL",
                "PRIVACY_DENY_PROJECT_KEYS": "SEC",
            }
        )
        assert config.deny_labels == ["secret", "confidential"]
        assert config.deny_space_keys == ["HR", "LEGAL"]
        assert config.deny_project_keys == ["SEC"]

    def test_drop_and_mask_field_maps(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_DROP_FIELDS": (
                    '{"jira_issue": ["fields.reporter.emailAddress"]}'
                ),
                "PRIVACY_MASK_FIELDS": (
                    '{"jira_issue_list": ["issues.*.fields.assignee"]}'
                ),
            }
        )
        assert config.drop_fields == {"jira_issue": ["fields.reporter.emailAddress"]}
        assert config.mask_fields == {"jira_issue_list": ["issues.*.fields.assignee"]}

    def test_drop_fields_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="must be valid JSON"):
            PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_DROP_FIELDS": "not-json",
                }
            )

    def test_drop_fields_non_object_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_DROP_FIELDS": "[1, 2, 3]",
                }
            )

    def test_drop_fields_non_string_key_raises(self) -> None:
        # JSON object keys are always strings, so to trigger this we'd need
        # to pre-parse; instead, check the value-shape branch: list of
        # non-strings.
        with pytest.raises(ValueError, match="must be a list of strings"):
            PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_DROP_FIELDS": '{"jira_issue": [1, 2]}',
                }
            )

    def test_drop_fields_value_not_list_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a list of strings"):
            PrivacyConfig.from_env(
                env={
                    "PRIVACY_FILTER_ENABLED": "true",
                    "PRIVACY_DROP_FIELDS": '{"jira_issue": "x"}',
                }
            )

    def test_use_presidio_toggle(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_USE_PRESIDIO": "true",
            }
        )
        assert config.use_presidio is True

    def test_custom_mask_token(self) -> None:
        config = PrivacyConfig.from_env(
            env={
                "PRIVACY_FILTER_ENABLED": "true",
                "PRIVACY_MASK_TOKEN": "<<HIDDEN>>",
            }
        )
        assert config.mask_token == "<<HIDDEN>>"

    def test_default_uses_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PRIVACY_FILTER_ENABLED", raising=False)
        config = PrivacyConfig.from_env()
        assert config.enabled is False
