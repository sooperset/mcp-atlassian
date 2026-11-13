"""Unit tests for Confluence folder operations."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.folders import FoldersMixin
from mcp_atlassian.models.confluence import ConfluenceFolder

BASE_URL = "https://example.atlassian.net/wiki"

FOLDER_RESPONSE = {
    "id": "3755409420",
    "type": "folder",
    "title": "Runbooks",
    "status": "current",
    "spaceId": "2810380295",
    "parentId": "2810380568",
    "parentType": "page",
    "version": {"number": 1},
    "_links": {"webui": "/spaces/DOCS/folder/3755409420", "base": BASE_URL},
}


def _make_mixin(*, is_cloud: bool = True, auth_type: str = "basic") -> FoldersMixin:
    with patch(
        "mcp_atlassian.confluence.folders.ConfluenceClient.__init__"
    ) as mock_init:
        mock_init.return_value = None
        mixin = FoldersMixin()
    mixin.confluence = MagicMock()
    mixin.confluence.url = BASE_URL
    mixin.config = MagicMock()
    mixin.config.is_cloud = is_cloud
    mixin.config.auth_type = auth_type
    mixin.config.url = BASE_URL
    return mixin


@pytest.fixture
def mock_adapter():
    """Patch the v2 adapter used by the folders mixin."""
    with patch("mcp_atlassian.confluence.folders.ConfluenceV2Adapter") as cls:
        adapter = cls.return_value
        adapter.create_folder.return_value = FOLDER_RESPONSE
        adapter.get_folder.return_value = FOLDER_RESPONSE
        adapter.get_folder_direct_children.return_value = (
            [{"id": "42", "title": "Child page", "type": "page", "status": "current"}],
            False,
        )
        yield adapter


class TestFoldersMixin:
    """Tests for FoldersMixin."""

    def test_create_folder(self, mock_adapter):
        mixin = _make_mixin()

        folder = mixin.create_folder("DOCS", "Runbooks", parent_id="2810380568")

        mock_adapter.create_folder.assert_called_once_with(
            space_key="DOCS", title="Runbooks", parent_id="2810380568"
        )
        assert isinstance(folder, ConfluenceFolder)
        assert folder.id == "3755409420"
        assert folder.url == f"{BASE_URL}/spaces/DOCS/folder/3755409420"

    def test_get_folder_without_children(self, mock_adapter):
        mixin = _make_mixin()

        folder = mixin.get_folder("3755409420")

        mock_adapter.get_folder.assert_called_once_with("3755409420")
        mock_adapter.get_folder_direct_children.assert_not_called()
        assert folder.children is None

    def test_get_folder_with_children(self, mock_adapter):
        mixin = _make_mixin()

        folder = mixin.get_folder("3755409420", include_children=True)

        mock_adapter.get_folder_direct_children.assert_called_once_with("3755409420")
        assert folder.children is not None
        assert folder.children[0]["id"] == "42"
        assert folder.children_has_more is False

    def test_delete_folder(self, mock_adapter):
        mixin = _make_mixin()

        mixin.delete_folder("3755409420")

        mock_adapter.delete_folder.assert_called_once_with("3755409420")

    @pytest.mark.parametrize("position", ["append", "before", "after"])
    def test_move_folder(self, mock_adapter, position):
        mixin = _make_mixin()

        folder = mixin.move_folder("3755409420", "999", position=position)

        mock_adapter.move_page.assert_called_once_with(
            page_id="3755409420", position=position, target_id="999"
        )
        mock_adapter.get_folder.assert_called_once_with("3755409420")
        assert folder.id == "3755409420"

    def test_move_folder_rejects_invalid_position(self, mock_adapter):
        mixin = _make_mixin()

        with pytest.raises(ValueError, match="Invalid position"):
            mixin.move_folder("3755409420", "999", position="above")

        mock_adapter.move_page.assert_not_called()

    def test_server_dc_is_rejected(self, mock_adapter):
        mixin = _make_mixin(is_cloud=False)

        with pytest.raises(ValueError, match="only available for Confluence Cloud"):
            mixin.create_folder("DOCS", "Runbooks")

        mock_adapter.create_folder.assert_not_called()

    @pytest.mark.parametrize(
        ("auth_type", "expected_base_url"),
        [("basic", "https://config.example/wiki"), ("oauth", BASE_URL)],
    )
    def test_adapter_base_url_follows_auth_type(self, auth_type, expected_base_url):
        mixin = _make_mixin(auth_type=auth_type)
        mixin.config.url = "https://config.example/wiki"

        with patch("mcp_atlassian.confluence.folders.ConfluenceV2Adapter") as cls:
            mixin._folder_v2_adapter()

        cls.assert_called_once_with(
            session=mixin.confluence._session, base_url=expected_base_url
        )


class TestConfluenceFolderModel:
    """Tests for the ConfluenceFolder model."""

    def test_from_api_response(self):
        folder = ConfluenceFolder.from_api_response(FOLDER_RESPONSE)

        assert folder.to_simplified_dict() == {
            "id": "3755409420",
            "title": "Runbooks",
            "type": "folder",
            "status": "current",
            "space_id": "2810380295",
            "parent_id": "2810380568",
            "parent_type": "page",
            "version": 1,
            "url": f"{BASE_URL}/spaces/DOCS/folder/3755409420",
        }

    def test_url_uses_base_url_kwarg_when_links_have_no_base(self):
        data = {**FOLDER_RESPONSE, "_links": {"webui": "/spaces/DOCS/folder/1"}}

        folder = ConfluenceFolder.from_api_response(data, base_url=f"{BASE_URL}/")

        assert folder.url == f"{BASE_URL}/spaces/DOCS/folder/1"

    def test_empty_response(self):
        folder = ConfluenceFolder.from_api_response({})

        assert folder.url is None
        assert "children" not in folder.to_simplified_dict()

    def test_children_are_simplified(self):
        folder = ConfluenceFolder.from_api_response(FOLDER_RESPONSE)
        folder.children = [
            {
                "id": 42,
                "title": "Child",
                "type": "page",
                "status": "current",
                "spaceId": "2810380295",
                "childPosition": 7,
            }
        ]
        folder.children_has_more = True

        result = folder.to_simplified_dict()

        assert result["children"] == [
            {"id": "42", "title": "Child", "type": "page", "status": "current"}
        ]
        assert result["children_has_more"] is True
