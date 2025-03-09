"""Unit tests for the SpacesMixin class."""

from unittest.mock import patch

import pytest
import requests
from fixtures.confluence_mocks import MOCK_SPACES_RESPONSE

from mcp_atlassian.confluence.spaces import SpacesMixin


class TestSpacesMixin:
    """Tests for the SpacesMixin class."""

    @pytest.fixture
    def spaces_mixin(self, confluence_client):
        """Create a SpacesMixin instance for testing."""
        # SpacesMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.spaces.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = SpacesMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_get_spaces(self, spaces_mixin):
        """Test that get_spaces returns spaces from the Confluence client."""
        # Act
        result = spaces_mixin.get_spaces(start=10, limit=20)

        # Assert
        spaces_mixin.confluence.get_all_spaces.assert_called_once_with(
            start=10, limit=20
        )
        assert result == MOCK_SPACES_RESPONSE

    def test_get_user_contributed_spaces_success(self, spaces_mixin):
        """Test getting spaces that the user has contributed to."""
        # Arrange
        mock_result = {
            "results": [
                {
                    "content": {"_expandable": {"space": "/rest/api/space/TEST"}},
                    "resultGlobalContainer": {
                        "title": "Test Space",
                        "displayUrl": "/spaces/TEST",
                    },
                }
            ]
        }
        spaces_mixin.confluence.cql.return_value = mock_result

        # Act
        result = spaces_mixin.get_user_contributed_spaces(limit=100)

        # Assert
        spaces_mixin.confluence.cql.assert_called_once_with(
            cql="contributor = currentUser() order by lastmodified DESC", limit=100
        )
        assert result == {"TEST": {"key": "TEST", "name": "Test Space"}}

    def test_get_user_contributed_spaces_extraction_methods(self, spaces_mixin):
        """Test that the method extracts space keys from different result structures."""
        # Arrange - Test different extraction methods
        mock_results = {
            "results": [
                # Case 1: Extract from resultGlobalContainer.displayUrl
                {
                    "resultGlobalContainer": {
                        "title": "Space 1",
                        "displayUrl": "/spaces/SPACE1/pages",
                    }
                },
                # Case 2: Extract from content._expandable.space
                {
                    "content": {"_expandable": {"space": "/rest/api/space/SPACE2"}},
                    "resultGlobalContainer": {"title": "Space 2"},
                },
                # Case 3: Extract from url
                {
                    "url": "/spaces/SPACE3/pages/12345",
                    "resultGlobalContainer": {"title": "Space 3"},
                },
            ]
        }
        spaces_mixin.confluence.cql.return_value = mock_results

        # Act
        result = spaces_mixin.get_user_contributed_spaces()

        # Assert
        assert "SPACE1" in result
        assert result["SPACE1"]["name"] == "Space 1"
        assert "SPACE2" in result
        assert result["SPACE2"]["name"] == "Space 2"
        assert "SPACE3" in result
        assert result["SPACE3"]["name"] == "Space 3"

    def test_get_user_contributed_spaces_with_duplicate_spaces(self, spaces_mixin):
        """Test that duplicate spaces are deduplicated."""
        # Arrange
        mock_results = {
            "results": [
                # Same space key appears multiple times
                {
                    "resultGlobalContainer": {
                        "title": "Space 1",
                        "displayUrl": "/spaces/SPACE1",
                    }
                },
                {
                    "resultGlobalContainer": {
                        "title": "Space 1",
                        "displayUrl": "/spaces/SPACE1",
                    }
                },
                {"content": {"_expandable": {"space": "/rest/api/space/SPACE1"}}},
            ]
        }
        spaces_mixin.confluence.cql.return_value = mock_results

        # Act
        result = spaces_mixin.get_user_contributed_spaces()

        # Assert
        assert len(result) == 1
        assert "SPACE1" in result
        assert result["SPACE1"]["name"] == "Space 1"

    def test_get_user_contributed_spaces_api_error(self, spaces_mixin):
        """Test handling of API errors."""
        # Arrange
        spaces_mixin.confluence.cql.side_effect = requests.RequestException("API Error")

        # Act
        result = spaces_mixin.get_user_contributed_spaces()

        # Assert
        assert result == {}

    def test_get_user_contributed_spaces_key_error(self, spaces_mixin):
        """Test handling of KeyError when parsing results."""
        # Arrange
        spaces_mixin.confluence.cql.return_value = {"invalid_key": []}

        # Act
        result = spaces_mixin.get_user_contributed_spaces()

        # Assert
        assert result == {}

    def test_get_user_contributed_spaces_type_error(self, spaces_mixin):
        """Test handling of TypeError when processing results."""
        # Arrange
        spaces_mixin.confluence.cql.return_value = (
            None  # Will cause TypeError when iterating
        )

        # Act
        result = spaces_mixin.get_user_contributed_spaces()

        # Assert
        assert result == {}
