"""Tests for AIO Tests tag operations."""

from unittest.mock import MagicMock

import pytest

from tests.fixtures.aio_mocks import MOCK_AIO_TAGS


@pytest.fixture
def fetcher(aio_fetcher):
    """Provide a fetcher whose tag call returns the mock tags."""
    aio_fetcher.get = MagicMock(return_value=MOCK_AIO_TAGS)
    aio_fetcher.post = MagicMock(return_value=[{"ID": 9, "name": "Nightly"}])
    return aio_fetcher


class TestGetTags:
    """Tests for get_tags."""

    def test_returns_project_tags(self, fetcher):
        """Tags are parsed into models."""
        tags = fetcher.get_tags("PROJ")

        assert [tag.to_simplified_dict() for tag in tags] == [
            {"id": 1, "name": "AutomationEligible"},
            {"id": 2, "name": "Smoke"},
        ]
        fetcher.get.assert_called_once_with("/project/PROJ/tag")

    def test_empty_response(self, aio_fetcher):
        """A project without tags returns an empty list."""
        aio_fetcher.get = MagicMock(return_value=None)

        assert aio_fetcher.get_tags("PROJ") == []


class TestCreateTags:
    """Tests for create_tags."""

    def test_posts_tag_names(self, fetcher):
        """Tags are created from their names."""
        created = fetcher.create_tags("PROJ", ["Nightly"])

        fetcher.post.assert_called_once_with(
            "/project/PROJ/tag", json=[{"name": "Nightly"}]
        )
        assert created[0].id == 9


class TestResolveTags:
    """Tests for resolve_tags."""

    def test_resolves_existing_names(self, fetcher):
        """Known tag names resolve to their IDs without creating anything."""
        resolved = fetcher.resolve_tags("PROJ", ["Smoke"])

        assert resolved == [{"tag": {"ID": 2, "name": "Smoke"}}]
        fetcher.post.assert_not_called()

    def test_name_match_is_case_insensitive(self, fetcher):
        """Tag names match without regard to case."""
        assert fetcher.resolve_tags("PROJ", ["smoke"])[0]["tag"]["ID"] == 2

    def test_numeric_values_are_ids(self, fetcher):
        """Numeric values are used directly as tag IDs."""
        assert fetcher.resolve_tags("PROJ", [1, "2"]) == [
            {"tag": {"ID": 1, "name": "AutomationEligible"}},
            {"tag": {"ID": 2, "name": "Smoke"}},
        ]

    def test_creates_missing_tags(self, fetcher):
        """Unknown tags are created so the case can reference them."""
        resolved = fetcher.resolve_tags("PROJ", ["Smoke", "Nightly"])

        fetcher.post.assert_called_once_with(
            "/project/PROJ/tag", json=[{"name": "Nightly"}]
        )
        assert resolved == [
            {"tag": {"ID": 2, "name": "Smoke"}},
            {"tag": {"name": "Nightly", "ID": 9}},
        ]

    def test_missing_tags_can_be_rejected(self, fetcher):
        """Creation can be turned off, which makes unknown tags an error."""
        with pytest.raises(ValueError, match="Unknown tags"):
            fetcher.resolve_tags("PROJ", ["Nightly"], create_missing=False)

    def test_empty_list_short_circuits(self, fetcher):
        """No tags means no API calls at all."""
        assert fetcher.resolve_tags("PROJ", []) == []
        fetcher.get.assert_not_called()
