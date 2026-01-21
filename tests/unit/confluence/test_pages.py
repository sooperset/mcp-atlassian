"""Unit tests for the PagesMixin class."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.pages import PagesMixin
from mcp_atlassian.confluence.utils import extract_emoji_from_property
from mcp_atlassian.models.confluence import ConfluencePage


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
            page_id=page_id, expand="body.storage,version,space,children.attachment"
        )

        # Verify result structure
        assert isinstance(result, ConfluencePage)
        assert result.id == "987654321"
        assert result.title == "Example Meeting Notes"

        # Test space information
        assert result.space is not None
        assert result.space.key == "PROJ"

        # Use direct attributes instead of backward compatibility
        assert result.content == "Processed Markdown"
        assert result.id == page_id
        assert result.title == "Example Meeting Notes"
        assert result.space.key == "PROJ"
        assert result.url is not None

        # Test version information
        assert result.version is not None
        assert result.version.number == 1

        # Test attachments
        assert result.attachments is not None
        assert len(result.attachments) == 2
        assert result.attachments[0].id is not None
        assert result.attachments[1].id is not None

    def test_get_page_ancestors(self, pages_mixin):
        """Test getting page ancestors (parent pages)."""
        # Arrange
        page_id = "987654321"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock the ancestors API response
        ancestors_data = [
            {
                "id": "123456789",
                "title": "Parent Page",
                "type": "page",
                "status": "current",
                "space": {"key": "PROJ", "name": "Project Space"},
            },
            {
                "id": "111222333",
                "title": "Grandparent Page",
                "type": "page",
                "status": "current",
                "space": {"key": "PROJ", "name": "Project Space"},
            },
        ]
        pages_mixin.confluence.get_page_ancestors.return_value = ancestors_data

        # Act
        result = pages_mixin.get_page_ancestors(page_id)

        # Assert
        pages_mixin.confluence.get_page_ancestors.assert_called_once_with(page_id)

        # Verify result structure
        assert isinstance(result, list)
        assert len(result) == 2

        # Test first ancestor (parent)
        assert isinstance(result[0], ConfluencePage)
        assert result[0].id == "123456789"
        assert result[0].title == "Parent Page"
        assert result[0].space.key == "PROJ"

        # Test second ancestor (grandparent)
        assert isinstance(result[1], ConfluencePage)
        assert result[1].id == "111222333"
        assert result[1].title == "Grandparent Page"

    def test_get_page_ancestors_empty(self, pages_mixin):
        """Test getting ancestors when there are none (top-level page)."""
        # Arrange
        page_id = "987654321"
        pages_mixin.confluence.get_page_ancestors.return_value = []

        # Act
        result = pages_mixin.get_page_ancestors(page_id)

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_page_ancestors_error(self, pages_mixin):
        """Test error handling when getting ancestors."""
        # Arrange
        page_id = "987654321"
        pages_mixin.confluence.get_page_ancestors.side_effect = Exception("API Error")

        # Act
        result = pages_mixin.get_page_ancestors(page_id)

        # Assert - should return empty list on error, not raise exception
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_page_content_html(self, pages_mixin):
        """Test getting page content in HTML format."""
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock the preprocessor to return HTML
        pages_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )

        # Act
        result = pages_mixin.get_page_content("987654321", convert_to_markdown=False)

        # Assert HTML processing was used
        assert result.content == "<p>Processed HTML</p>"

    def test_get_page_by_title_success(self, pages_mixin):
        """Test getting a page by title when it exists."""
        # Setup
        space_key = "DEMO"
        title = "Example Page"

        # Mock getting the page by title
        pages_mixin.confluence.get_page_by_title.return_value = {
            "id": "987654321",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": "<p>Example content</p>"}},
            "version": {"number": 1},
        }

        # Mock the HTML processing
        pages_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )

        # Call the method
        result = pages_mixin.get_page_by_title(space_key, title)

        # Verify API calls
        pages_mixin.confluence.get_page_by_title.assert_called_once_with(
            space=space_key, title=title, expand="body.storage,version"
        )

        # Verify result
        assert result.id == "987654321"
        assert result.title == title
        assert result.content == "Processed Markdown"

    def test_get_page_by_title_space_not_found(self, pages_mixin):
        """Test getting a page when the space doesn't exist."""
        # Arrange - API returns None when space doesn't exist
        pages_mixin.confluence.get_page_by_title.return_value = None

        # Act
        result = pages_mixin.get_page_by_title("NONEXISTENT", "Page Title")

        # Assert
        assert result is None
        pages_mixin.confluence.get_page_by_title.assert_called_once_with(
            space="NONEXISTENT", title="Page Title", expand="body.storage,version"
        )

    def test_get_page_by_title_page_not_found(self, pages_mixin):
        """Test getting a page that doesn't exist."""
        # Arrange
        pages_mixin.confluence.get_page_by_title.return_value = None

        # Act
        result = pages_mixin.get_page_by_title("PROJ", "Nonexistent Page")

        # Assert
        assert result is None
        pages_mixin.confluence.get_page_by_title.assert_called_once_with(
            space="PROJ", title="Nonexistent Page", expand="body.storage,version"
        )

    def test_get_page_by_title_error_handling(self, pages_mixin):
        """Test error handling in get_page_by_title."""
        # Arrange
        pages_mixin.confluence.get_page_by_title.side_effect = KeyError("Missing key")

        # Act
        result = pages_mixin.get_page_by_title("PROJ", "Page Title")

        # Assert
        assert result is None

    def test_get_space_pages(self, pages_mixin):
        """Test getting all pages from a space."""
        # Arrange
        space_key = "PROJ"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Act
        results = pages_mixin.get_space_pages(
            space_key, start=0, limit=10, convert_to_markdown=True
        )

        # Assert
        pages_mixin.confluence.get_all_pages_from_space.assert_called_once_with(
            space=space_key, start=0, limit=10, expand="body.storage"
        )

        # Verify results
        assert len(results) == 2  # Mock has 2 pages

        # Verify each result is a ConfluencePage
        for result in results:
            assert isinstance(result, ConfluencePage)
            assert result.content == "Processed Markdown"
            assert result.space is not None
            assert result.space.key == "PROJ"

        # Verify individual pages
        assert results[0].id == "123456789"  # First page ID from mock
        assert results[0].title == "Sample Research Paper Title"

        # Verify the second page
        assert results[1].id == "987654321"  # Second page ID from mock
        assert results[1].title == "Example Meeting Notes"

    def test_create_page_success(self, pages_mixin):
        """Test creating a new page."""
        # Arrange
        space_key = "PROJ"
        title = "New Test Page"
        body = "<p>Test content</p>"
        parent_id = "987654321"

        # Mock get_page_content to return a ConfluencePage
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=ConfluencePage(
                id="123456789",
                title=title,
                content="Page content",
                space={"key": space_key, "name": "Project"},
            ),
        ):
            # Act - specify is_markdown=False since we're directly providing storage format
            result = pages_mixin.create_page(
                space_key, title, body, parent_id, is_markdown=False
            )

            # Assert
            pages_mixin.confluence.create_page.assert_called_once_with(
                space=space_key,
                title=title,
                body=body,
                parent_id=parent_id,
                representation="storage",
            )

            # Verify result is a ConfluencePage
            assert isinstance(result, ConfluencePage)
            assert result.id == "123456789"
            assert result.title == title
            assert result.content == "Page content"

    def test_create_page_error(self, pages_mixin):
        """Test error handling when creating a page."""
        # Arrange
        pages_mixin.confluence.create_page.side_effect = Exception("API Error")

        # Act/Assert
        with pytest.raises(Exception, match="API Error"):
            pages_mixin.create_page("PROJ", "Test Page", "<p>Content</p>")

    def test_create_page_with_wiki_format(self, pages_mixin):
        """Test creating a new page with wiki markup format."""
        # Arrange
        space_key = "PROJ"
        title = "Wiki Format Test Page"
        wiki_body = "h1. This is a heading\n\n* Item 1\n* Item 2"

        # Mock get_page_content to return a ConfluencePage
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=ConfluencePage(
                id="wiki123",
                title=title,
                content="Wiki page content",
                space={"key": space_key, "name": "Project"},
            ),
        ):
            # Act - use wiki format
            result = pages_mixin.create_page(
                space_key,
                title,
                wiki_body,
                is_markdown=False,
                content_representation="wiki",
            )

            # Assert
            pages_mixin.confluence.create_page.assert_called_once_with(
                space=space_key,
                title=title,
                body=wiki_body,  # Should be passed as-is
                parent_id=None,
                representation="wiki",  # Should use wiki representation
            )

            # Verify no markdown conversion happened
            pages_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

            # Verify result is a ConfluencePage
            assert isinstance(result, ConfluencePage)
            assert result.id == "wiki123"

    def test_update_page_success(self, pages_mixin):
        """Test updating an existing page."""
        # Arrange
        page_id = "987654321"
        title = "Updated Page"
        body = "<p>Updated content</p>"
        is_minor_edit = True
        version_comment = "Updated test"

        # Mock get_page_content to return a document
        mock_document = ConfluencePage(
            id=page_id,
            title=title,
            content="Updated content",
            space={"key": "PROJ", "name": "Project"},
            version={"number": 1},  # Add version information
        )
        with patch.object(pages_mixin, "get_page_content", return_value=mock_document):
            # Act - specify is_markdown=False since we're directly providing storage format
            result = pages_mixin.update_page(
                page_id,
                title,
                body,
                is_minor_edit=is_minor_edit,
                version_comment=version_comment,
                is_markdown=False,
            )

            # Assert
            # Verify update_page was called with the correct arguments
            # We now include type='page' and always_update=True parameters
            pages_mixin.confluence.update_page.assert_called_once_with(
                page_id=page_id,
                title=title,
                body=body,
                type="page",
                representation="storage",
                minor_edit=is_minor_edit,
                version_comment=version_comment,
                always_update=True,
            )

    def test_update_page_error(self, pages_mixin):
        """Test error handling when updating a page."""
        # Arrange
        pages_mixin.confluence.update_page.side_effect = Exception("API Error")

        # Act/Assert
        with pytest.raises(Exception, match="Failed to update page"):
            pages_mixin.update_page("987654321", "Test Page", "<p>Content</p>")

    def test_update_page_with_wiki_format(self, pages_mixin):
        """Test updating a page with wiki markup format."""
        # Arrange
        page_id = "wiki987"
        title = "Updated Wiki Page"
        wiki_body = "h1. Updated Heading\n\n||Header 1||Header 2||\n|Cell 1|Cell 2|"
        version_comment = "Wiki format update"

        # Mock get_page_content to return a document
        mock_document = ConfluencePage(
            id=page_id,
            title=title,
            content="Updated wiki content",
            space={"key": "PROJ", "name": "Project"},
            version={"number": 2},
        )
        with patch.object(pages_mixin, "get_page_content", return_value=mock_document):
            # Act - use wiki format
            result = pages_mixin.update_page(
                page_id,
                title,
                wiki_body,
                version_comment=version_comment,
                is_markdown=False,
                content_representation="wiki",
            )

            # Assert
            pages_mixin.confluence.update_page.assert_called_once_with(
                page_id=page_id,
                title=title,
                body=wiki_body,  # Should be passed as-is
                type="page",
                representation="wiki",  # Should use wiki representation
                minor_edit=False,
                version_comment=version_comment,
                always_update=True,
            )

            # Verify no markdown conversion happened
            pages_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

            # Verify result is a ConfluencePage
            assert isinstance(result, ConfluencePage)
            assert result.id == page_id

    def test_delete_page_success(self, pages_mixin):
        """Test successfully deleting a page."""
        # Arrange
        page_id = "987654321"
        pages_mixin.confluence.remove_page.return_value = True

        # Act
        result = pages_mixin.delete_page(page_id)

        # Assert
        pages_mixin.confluence.remove_page.assert_called_once_with(page_id=page_id)
        assert result is True

    def test_delete_page_error(self, pages_mixin):
        """Test error handling when deleting a page."""
        # Arrange
        page_id = "987654321"
        pages_mixin.confluence.remove_page.side_effect = Exception("API Error")

        # Act/Assert
        with pytest.raises(Exception, match="Failed to delete page"):
            pages_mixin.delete_page(page_id)

    def test_get_page_children_success(self, pages_mixin):
        """Test successfully getting child pages and folders."""
        # Arrange
        parent_id = "123456"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock the response from get_page_child_by_type for pages
        child_pages_data = {
            "results": [
                {
                    "id": "789012",
                    "title": "Child Page 1",
                    "type": "page",
                    "space": {"key": "DEMO"},
                    "version": {"number": 1},
                },
                {
                    "id": "345678",
                    "title": "Child Page 2",
                    "type": "page",
                    "space": {"key": "DEMO"},
                    "version": {"number": 3},
                },
            ]
        }
        # Mock the response for folders
        child_folders_data = {
            "results": [
                {
                    "id": "111222",
                    "title": "Child Folder 1",
                    "type": "folder",
                    "space": {"key": "DEMO"},
                    "version": {"number": 1},
                },
            ]
        }

        # Mock to return pages first, then folders
        pages_mixin.confluence.get_page_child_by_type.side_effect = [
            child_pages_data,
            child_folders_data,
        ]

        # Act
        results = pages_mixin.get_page_children(
            page_id=parent_id, limit=10, expand="version"
        )

        # Assert - should be called twice (once for pages, once for folders)
        assert pages_mixin.confluence.get_page_child_by_type.call_count == 2

        # Verify the results include both pages and folders
        assert len(results) == 3
        assert isinstance(results[0], ConfluencePage)
        assert results[0].id == "789012"
        assert results[0].title == "Child Page 1"
        assert results[1].id == "345678"
        assert results[1].title == "Child Page 2"
        assert results[2].id == "111222"
        assert results[2].title == "Child Folder 1"

    def test_get_page_children_without_folders(self, pages_mixin):
        """Test getting child pages only (without folders)."""
        # Arrange
        parent_id = "123456"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock the response from get_page_child_by_type
        child_pages_data = {
            "results": [
                {
                    "id": "789012",
                    "title": "Child Page 1",
                    "space": {"key": "DEMO"},
                    "version": {"number": 1},
                },
            ]
        }
        pages_mixin.confluence.get_page_child_by_type.return_value = child_pages_data

        # Act
        results = pages_mixin.get_page_children(
            page_id=parent_id, limit=10, expand="version", include_folders=False
        )

        # Assert - should only be called once (for pages only)
        pages_mixin.confluence.get_page_child_by_type.assert_called_once_with(
            page_id=parent_id, type="page", start=0, limit=10, expand="version"
        )

        # Verify the results
        assert len(results) == 1
        assert results[0].id == "789012"

    def test_get_page_children_with_content(self, pages_mixin):
        """Test getting child pages with content."""
        # Arrange
        parent_id = "123456"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock the response with body content
        child_pages_data = {
            "results": [
                {
                    "id": "789012",
                    "title": "Child Page With Content",
                    "space": {"key": "DEMO"},
                    "version": {"number": 1},
                    "body": {"storage": {"value": "<p>This is some content</p>"}},
                }
            ]
        }
        # Mock empty folders response
        child_folders_data = {"results": []}

        pages_mixin.confluence.get_page_child_by_type.side_effect = [
            child_pages_data,
            child_folders_data,
        ]

        # Mock the preprocessor
        pages_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )

        # Act
        results = pages_mixin.get_page_children(
            page_id=parent_id, expand="body.storage", convert_to_markdown=True
        )

        # Assert
        assert len(results) == 1
        assert results[0].content == "Processed Markdown"
        pages_mixin.preprocessor.process_html_content.assert_called_once_with(
            "<p>This is some content</p>",
            space_key="DEMO",
            confluence_client=pages_mixin.confluence,
        )

    def test_get_page_children_empty(self, pages_mixin):
        """Test getting child pages when there are none."""
        # Arrange
        parent_id = "123456"

        # Mock empty response for both pages and folders
        pages_mixin.confluence.get_page_child_by_type.return_value = {"results": []}

        # Act
        results = pages_mixin.get_page_children(page_id=parent_id)

        # Assert
        assert len(results) == 0

    def test_get_page_children_error(self, pages_mixin):
        """Test error handling when getting child pages."""
        # Arrange
        parent_id = "123456"

        # Mock an exception on the first call (pages)
        pages_mixin.confluence.get_page_child_by_type.side_effect = Exception(
            "API Error"
        )

        # Act
        results = pages_mixin.get_page_children(page_id=parent_id)

        # Assert - should return empty list on error, not raise exception
        assert len(results) == 0

    def test_get_page_children_folder_error_graceful(self, pages_mixin):
        """Test that folder fetch errors don't fail the whole operation."""
        # Arrange
        parent_id = "123456"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock pages success, folders failure
        child_pages_data = {
            "results": [
                {
                    "id": "789012",
                    "title": "Child Page 1",
                    "space": {"key": "DEMO"},
                    "version": {"number": 1},
                },
            ]
        }
        pages_mixin.confluence.get_page_child_by_type.side_effect = [
            child_pages_data,
            Exception("Folder API not supported"),
        ]

        # Act
        results = pages_mixin.get_page_children(page_id=parent_id)

        # Assert - should still return pages even if folder fetch fails
        assert len(results) == 1
        assert results[0].id == "789012"

    def test_get_page_success(self, pages_mixin):
        """Test successful page retrieval."""
        # Setup
        page_id = "12345"
        page_data = {
            "id": page_id,
            "title": "Test Page",
            "body": {"storage": {"value": "<p>Test content</p>"}},
            "version": {"number": 1},
            "space": {"key": "TEST", "name": "Test Space"},
        }
        pages_mixin.confluence.get_page_by_id.return_value = page_data

        # Mock the preprocessor
        pages_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed content",
        )

        # Call the method
        result = pages_mixin.get_page_content(page_id)

        # Verify the API call
        pages_mixin.confluence.get_page_by_id.assert_called_once_with(
            page_id=page_id, expand="body.storage,version,space,children.attachment"
        )

        # Verify the result
        assert result.id == page_id
        assert result.title == "Test Page"
        assert result.content == "Processed content"
        assert (
            result.version.number == 1
        )  # Compare version number instead of the whole object
        assert result.space.key == "TEST"
        assert result.space.name == "Test Space"

    def test_create_page_with_markdown(self, pages_mixin):
        """Test creating a new page with markdown content."""
        # Arrange
        space_key = "PROJ"
        title = "New Test Page"
        markdown_body = "# Test Heading\n\nThis is *markdown* content."
        parent_id = "987654321"
        storage_format = (
            "<h1>Test Heading</h1><p>This is <em>markdown</em> content.</p>"
        )

        # Mock the markdown conversion
        pages_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            storage_format
        )

        # Mock get_page_content to return a ConfluencePage
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=ConfluencePage(
                id="123456789",
                title=title,
                content="Converted content",
                space={"key": space_key, "name": "Project"},
            ),
        ):
            # Act
            result = pages_mixin.create_page(
                space_key=space_key,
                title=title,
                body=markdown_body,
                parent_id=parent_id,
                is_markdown=True,
            )

            # Assert
            # Verify markdown was converted
            pages_mixin.preprocessor.markdown_to_confluence_storage.assert_called_once_with(
                markdown_body, enable_heading_anchors=False
            )

            # Verify create_page was called with the converted content
            pages_mixin.confluence.create_page.assert_called_once_with(
                space=space_key,
                title=title,
                body=storage_format,
                parent_id=parent_id,
                representation="storage",
            )

            # Verify result
            assert isinstance(result, ConfluencePage)
            assert result.id == "123456789"
            assert result.title == title

    def test_create_page_with_storage_format(self, pages_mixin):
        """Test creating a page with pre-converted storage format content."""
        # Arrange
        space_key = "PROJ"
        title = "New Test Page"
        storage_body = "<p>Already in storage format</p>"

        # Mock get_page_content
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=ConfluencePage(id="123456789", title=title),
        ):
            # Act
            result = pages_mixin.create_page(
                space_key=space_key, title=title, body=storage_body, is_markdown=False
            )

            # Assert
            # Verify conversion was not called
            pages_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

            # Verify create_page was called with the original content
            pages_mixin.confluence.create_page.assert_called_once_with(
                space=space_key,
                title=title,
                body=storage_body,
                parent_id=None,
                representation="storage",
            )

    def test_update_page_with_markdown(self, pages_mixin):
        """Test updating a page with markdown content."""
        # Arrange
        page_id = "987654321"
        title = "Updated Page"
        markdown_body = "# Updated Content\n\nThis is *updated* content."
        storage_format = (
            "<h1>Updated Content</h1><p>This is <em>updated</em> content.</p>"
        )

        # Mock the markdown conversion
        pages_mixin.preprocessor.markdown_to_confluence_storage.return_value = (
            storage_format
        )

        # Mock get_page_content
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=ConfluencePage(
                id=page_id,
                title=title,
                content="Updated content",
                space={"key": "PROJ", "name": "Project"},
            ),
        ):
            # Act
            result = pages_mixin.update_page(
                page_id=page_id,
                title=title,
                body=markdown_body,
                is_minor_edit=True,
                version_comment="Updated test",
                is_markdown=True,
            )

            # Assert
            # Verify markdown was converted
            pages_mixin.preprocessor.markdown_to_confluence_storage.assert_called_once_with(
                markdown_body, enable_heading_anchors=False
            )

            # Verify update_page was called with the converted content
            pages_mixin.confluence.update_page.assert_called_once_with(
                page_id=page_id,
                title=title,
                body=storage_format,
                type="page",
                representation="storage",
                minor_edit=True,
                version_comment="Updated test",
                always_update=True,
            )

    def test_update_page_with_parent_id(self, pages_mixin):
        """Test updating a page and changing its parent."""
        # Arrange
        page_id = "987654321"
        title = "Updated Page"
        body = "<p>Updated content</p>"
        parent_id = "123456789"
        is_minor_edit = False
        version_comment = "Parent changed"

        # Mock get_page_content to return a document
        mock_document = ConfluencePage(
            id=page_id,
            title=title,
            content="Updated content",
            space={"key": "PROJ", "name": "Project"},
            version={"number": 2},
        )
        with patch.object(pages_mixin, "get_page_content", return_value=mock_document):
            # Act
            result = pages_mixin.update_page(
                page_id=page_id,
                title=title,
                body=body,
                is_minor_edit=is_minor_edit,
                version_comment=version_comment,
                is_markdown=False,
                parent_id=parent_id,
            )

            # Assert
            pages_mixin.confluence.update_page.assert_called_once_with(
                page_id=page_id,
                title=title,
                body=body,
                type="page",
                representation="storage",
                minor_edit=is_minor_edit,
                version_comment=version_comment,
                always_update=True,
                parent_id=parent_id,
            )
            assert result.id == page_id
            assert result.title == title
            assert result.version.number == 2

    def test_non_oauth_still_uses_v1_api(self, pages_mixin):
        """Test that non-OAuth authentication still uses v1 API."""
        # This test ensures backward compatibility for API token/basic auth
        # Arrange
        space_key = "PROJ"
        title = "New V1 Test Page"
        body = "<p>Test content for V1</p>"

        # Mock get_page_content to return a ConfluencePage
        with patch.object(
            pages_mixin,
            "get_page_content",
            return_value=ConfluencePage(
                id="v1_123456789",
                title=title,
                content="V1 page content",
                space={"key": space_key, "name": "Project"},
            ),
        ):
            # Act
            result = pages_mixin.create_page(space_key, title, body, is_markdown=False)

            # Assert that v1 API was used
            pages_mixin.confluence.create_page.assert_called_once_with(
                space=space_key,
                title=title,
                body=body,
                parent_id=None,
                representation="storage",
            )

            # Verify result is a ConfluencePage
            assert isinstance(result, ConfluencePage)
            assert result.id == "v1_123456789"
            assert result.title == title

    @pytest.mark.parametrize(
        "body",
        [None, {"storage": None}, {"storage": {"value": None}}],
        ids=["body=None", "storage=None", "value=None"],
    )
    def test_get_page_content_missing_body_regression(self, pages_mixin, body):
        """Regression test for #760: handle missing body.storage.value."""
        pages_mixin.confluence.get_page_by_id.return_value = {
            "id": "123456",
            "title": "Test",
            "space": {"key": "TEST"},
            "body": body,
            "version": {"number": 1},
        }
        pages_mixin.config.url = "https://example.atlassian.net/wiki"
        result = pages_mixin.get_page_content("123456")
        assert isinstance(result, ConfluencePage)
        assert result.id == "123456"

    def test_get_page_by_title_missing_body_regression(self, pages_mixin):
        """Regression test for #760: get_page_by_title handles None body."""
        pages_mixin.confluence.get_page_by_title.return_value = {
            "id": "123456",
            "title": "Test",
            "space": {"key": "TEST"},
            "body": None,
            "version": {"number": 1},
        }
        pages_mixin.config.url = "https://example.atlassian.net/wiki"
        result = pages_mixin.get_page_by_title("TEST", "Test")
        assert isinstance(result, ConfluencePage)

    def test_get_space_pages_missing_body_regression(self, pages_mixin):
        """Regression test for #760: get_space_pages handles None body."""
        pages_mixin.confluence.get_all_pages_from_space.return_value = [
            {
                "id": "1",
                "title": "A",
                "space": {"key": "T"},
                "body": None,
                "version": {"number": 1},
            },
            {
                "id": "2",
                "title": "B",
                "space": {"key": "T"},
                "body": {"storage": None},
                "version": {"number": 1},
            },
        ]
        pages_mixin.config.url = "https://example.atlassian.net/wiki"
        results = pages_mixin.get_space_pages("T")
        assert len(results) == 2


class TestPagesOAuthMixin:
    """Tests for PagesMixin with OAuth authentication."""

    @pytest.fixture
    def oauth_pages_mixin(self, oauth_confluence_client):
        """Create a PagesMixin instance for OAuth testing."""
        # PagesMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = PagesMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = oauth_confluence_client.confluence
            mixin.config = oauth_confluence_client.config
            mixin.preprocessor = oauth_confluence_client.preprocessor
            return mixin

    def test_create_page_oauth_uses_v2_api(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for creating pages."""
        # Arrange
        space_key = "PROJ"
        title = "New OAuth Test Page"
        body = "<p>Test content for OAuth</p>"
        parent_id = "987654321"

        # Mock the v2 adapter
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.create_page.return_value = {
                "id": "oauth_123456789",
                "title": title,
            }

            # Mock get_page_content to return a ConfluencePage
            with patch.object(
                oauth_pages_mixin,
                "get_page_content",
                return_value=ConfluencePage(
                    id="oauth_123456789",
                    title=title,
                    content="OAuth page content",
                    space={"key": space_key, "name": "Project"},
                ),
            ):
                # Act - specify is_markdown=False since we're directly providing storage format
                result = oauth_pages_mixin.create_page(
                    space_key, title, body, parent_id, is_markdown=False
                )

                # Assert that v2 API was used instead of v1
                mock_v2_adapter.create_page.assert_called_once_with(
                    space_key=space_key,
                    title=title,
                    body=body,
                    parent_id=parent_id,
                    representation="storage",
                )

                # Verify v1 API was NOT called
                oauth_pages_mixin.confluence.create_page.assert_not_called()

                # Verify result is a ConfluencePage
                assert isinstance(result, ConfluencePage)
                assert result.id == "oauth_123456789"

    def test_create_page_oauth_with_wiki_format(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for creating pages with wiki format."""
        # Arrange
        space_key = "PROJ"
        title = "OAuth Wiki Test Page"
        wiki_body = "h1. OAuth Wiki Test\n\n* Item 1\n* Item 2"

        # Mock the v2 adapter
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.create_page.return_value = {
                "id": "oauth_wiki_123",
                "title": title,
            }

            # Mock get_page_content to return a ConfluencePage
            with patch.object(
                oauth_pages_mixin,
                "get_page_content",
                return_value=ConfluencePage(
                    id="oauth_wiki_123",
                    title=title,
                    content="OAuth wiki page content",
                    space={"key": space_key, "name": "Project"},
                ),
            ):
                # Act - use wiki format
                result = oauth_pages_mixin.create_page(
                    space_key,
                    title,
                    wiki_body,
                    is_markdown=False,
                    content_representation="wiki",
                )

                # Assert that v2 API was used with wiki representation
                mock_v2_adapter.create_page.assert_called_once_with(
                    space_key=space_key,
                    title=title,
                    body=wiki_body,
                    parent_id=None,
                    representation="wiki",
                )

                # Verify v1 API was NOT called
                oauth_pages_mixin.confluence.create_page.assert_not_called()

                # Verify no markdown conversion happened
                oauth_pages_mixin.preprocessor.markdown_to_confluence_storage.assert_not_called()

                # Verify result is a ConfluencePage
                assert isinstance(result, ConfluencePage)
                assert result.id == "oauth_wiki_123"
                assert result.title == title

    def test_update_page_oauth_uses_v2_api(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for updating pages."""
        # Arrange
        page_id = "oauth_987654321"
        title = "Updated OAuth Test Page"
        body = "<p>Updated test content for OAuth</p>"
        version_comment = "OAuth update test"

        # Mock the v2 adapter
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.update_page.return_value = {
                "id": page_id,
                "title": title,
            }

            # Mock get_page_content to return a ConfluencePage
            with patch.object(
                oauth_pages_mixin,
                "get_page_content",
                return_value=ConfluencePage(
                    id=page_id,
                    title=title,
                    content="Updated OAuth page content",
                    version={"number": 2},
                ),
            ):
                # Act - specify is_markdown=False since we're directly providing storage format
                result = oauth_pages_mixin.update_page(
                    page_id,
                    title,
                    body,
                    is_markdown=False,
                    version_comment=version_comment,
                )

                # Assert that v2 API was used instead of v1
                mock_v2_adapter.update_page.assert_called_once_with(
                    page_id=page_id,
                    title=title,
                    body=body,
                    representation="storage",
                    version_comment=version_comment,
                )

                # Verify v1 API was NOT called
                oauth_pages_mixin.confluence.update_page.assert_not_called()

                # Verify result is a ConfluencePage
                assert isinstance(result, ConfluencePage)
                assert result.id == page_id
                assert result.title == title

    def test_get_page_content_oauth_uses_v2_api(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for getting page content."""
        # Arrange
        page_id = "oauth_get_123"

        # Mock the v2 adapter
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter

            # Mock v2 API response
            mock_v2_adapter.get_page.return_value = {
                "id": page_id,
                "title": "OAuth Test Page",
                "body": {"storage": {"value": "<p>OAuth page content</p>"}},
                "space": {"key": "PROJ", "name": "Project"},
                "version": {"number": 3},
            }

            # Mock get_page_emoji
            mock_v2_adapter.get_page_emoji.return_value = None

            # Mock the preprocessor
            oauth_pages_mixin.preprocessor.process_html_content.return_value = (
                "<p>Processed HTML</p>",
                "Processed OAuth content",
            )

            # Act
            result = oauth_pages_mixin.get_page_content(
                page_id, convert_to_markdown=True
            )

            # Assert that v2 API was used instead of v1
            mock_v2_adapter.get_page.assert_called_once_with(
                page_id=page_id, expand="body.storage,version,space,children.attachment"
            )

            # Verify v1 API was NOT called
            oauth_pages_mixin.confluence.get_page_by_id.assert_not_called()

            # Verify the preprocessor was called
            oauth_pages_mixin.preprocessor.process_html_content.assert_called_once_with(
                "<p>OAuth page content</p>",
                space_key="PROJ",
                confluence_client=oauth_pages_mixin.confluence,
            )

            # Verify result is a ConfluencePage with correct data
            assert isinstance(result, ConfluencePage)
            assert result.id == page_id
            assert result.title == "OAuth Test Page"
            assert result.content == "Processed OAuth content"
            assert result.space.key == "PROJ"
            assert result.version.number == 3

    def test_delete_page_oauth_uses_v2_api(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for deleting pages."""
        # Arrange
        page_id = "oauth_delete_123"

        # Mock the v2 adapter
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.delete_page.return_value = True

            # Act
            result = oauth_pages_mixin.delete_page(page_id)

            # Assert that v2 API was used instead of v1
            mock_v2_adapter.delete_page.assert_called_once_with(page_id=page_id)

            # Verify v1 API was NOT called
            oauth_pages_mixin.confluence.remove_page.assert_not_called()

            # Verify result
            assert result is True


class TestPageEmoji:
    """Tests for page title emoji functionality."""

    @pytest.fixture
    def pages_mixin(self, confluence_client):
        """Create a PagesMixin instance for testing."""
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = PagesMixin()
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_extract_emoji_from_property_with_fallback(self, pages_mixin):
        """Test extracting emoji from property with fallback attribute."""
        value = {"id": "1f4dd", "shortName": ":memo:", "fallback": "📝"}
        result = extract_emoji_from_property(value)
        assert result == "📝"

    def test_extract_emoji_from_property_with_shortname(self, pages_mixin):
        """Test extracting emoji from property with shortName when no fallback."""
        value = {"id": "1f4dd", "shortName": ":memo:"}
        result = extract_emoji_from_property(value)
        assert result == ":memo:"

    def test_extract_emoji_from_property_with_id(self, pages_mixin):
        """Test extracting emoji from property using hex id conversion."""
        value = {"id": "1f4dd"}  # Memo emoji code point
        result = extract_emoji_from_property(value)
        assert result == "📝"

    def test_extract_emoji_from_property_string(self, pages_mixin):
        """Test extracting emoji from string property value."""
        result = extract_emoji_from_property("🚀")
        assert result == "🚀"

    def test_extract_emoji_from_property_none(self, pages_mixin):
        """Test extracting emoji from None value."""
        result = extract_emoji_from_property(None)
        assert result is None

    def test_extract_emoji_from_property_empty_dict(self, pages_mixin):
        """Test extracting emoji from empty dict."""
        result = extract_emoji_from_property({})
        assert result is None

    def test_get_page_emoji_v1_api(self, pages_mixin):
        """Test getting page emoji via v1 API (non-OAuth)."""
        # Mock the properties API response
        pages_mixin.confluence.get_page_properties.return_value = {
            "results": [
                {
                    "key": "emoji-title-published",
                    "value": {"id": "1f680", "shortName": ":rocket:", "fallback": "🚀"},
                },
            ]
        }

        result = pages_mixin._get_page_emoji("123456")
        assert result == "🚀"
        pages_mixin.confluence.get_page_properties.assert_called_once_with("123456")

    def test_get_page_emoji_draft_fallback(self, pages_mixin):
        """Test getting page emoji from draft when published not available."""
        pages_mixin.confluence.get_page_properties.return_value = {
            "results": [
                {
                    "key": "emoji-title-draft",
                    "value": {"fallback": "📋"},
                },
            ]
        }

        result = pages_mixin._get_page_emoji("123456")
        assert result == "📋"

    def test_get_page_emoji_no_emoji(self, pages_mixin):
        """Test getting page emoji when none is set."""
        pages_mixin.confluence.get_page_properties.return_value = {
            "results": [
                {"key": "some-other-property", "value": "something"},
            ]
        }

        result = pages_mixin._get_page_emoji("123456")
        assert result is None

    def test_get_page_emoji_empty_properties(self, pages_mixin):
        """Test getting page emoji with empty properties."""
        pages_mixin.confluence.get_page_properties.return_value = {"results": []}

        result = pages_mixin._get_page_emoji("123456")
        assert result is None

    def test_get_page_emoji_api_error(self, pages_mixin):
        """Test that API errors return None gracefully."""
        pages_mixin.confluence.get_page_properties.side_effect = Exception("API Error")

        result = pages_mixin._get_page_emoji("123456")
        assert result is None

    def test_get_page_content_includes_emoji(self, pages_mixin):
        """Test that get_page_content includes emoji in result."""
        page_id = "987654321"
        pages_mixin.config.url = "https://example.atlassian.net/wiki"

        # Mock the emoji properties
        pages_mixin.confluence.get_page_properties.return_value = {
            "results": [
                {
                    "key": "emoji-title-published",
                    "value": {"fallback": "📖"},
                },
            ]
        }

        result = pages_mixin.get_page_content(page_id, convert_to_markdown=True)

        assert isinstance(result, ConfluencePage)
        assert result.emoji == "📖"

    def test_get_page_by_title_includes_emoji(self, pages_mixin):
        """Test that get_page_by_title includes emoji in result."""
        space_key = "DEMO"
        title = "Example Page"

        pages_mixin.confluence.get_page_by_title.return_value = {
            "id": "987654321",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": "<p>Example content</p>"}},
            "version": {"number": 1},
        }

        pages_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed Markdown",
        )

        # Mock the emoji properties
        pages_mixin.confluence.get_page_properties.return_value = {
            "results": [
                {
                    "key": "emoji-title-published",
                    "value": {"fallback": "✨"},
                },
            ]
        }

        result = pages_mixin.get_page_by_title(space_key, title)

        assert result is not None
        assert result.emoji == "✨"

    def test_set_page_emoji_success(self, pages_mixin):
        """Test successfully setting a page emoji."""
        page_id = "set_emoji_123"

        # Mock set_page_property for creating new property
        pages_mixin.confluence.get_page_properties.return_value = {"results": []}
        pages_mixin.confluence.set_page_property.return_value = {
            "key": "emoji-title-published"
        }

        result = pages_mixin._set_page_emoji(page_id, "🚀")

        assert result is True
        # Emoji 🚀 has Unicode code point U+1F680 - Confluence expects just the hex string
        # Both published and draft properties should be set
        assert pages_mixin.confluence.set_page_property.call_count == 2
        pages_mixin.confluence.set_page_property.assert_any_call(
            page_id,
            {"key": "emoji-title-published", "value": "1f680"},
        )
        pages_mixin.confluence.set_page_property.assert_any_call(
            page_id,
            {"key": "emoji-title-draft", "value": "1f680"},
        )

    def test_set_page_emoji_update_existing(self, pages_mixin):
        """Test updating an existing page emoji."""
        page_id = "update_emoji_123"

        # The v1 API doesn't need to fetch existing properties - it just sets the value
        pages_mixin.confluence.set_page_property.return_value = {
            "key": "emoji-title-published"
        }

        result = pages_mixin._set_page_emoji(page_id, "🎉")

        assert result is True
        # Emoji 🎉 has Unicode code point U+1F389 - Confluence expects just the hex string
        # Both published and draft properties should be set
        assert pages_mixin.confluence.set_page_property.call_count == 2
        pages_mixin.confluence.set_page_property.assert_any_call(
            page_id,
            {"key": "emoji-title-published", "value": "1f389"},
        )
        pages_mixin.confluence.set_page_property.assert_any_call(
            page_id,
            {"key": "emoji-title-draft", "value": "1f389"},
        )

    def test_set_page_emoji_remove(self, pages_mixin):
        """Test removing a page emoji by setting to None."""
        page_id = "remove_emoji_123"

        # Mock existing emoji property
        pages_mixin.confluence.get_page_properties.return_value = {
            "results": [
                {
                    "key": "emoji-title-published",
                    "value": {"fallback": "📝"},
                    "version": {"number": 1},
                }
            ]
        }
        pages_mixin.confluence.delete_page_property.return_value = True

        result = pages_mixin._set_page_emoji(page_id, None)

        assert result is True
        # Both published and draft properties should be deleted
        assert pages_mixin.confluence.delete_page_property.call_count == 2
        pages_mixin.confluence.delete_page_property.assert_any_call(
            page_id, "emoji-title-published"
        )
        pages_mixin.confluence.delete_page_property.assert_any_call(
            page_id, "emoji-title-draft"
        )

    def test_set_page_emoji_remove_nonexistent(self, pages_mixin):
        """Test removing emoji when none exists still succeeds."""
        page_id = "no_emoji_123"

        # Mock delete returning an error (property doesn't exist)
        pages_mixin.confluence.delete_page_property.side_effect = Exception(
            "Property not found"
        )

        result = pages_mixin._set_page_emoji(page_id, None)

        # Should succeed even if property doesn't exist (exception caught)
        assert result is True
        # Both published and draft properties should be attempted to delete
        assert pages_mixin.confluence.delete_page_property.call_count == 2
        pages_mixin.confluence.delete_page_property.assert_any_call(
            page_id, "emoji-title-published"
        )
        pages_mixin.confluence.delete_page_property.assert_any_call(
            page_id, "emoji-title-draft"
        )

    def test_set_page_emoji_failure(self, pages_mixin):
        """Test handling failure when setting emoji."""
        page_id = "fail_emoji_123"

        pages_mixin.confluence.get_page_properties.return_value = {"results": []}
        pages_mixin.confluence.set_page_property.side_effect = Exception("API error")

        result = pages_mixin._set_page_emoji(page_id, "💥")

        assert result is False


class TestPageEmojiOAuth:
    """Tests for page emoji with OAuth authentication."""

    @pytest.fixture
    def oauth_pages_mixin(self, oauth_confluence_client):
        """Create a PagesMixin instance for OAuth testing."""
        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = PagesMixin()
            mixin.confluence = oauth_confluence_client.confluence
            mixin.config = oauth_confluence_client.config
            mixin.preprocessor = oauth_confluence_client.preprocessor
            return mixin

    def test_get_page_emoji_oauth_uses_v2_api(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for getting page emoji."""
        page_id = "oauth_emoji_123"

        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.get_page_emoji.return_value = "🎉"

            result = oauth_pages_mixin._get_page_emoji(page_id)

            mock_v2_adapter.get_page_emoji.assert_called_once_with(page_id)
            assert result == "🎉"

    def test_get_page_content_oauth_includes_emoji(self, oauth_pages_mixin):
        """Test that OAuth get_page_content includes emoji in result."""
        page_id = "oauth_get_123"

        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter

            mock_v2_adapter.get_page.return_value = {
                "id": page_id,
                "title": "OAuth Test Page",
                "body": {"storage": {"value": "<p>OAuth page content</p>"}},
                "space": {"key": "PROJ", "name": "Project"},
                "version": {"number": 3},
            }
            mock_v2_adapter.get_page_emoji.return_value = "🔥"

            oauth_pages_mixin.preprocessor.process_html_content.return_value = (
                "<p>Processed HTML</p>",
                "Processed OAuth content",
            )

            result = oauth_pages_mixin.get_page_content(
                page_id, convert_to_markdown=True
            )

            assert isinstance(result, ConfluencePage)
            assert result.emoji == "🔥"

    def test_set_page_emoji_oauth_uses_v2_api(self, oauth_pages_mixin):
        """Test that OAuth authentication uses v2 API for setting page emoji."""
        page_id = "oauth_set_emoji_123"

        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.set_page_emoji.return_value = True

            result = oauth_pages_mixin._set_page_emoji(page_id, "🚀")

            mock_v2_adapter.set_page_emoji.assert_called_once_with(page_id, "🚀")
            assert result is True

    def test_set_page_emoji_oauth_remove(self, oauth_pages_mixin):
        """Test that OAuth can remove emoji by setting to None."""
        page_id = "oauth_remove_emoji_123"

        with patch(
            "mcp_atlassian.confluence.pages.ConfluenceV2Adapter"
        ) as mock_v2_adapter_class:
            mock_v2_adapter = MagicMock()
            mock_v2_adapter_class.return_value = mock_v2_adapter
            mock_v2_adapter.set_page_emoji.return_value = True

            result = oauth_pages_mixin._set_page_emoji(page_id, None)

            mock_v2_adapter.set_page_emoji.assert_called_once_with(page_id, None)
            assert result is True
