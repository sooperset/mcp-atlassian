"""Unit tests for the PagesMixin class."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from atlassian.errors import ApiError
from requests.exceptions import RequestException

from mcp_atlassian.confluence.pages import PagesMixin
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

        # Mock getting all spaces
        pages_mixin.confluence.get_all_spaces.return_value = {
            "results": [{"key": space_key, "name": "Demo Space"}]
        }

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
        # Arrange
        pages_mixin.confluence.get_all_spaces.return_value = {
            "results": [{"key": "OTHER"}, {"key": "TEST"}]
        }

        # Act
        result = pages_mixin.get_page_by_title("NONEXISTENT", "Page Title")

        # Assert
        assert result is None
        pages_mixin.confluence.get_all_spaces.assert_called_once()
        pages_mixin.confluence.get_page_by_title.assert_not_called()

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

    def test_attach_content_success(self, pages_mixin):
        """Test successfully attach content."""
        # Arrange
        page_id = "987654321"
        content = b"Content to attach"
        name = "test.pdf"

        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        pages_mixin.confluence.attach_content.return_value = mock_response

        result = pages_mixin.attach_content(content=content, name=name, page_id=page_id)

        # Assert
        pages_mixin.confluence.attach_content.assert_called_once_with(
            content=content, name=name, page_id=page_id
        )

        assert isinstance(result, ConfluencePage)
        assert result.id == page_id

    def test_attach_content_api_error(self, pages_mixin):
        """Test error handling when attaching content."""
        # Arrange
        page_id = "987654321"
        content = b"Content to attach"
        name = "test.pdf"
        exception_message = "Attachments are disabled or the calling user does not have permission to attach content."
        pages_mixin.confluence.attach_content.side_effect = ApiError(exception_message)

        # Act/Assert
        with pytest.raises(ApiError, match=exception_message):
            pages_mixin.attach_content(content=content, name=name, page_id=page_id)

    def test_attach_content_network_error(self, pages_mixin):
        """Test error handling when attaching content due to network error."""
        # Arrange
        page_id = "987654321"
        content = b"Content to attach"
        name = "test.pdf"
        exception_message = "Network error"
        pages_mixin.confluence.attach_content.side_effect = RequestException(
            exception_message
        )

        # Act/Assert
        with pytest.raises(RequestException, match=exception_message):
            pages_mixin.attach_content(content=content, name=name, page_id=page_id)

    def test_attach_content_unhandled_exception_propagates(self, pages_mixin):
        """Test error handling when attaching content due to unexpected error."""
        # Arrange
        page_id = "987654321"
        content = b"Content to attach"
        name = "test.pdf"
        exception_message = "Unexpected error"
        pages_mixin.confluence.attach_content.side_effect = ValueError(
            exception_message
        )

        # Act/Assert
        with pytest.raises(ValueError, match=exception_message):
            pages_mixin.attach_content(content=content, name=name, page_id=page_id)

    def test_get_page_children_success(self, pages_mixin):
        """Test successfully getting child pages."""
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
                {
                    "id": "345678",
                    "title": "Child Page 2",
                    "space": {"key": "DEMO"},
                    "version": {"number": 3},
                },
            ]
        }
        pages_mixin.confluence.get_page_child_by_type.return_value = child_pages_data

        # Act
        results = pages_mixin.get_page_children(
            page_id=parent_id, limit=10, expand="version"
        )

        # Assert
        pages_mixin.confluence.get_page_child_by_type.assert_called_once_with(
            page_id=parent_id, type="page", start=0, limit=10, expand="version"
        )

        # Verify the results
        assert len(results) == 2
        assert isinstance(results[0], ConfluencePage)
        assert results[0].id == "789012"
        assert results[0].title == "Child Page 1"
        assert results[1].id == "345678"
        assert results[1].title == "Child Page 2"

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
        pages_mixin.confluence.get_page_child_by_type.return_value = child_pages_data

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
            "<p>This is some content</p>", space_key="DEMO"
        )

    def test_get_page_children_empty(self, pages_mixin):
        """Test getting child pages when there are none."""
        # Arrange
        parent_id = "123456"

        # Mock empty response
        pages_mixin.confluence.get_page_child_by_type.return_value = {"results": []}

        # Act
        results = pages_mixin.get_page_children(page_id=parent_id)

        # Assert
        assert len(results) == 0

    def test_get_page_children_error(self, pages_mixin):
        """Test error handling when getting child pages."""
        # Arrange
        parent_id = "123456"

        # Mock an exception
        pages_mixin.confluence.get_page_child_by_type.side_effect = Exception(
            "API Error"
        )

        # Act
        results = pages_mixin.get_page_children(page_id=parent_id)

        # Assert - should return empty list on error, not raise exception
        assert len(results) == 0

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
                markdown_body
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
                markdown_body
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
