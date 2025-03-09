"""Unit tests for the PagesMixin class."""

from unittest.mock import patch

import pytest

from mcp_atlassian.confluence.pages import PagesMixin
from mcp_atlassian.document_types import Document


class TestPagesMixin:
    """Tests for the PagesMixin class."""

    @pytest.fixture
    def pages_mixin(self, confluence_client):
        """Create a PagesMixin instance for testing."""
        # PagesMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = PagesMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_get_page_content(self, pages_mixin):
        """Test getting page content by ID."""
        # Arrange
        page_id = "987654321"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Act
        result = pages_mixin.get_page_content(page_id, convert_to_markdown=True)

        # Assert
        pages_mixin.confluence.get_page_by_id.assert_called_once_with(
            page_id=page_id, expand="body.storage,version,space"
        )

        # Verify result structure
        assert isinstance(result, Document)
        assert result.page_content == "Processed Markdown"  # from mock_preprocessor
        assert result.metadata["page_id"] == page_id
        assert result.metadata["title"] == "Example Meeting Notes"
        assert result.metadata["space_key"] == "PROJ"
        assert (
            result.metadata["url"]
            == "https://example.atlassian.net/wiki/spaces/PROJ/pages/987654321"
        )

    def test_get_page_content_html(self, pages_mixin):
        """Test getting page content in HTML format."""
        # Act
        result = pages_mixin.get_page_content("987654321", convert_to_markdown=False)

        # Assert
        assert result.page_content == "<p>Processed HTML</p>"  # from mock_preprocessor

    def test_get_page_by_title_success(self, pages_mixin):
        """Test getting a page by title."""
        # Arrange
        space_key = "PROJ"
        title = "Example Page"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock spaces list
        pages_mixin.confluence.get_all_spaces.return_value = {
            "results": [{"key": "PROJ"}, {"key": "TEST"}]
        }

        # Act
        result = pages_mixin.get_page_by_title(space_key, title)

        # Assert
        pages_mixin.confluence.get_all_spaces.assert_called_once_with(
            start=0, limit=500
        )
        pages_mixin.confluence.get_page_by_title.assert_called_once_with(
            space=space_key, title=title, expand="body.storage,version"
        )

        # Verify result
        assert isinstance(result, Document)
        assert result.metadata["page_id"] == "987654321"
        assert result.metadata["title"] == "Example Meeting Notes"
        assert result.metadata["space_key"] == space_key

    def test_get_page_by_title_space_not_found(self, pages_mixin):
        """Test getting a page when the space doesn't exist."""
        # Arrange
        pages_mixin.confluence.get_all_spaces.return_value = {
            "results": [{"key": "OTHER"}, {"key": "TEST"}]
        }

        # Act
        result = pages_mixin.get_page_by_title("NONEXISTENT", "Page Title")

        # Assert
        assert result is None

    def test_get_page_by_title_page_not_found(self, pages_mixin):
        """Test getting a page that doesn't exist."""
        # Arrange
        pages_mixin.confluence.get_all_spaces.return_value = {
            "results": [{"key": "PROJ"}, {"key": "TEST"}]
        }
        pages_mixin.confluence.get_page_by_title.return_value = None

        # Act
        result = pages_mixin.get_page_by_title("PROJ", "Nonexistent Page")

        # Assert
        assert result is None

    def test_get_page_by_title_error_handling(self, pages_mixin):
        """Test error handling in get_page_by_title."""
        # Arrange
        pages_mixin.confluence.get_all_spaces.return_value = {
            "results": [{"key": "PROJ"}]
        }
        pages_mixin.confluence.get_page_by_title.side_effect = KeyError("Missing key")

        # Act
        result = pages_mixin.get_page_by_title("PROJ", "Page Title")

        # Assert
        assert result is None

    def test_get_space_pages(self, pages_mixin):
        """Test getting all pages from a space."""
        # Arrange
        space_key = "PROJ"
        start = 5
        limit = 15
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Act
        results = pages_mixin.get_space_pages(
            space_key, start=start, limit=limit, convert_to_markdown=True
        )

        # Assert
        pages_mixin.confluence.get_all_pages_from_space.assert_called_once_with(
            space=space_key, start=start, limit=limit, expand="body.storage"
        )

        # Verify results
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(doc, Document) for doc in results)

        # Check first document
        doc = results[0]
        assert doc.page_content == "Processed Markdown"  # from mock_preprocessor
        assert doc.metadata["space_key"] == space_key
        assert "page_id" in doc.metadata
        assert "title" in doc.metadata

    def test_create_page_success(self, pages_mixin):
        """Test creating a new page."""
        # Arrange
        space_key = "PROJ"
        title = "New Test Page"
        body = "<p>Test content</p>"
        parent_id = "987654321"

        # Mock get_page_content to return a document
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=Document(
                page_content="Page content",
                metadata={"page_id": "123456789", "title": title},
            ),
        ):
            # Act
            result = pages_mixin.create_page(space_key, title, body, parent_id)

            # Assert
            pages_mixin.confluence.create_page.assert_called_once_with(
                space=space_key,
                title=title,
                body=body,
                parent_id=parent_id,
                representation="storage",
            )

            # Verify result
            assert isinstance(result, Document)
            assert result.page_content == "Page content"
            assert result.metadata["page_id"] == "123456789"
            assert result.metadata["title"] == title

    def test_create_page_error(self, pages_mixin):
        """Test error handling when creating a page."""
        # Arrange
        pages_mixin.confluence.create_page.side_effect = Exception("API Error")

        # Act/Assert
        with pytest.raises(Exception, match="API Error"):
            pages_mixin.create_page("PROJ", "Test Page", "<p>Content</p>")

    def test_update_page_success(self, pages_mixin):
        """Test updating an existing page."""
        # Arrange
        page_id = "987654321"
        title = "Updated Page"
        body = "<p>Updated content</p>"
        is_minor_edit = True
        version_comment = "Updated test"

        # Mock get_page_content to return a document
        mock_document = Document(
            page_content="Updated content",
            metadata={"page_id": page_id, "title": title},
        )
        with patch.object(pages_mixin, "get_page_content", return_value=mock_document):
            # Act
            result = pages_mixin.update_page(
                page_id,
                title,
                body,
                is_minor_edit=is_minor_edit,
                version_comment=version_comment,
            )

            # Assert
            # Should first get the page
            pages_mixin.confluence.get_page_by_id.assert_called_once()

            # Then update it
            pages_mixin.confluence.update_page.assert_called_once_with(
                page_id=page_id,
                title=title,
                body=body,
                minor_edit=is_minor_edit,
                version_comment=version_comment,
            )

            # Verify result
            assert result is mock_document

    def test_update_page_error(self, pages_mixin):
        """Test error handling when updating a page."""
        # Arrange
        pages_mixin.confluence.update_page.side_effect = Exception("API Error")

        # Act/Assert
        with pytest.raises(Exception, match="API Error"):
            pages_mixin.update_page("987654321", "Test", "<p>Content</p>")
