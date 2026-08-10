"""Tests for AIO Tests folder operations."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.aio.folders import normalize_folder_path
from tests.fixtures.aio_mocks import MOCK_AIO_FOLDER_DETAILS, MOCK_AIO_FOLDER_TREE


@pytest.fixture
def fetcher(aio_fetcher):
    """Provide a fetcher whose folder tree call returns the mock tree."""
    aio_fetcher.get = MagicMock(return_value=MOCK_AIO_FOLDER_TREE)
    aio_fetcher.put = MagicMock(return_value=MOCK_AIO_FOLDER_DETAILS)
    return aio_fetcher


class TestNormalizeFolderPath:
    """Tests for folder path parsing."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("Regression", ["Regression"]),
            ("/Regression/Checkout", ["Regression", "Checkout"]),
            ("Regression/Checkout/", ["Regression", "Checkout"]),
            ("  /A / B ", ["A", "B"]),
        ],
    )
    def test_splits_paths(self, path, expected):
        """Paths split into their folder names, ignoring empty segments."""
        assert normalize_folder_path(path) == expected

    @pytest.mark.parametrize("path", ["", "/", "   ", "//"])
    def test_empty_paths_raise(self, path):
        """A path with no folder name is rejected."""
        with pytest.raises(ValueError, match="at least one folder name"):
            normalize_folder_path(path)


class TestGetFolderHierarchy:
    """Tests for get_folder_hierarchy."""

    def test_builds_nested_tree_with_paths(self, fetcher):
        """Children get a resolved parent ID and full path."""
        roots = fetcher.get_folder_hierarchy("PROJ")

        assert [root.name for root in roots] == ["Regression", "Smoke"]
        checkout = roots[0].children[0]
        assert checkout.path == "/Regression/Checkout"
        assert checkout.parent_id == 100
        fetcher.get.assert_called_once_with("/project/PROJ/testcase/folder")

    def test_uses_requested_folder_type(self, fetcher):
        """The folder type selects the tree to read."""
        fetcher.get_folder_hierarchy("PROJ", "testcycle")

        fetcher.get.assert_called_once_with("/project/PROJ/testcycle/folder")

    def test_rejects_unknown_folder_type(self, fetcher):
        """An unsupported folder type is rejected before any call."""
        with pytest.raises(ValueError, match="Invalid folder type"):
            fetcher.get_folder_hierarchy("PROJ", "testplan")

    def test_result_is_cached(self, fetcher):
        """The tree is fetched once per project and folder type."""
        fetcher.get_folder_hierarchy("PROJ")
        fetcher.get_folder_hierarchy("PROJ")

        assert fetcher.get.call_count == 1

    def test_flatten_returns_all_folders(self, fetcher):
        """Flattening yields parents before children with full paths."""
        folders = fetcher.flatten_folders("PROJ")

        assert [folder.path for folder in folders] == [
            "/Regression",
            "/Regression/Checkout",
            "/Regression/Login",
            "/Smoke",
        ]

    def test_simplified_dict_nests_children(self, fetcher):
        """The simplified tree keeps its children."""
        root = fetcher.get_folder_hierarchy("PROJ")[0].to_simplified_dict()

        assert root["name"] == "Regression"
        assert [child["name"] for child in root["children"]] == ["Checkout", "Login"]


class TestFindFolder:
    """Tests for find_folder."""

    def test_finds_by_full_path(self, fetcher):
        """A full path matches exactly one folder."""
        folder = fetcher.find_folder("PROJ", "/Regression/Checkout")

        assert folder is not None
        assert folder.id == 101

    def test_finds_by_unique_name(self, fetcher):
        """A bare name works when it is unique in the project."""
        folder = fetcher.find_folder("PROJ", "Login")

        assert folder is not None
        assert folder.id == 102

    def test_match_is_case_insensitive(self, fetcher):
        """Folder lookups ignore case."""
        assert fetcher.find_folder("PROJ", "checkout").id == 101

    def test_missing_folder_returns_none(self, fetcher):
        """An unknown folder is simply not found."""
        assert fetcher.find_folder("PROJ", "/Nope") is None

    def test_ambiguous_name_raises(self, aio_fetcher):
        """A duplicated folder name requires a full path."""
        aio_fetcher.get = MagicMock(
            return_value=[
                {"ID": 1, "name": "A", "children": [{"ID": 2, "name": "Shared"}]},
                {"ID": 3, "name": "B", "children": [{"ID": 4, "name": "Shared"}]},
            ]
        )

        with pytest.raises(ValueError, match="is ambiguous"):
            aio_fetcher.find_folder("PROJ", "Shared")


class TestCreateFolder:
    """Tests for create_folder."""

    def test_creates_hierarchy(self, fetcher):
        """The folder path is sent as a hierarchy of names."""
        folder = fetcher.create_folder("PROJ", "/Regression/Checkout")

        fetcher.put.assert_called_once_with(
            "/project/PROJ/testcase/folder/hierarchy",
            json={"folderHierarchy": ["Regression", "Checkout"]},
        )
        assert folder.id == 101
        assert folder.name == "Checkout"

    def test_creates_under_parent_folder(self, fetcher):
        """A base folder ID scopes the created hierarchy."""
        fetcher.create_folder("PROJ", "Checkout", parent_folder_id=100)

        _, kwargs = fetcher.put.call_args
        assert kwargs["json"] == {
            "folderHierarchy": ["Checkout"],
            "baseFolderId": 100,
        }

    def test_invalidates_cached_tree(self, fetcher):
        """The cached tree is dropped so later reads see the new folder."""
        fetcher.get_folder_hierarchy("PROJ")
        fetcher.create_folder("PROJ", "New")
        fetcher.get_folder_hierarchy("PROJ")

        # One call before creation and one re-fetch afterwards while resolving
        # the new folder's path; the read after that is served from the
        # repopulated cache.
        assert fetcher.get.call_count == 2

    def test_rejects_unknown_folder_type(self, fetcher):
        """An unsupported folder type is rejected before any call."""
        with pytest.raises(ValueError, match="Invalid folder type"):
            fetcher.create_folder("PROJ", "New", folder_type="testplan")
        fetcher.put.assert_not_called()


class TestResolveFolderId:
    """Tests for resolve_folder_id."""

    def test_passes_through_integer(self, fetcher):
        """An integer is already a folder ID."""
        assert fetcher.resolve_folder_id("PROJ", 42) == 42
        fetcher.get.assert_not_called()

    def test_passes_through_numeric_string(self, fetcher):
        """A numeric string is treated as a folder ID."""
        assert fetcher.resolve_folder_id("PROJ", "42") == 42

    def test_resolves_path(self, fetcher):
        """A path resolves to the matching folder ID."""
        assert fetcher.resolve_folder_id("PROJ", "/Regression/Login") == 102

    def test_missing_folder_raises_by_default(self, fetcher):
        """Unknown folders are an error unless creation is requested."""
        with pytest.raises(ValueError, match="was not found"):
            fetcher.resolve_folder_id("PROJ", "/Nope")
        fetcher.put.assert_not_called()

    def test_missing_folder_can_be_created(self, fetcher):
        """With create_missing the hierarchy is created on demand."""
        folder_id = fetcher.resolve_folder_id("PROJ", "/Nope", create_missing=True)

        assert folder_id == 101
        fetcher.put.assert_called_once()

    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_empty_values_return_none(self, fetcher, value):
        """Empty values resolve to nothing."""
        assert fetcher.resolve_folder_id("PROJ", value) is None
