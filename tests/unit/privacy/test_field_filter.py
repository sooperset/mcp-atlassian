"""Tests for privacy.field_filter."""

from __future__ import annotations

from mcp_atlassian.privacy.field_filter import FieldFilter, build_field_filter


class TestFieldFilterDrop:
    def test_drops_exact_path(self) -> None:
        f = FieldFilter(
            drop_paths=["fields.reporter.emailAddress"],
            mask_paths=[],
            mask_token="X",
        )
        out = f.apply(
            value={
                "fields": {
                    "reporter": {
                        "displayName": "Alice",
                        "emailAddress": "alice@example.com",
                    }
                }
            }
        )
        assert out == {"fields": {"reporter": {"displayName": "Alice"}}}

    def test_drops_with_single_segment_wildcard(self) -> None:
        f = FieldFilter(
            drop_paths=["fields.*.emailAddress"], mask_paths=[], mask_token="X"
        )
        out = f.apply(
            value={
                "fields": {
                    "reporter": {"emailAddress": "a@example.com"},
                    "assignee": {"emailAddress": "b@example.com"},
                }
            }
        )
        assert out == {"fields": {"reporter": {}, "assignee": {}}}

    def test_drops_with_double_star_anywhere(self) -> None:
        f = FieldFilter(drop_paths=["**.emailAddress"], mask_paths=[], mask_token="X")
        out = f.apply(
            value={
                "emailAddress": "top@example.com",
                "fields": {"reporter": {"emailAddress": "x@example.com"}},
            }
        )
        assert out == {"fields": {"reporter": {}}}

    def test_drops_list_index_path(self) -> None:
        f = FieldFilter(drop_paths=["issues.*.assignee"], mask_paths=[], mask_token="X")
        out = f.apply(
            value={
                "issues": [
                    {"key": "A-1", "assignee": "alice"},
                    {"key": "A-2", "assignee": "bob"},
                ]
            }
        )
        assert out == {"issues": [{"key": "A-1"}, {"key": "A-2"}]}


class TestFieldFilterMask:
    def test_masks_with_token(self) -> None:
        f = FieldFilter(
            drop_paths=[],
            mask_paths=["fields.assignee"],
            mask_token="[X]",
        )
        out = f.apply(value={"fields": {"assignee": "alice"}})
        assert out == {"fields": {"assignee": "[X]"}}

    def test_drop_takes_precedence_over_mask(self) -> None:
        f = FieldFilter(
            drop_paths=["fields.x"],
            mask_paths=["fields.x"],
            mask_token="[X]",
        )
        out = f.apply(value={"fields": {"x": "secret"}})
        assert out == {"fields": {}}


class TestFieldFilterEdges:
    def test_no_rules_returns_input_unchanged(self) -> None:
        f = FieldFilter(drop_paths=[], mask_paths=[], mask_token="X")
        original = {"a": [1, 2], "b": {"c": "d"}}
        assert f.apply(value=original) == original
        assert f.has_rules is False

    def test_has_rules_when_either_set(self) -> None:
        assert (
            FieldFilter(drop_paths=["x"], mask_paths=[], mask_token="X").has_rules
            is True
        )
        assert (
            FieldFilter(drop_paths=[], mask_paths=["x"], mask_token="X").has_rules
            is True
        )

    def test_passes_through_scalar_top_level(self) -> None:
        f = FieldFilter(drop_paths=["x"], mask_paths=[], mask_token="X")
        assert f.apply(value="hello") == "hello"
        assert f.apply(value=42) == 42
        assert f.apply(value=None) is None

    def test_no_match_paths_unchanged(self) -> None:
        f = FieldFilter(drop_paths=["does.not.exist"], mask_paths=[], mask_token="X")
        out = f.apply(value={"a": {"b": 1}})
        assert out == {"a": {"b": 1}}


class TestFieldFilterPartialWildcardSegment:
    def test_partial_wildcard_segment_matches(self) -> None:
        f = FieldFilter(drop_paths=["fields.user_*"], mask_paths=[], mask_token="X")
        out = f.apply(
            value={
                "fields": {
                    "user_email": "x",
                    "user_name": "y",
                    "summary": "kept",
                }
            }
        )
        assert out == {"fields": {"summary": "kept"}}

    def test_partial_wildcard_segment_does_not_match_other(self) -> None:
        f = FieldFilter(drop_paths=["fields.user_*"], mask_paths=[], mask_token="X")
        out = f.apply(value={"fields": {"summary": "kept"}})
        assert out == {"fields": {"summary": "kept"}}

    def test_segment_regex_caches_per_pattern(self) -> None:
        # Cover the cache-hit branch by reusing the same pattern segment.
        f = FieldFilter(
            drop_paths=["a.user_*", "b.user_*"], mask_paths=[], mask_token="X"
        )
        out = f.apply(
            value={
                "a": {"user_x": 1, "kept": 2},
                "b": {"user_y": 3, "kept": 4},
            }
        )
        assert out == {"a": {"kept": 2}, "b": {"kept": 4}}


class TestFieldFilterListIndexPaths:
    def test_drops_specific_list_index(self) -> None:
        f = FieldFilter(drop_paths=["items.0"], mask_paths=[], mask_token="X")
        out = f.apply(value={"items": ["drop_me", "keep_me"]})
        assert out == {"items": ["keep_me"]}

    def test_masks_specific_list_index(self) -> None:
        f = FieldFilter(drop_paths=[], mask_paths=["items.1"], mask_token="[X]")
        out = f.apply(value={"items": ["a", "b", "c"]})
        assert out == {"items": ["a", "[X]", "c"]}


class TestBuildFieldFilter:
    def test_resource_specific_rules_only(self) -> None:
        f = build_field_filter(
            drop_fields={"jira_issue": ["fields.reporter"]},
            mask_fields={},
            mask_token="X",
            resource_type="jira_issue",
        )
        out = f.apply(value={"fields": {"reporter": "alice", "summary": "s"}})
        assert out == {"fields": {"summary": "s"}}

    def test_wildcard_resource_rules_apply_always(self) -> None:
        f = build_field_filter(
            drop_fields={"*": ["**.email_address"]},
            mask_fields={},
            mask_token="X",
            resource_type=None,
        )
        out = f.apply(value={"user": {"email_address": "x@y"}})
        assert out == {"user": {}}

    def test_unknown_resource_skips_specific_rules(self) -> None:
        f = build_field_filter(
            drop_fields={"jira_issue": ["fields.reporter"]},
            mask_fields={},
            mask_token="X",
            resource_type="unknown_type",
        )
        # No-op because no wildcard, and resource type doesn't match.
        assert f.has_rules is False

    def test_combines_specific_and_wildcard(self) -> None:
        f = build_field_filter(
            drop_fields={
                "jira_issue": ["fields.reporter"],
                "*": ["**.email_address"],
            },
            mask_fields={},
            mask_token="X",
            resource_type="jira_issue",
        )
        out = f.apply(
            value={
                "fields": {"reporter": "x"},
                "user": {"email_address": "y@z"},
            }
        )
        assert out == {"fields": {}, "user": {}}

    def test_mask_resource_specific_and_wildcard(self) -> None:
        f = build_field_filter(
            drop_fields={},
            mask_fields={
                "jira_issue": ["fields.reporter"],
                "*": ["**.email_address"],
            },
            mask_token="[X]",
            resource_type="jira_issue",
        )
        out = f.apply(
            value={
                "fields": {"reporter": {"name": "alice"}},
                "user": {"email_address": "y@z"},
            }
        )
        assert out == {
            "fields": {"reporter": "[X]"},
            "user": {"email_address": "[X]"},
        }
