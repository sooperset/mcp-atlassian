"""Tests for privacy.resource_filter."""

from __future__ import annotations

from mcp_atlassian.privacy.resource_filter import ResourceFilter
from mcp_atlassian.privacy.stats import FilterStats


class TestResourceFilter:
    def test_no_rules_passes_through(self) -> None:
        f = ResourceFilter(deny_labels=[], deny_space_keys=[], deny_project_keys=[])
        assert f.has_rules is False
        original = {"items": [{"key": "A-1"}]}
        assert f.apply(value=original) == original

    def test_drops_by_project_key_via_project_object(self) -> None:
        f = ResourceFilter(
            deny_labels=[],
            deny_space_keys=[],
            deny_project_keys=["SEC"],
        )
        result = f.apply(
            value={
                "issues": [
                    {"id": 1, "project": {"key": "SEC"}},
                    {"id": 2, "project": {"key": "PUB"}},
                ]
            }
        )
        assert result == {"issues": [{"id": 2, "project": {"key": "PUB"}}]}

    def test_drops_by_project_key_via_top_level_key(self) -> None:
        f = ResourceFilter(
            deny_labels=[],
            deny_space_keys=[],
            deny_project_keys=["SEC"],
        )
        result = f.apply(
            value=[
                {"key": "SEC-12", "summary": "x"},
                {"key": "PUB-7", "summary": "y"},
            ]
        )
        assert result == [{"key": "PUB-7", "summary": "y"}]

    def test_drops_by_space_key_via_space_object(self) -> None:
        f = ResourceFilter(
            deny_labels=[],
            deny_space_keys=["HR"],
            deny_project_keys=[],
        )
        result = f.apply(
            value={
                "results": [
                    {"id": 1, "space": {"key": "HR"}},
                    {"id": 2, "space": {"key": "ENG"}},
                ]
            }
        )
        assert result == {"results": [{"id": 2, "space": {"key": "ENG"}}]}

    def test_drops_by_flat_space_key(self) -> None:
        f = ResourceFilter(
            deny_labels=[],
            deny_space_keys=["HR"],
            deny_project_keys=[],
        )
        result = f.apply(
            value=[{"id": 1, "space_key": "HR"}, {"id": 2, "space_key": "ENG"}]
        )
        assert result == [{"id": 2, "space_key": "ENG"}]

    def test_drops_by_label_string_list(self) -> None:
        f = ResourceFilter(
            deny_labels=["confidential"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        result = f.apply(
            value=[
                {"id": 1, "labels": ["public"]},
                {"id": 2, "labels": ["confidential"]},
            ]
        )
        assert result == [{"id": 1, "labels": ["public"]}]

    def test_drops_by_label_dict_list(self) -> None:
        f = ResourceFilter(
            deny_labels=["secret"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        result = f.apply(value=[{"id": 1, "labels": [{"name": "secret"}]}])
        assert result == []

    def test_keeps_when_label_list_unrelated_shape(self) -> None:
        f = ResourceFilter(
            deny_labels=["secret"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        result = f.apply(value=[{"id": 1, "labels": [42, None]}])
        assert result == [{"id": 1, "labels": [42, None]}]

    def test_walks_nested_lists(self) -> None:
        f = ResourceFilter(
            deny_labels=["x"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        result = f.apply(
            value={
                "outer": {
                    "inner": [
                        {"labels": ["x"]},
                        {"labels": ["y"]},
                    ]
                }
            }
        )
        assert result == {"outer": {"inner": [{"labels": ["y"]}]}}

    def test_skips_when_labels_not_a_list(self) -> None:
        f = ResourceFilter(
            deny_labels=["x"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        # `labels` as a non-list shape (e.g., a string or dict) is ignored.
        result = f.apply(value=[{"id": 1, "labels": "x"}])
        assert result == [{"id": 1, "labels": "x"}]

    def test_does_not_filter_non_dict_top_level(self) -> None:
        f = ResourceFilter(
            deny_labels=["x"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        # A scalar top-level value is returned unchanged.
        assert f.apply(value="hello") == "hello"
        assert f.apply(value=42) == 42


class TestResourceFilterTopLevel:
    """Top-level single-resource matches wipe the whole payload."""

    def test_top_level_label_match_returns_empty_dict(self) -> None:
        f = ResourceFilter(
            deny_labels=["confidential"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        out = f.apply(
            value={"key": "PROJ-1", "labels": ["confidential"], "summary": "x"}
        )
        assert out == {}

    def test_top_level_project_key_match_returns_empty_dict(self) -> None:
        f = ResourceFilter(
            deny_labels=[],
            deny_space_keys=[],
            deny_project_keys=["SEC"],
        )
        out = f.apply(value={"key": "SEC-12", "summary": "x"})
        assert out == {}

    def test_top_level_space_key_match_returns_empty_dict(self) -> None:
        f = ResourceFilter(
            deny_labels=[],
            deny_space_keys=["HR"],
            deny_project_keys=[],
        )
        out = f.apply(value={"id": 1, "space": {"key": "HR"}})
        assert out == {}

    def test_top_level_no_match_returns_payload_intact(self) -> None:
        f = ResourceFilter(
            deny_labels=["confidential"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        original = {"key": "PROJ-1", "labels": ["public"]}
        assert f.apply(value=original) == original


class TestResourceFilterStats:
    """``FilterStats`` is bumped exactly once per dropped resource."""

    def test_top_level_drop_counts_once(self) -> None:
        f = ResourceFilter(
            deny_labels=["confidential"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        stats = FilterStats()
        f.apply(value={"key": "PROJ-1", "labels": ["confidential"]}, stats=stats)
        assert stats.resources_dropped == 1

    def test_list_drops_count_per_item(self) -> None:
        f = ResourceFilter(
            deny_labels=["confidential"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        stats = FilterStats()
        f.apply(
            value={
                "issues": [
                    {"key": "PUB-1", "labels": ["public"]},
                    {"key": "RED-1", "labels": ["confidential"]},
                    {"key": "RED-2", "labels": ["confidential"]},
                ]
            },
            stats=stats,
        )
        assert stats.resources_dropped == 2

    def test_no_match_no_increment(self) -> None:
        f = ResourceFilter(
            deny_labels=["confidential"],
            deny_space_keys=[],
            deny_project_keys=[],
        )
        stats = FilterStats()
        f.apply(value={"key": "PUB-1", "labels": ["public"]}, stats=stats)
        assert stats.resources_dropped == 0
