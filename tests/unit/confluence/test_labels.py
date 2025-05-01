"""Unit tests for the LabelsMixin class."""

from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.confluence.labels import LabelsMixin
from mcp_atlassian.models.confluence import ConfluenceLabel


class TestLabelsMixin:
    """Tests for the LabelsMixin class."""

    @pytest.fixture
    def labels_mixin(self, confluence_client):
        """Create a LabelsMixin instance for testing."""
        # LabelsMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.labels.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = LabelsMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_get_page_labels_success(self, labels_mixin):
        """Test get_page_labels with success response."""
        # Setup
        page_id = "12345"

        # Call the method
        result = labels_mixin.get_page_labels(page_id)

        # Verify
        labels_mixin.confluence.get_page_labels.assert_called_once_with(page_id=page_id)
        assert len(result) == 3
        assert result[0].id == "456789123"
        assert result[0].prefix == "global"
        assert result[0].label == "meeting-notes"
        assert result[1].id == "456789124"
        assert result[1].prefix == "my"
        assert result[1].name == "important"
        assert result[2].id == "456789125"
        assert result[2].name == "test"

    def test_get_page_labels_api_error(self, labels_mixin):
        """Test handling of API errors."""
        # Mock the API to raise an exception
        labels_mixin.confluence.get_page_labels.side_effect = requests.RequestException(
            "API error"
        )

        # Act/Assert
        with pytest.raises(Exception, match="Failed fetching labels"):
            labels_mixin.get_page_labels("987654321")

    def test_get_page_labels_key_error(self, labels_mixin):
        """Test handling of missing keys in API response."""
        # Mock the response to be missing expected keys
        labels_mixin.confluence.get_page_labels.return_value = {"invalid": "data"}

        # Act/Assert
        with pytest.raises(Exception, match="Failed fetching labels"):
            labels_mixin.get_page_labels("987654321")

    def test_get_page_labels_value_error(self, labels_mixin):
        """Test handling of unexpected data types."""
        # Cause a value error by returning a string where a dict is expected
        labels_mixin.confluence.get_page_labels.return_value = "invalid"

        # Act/Assert
        with pytest.raises(Exception, match="Failed fetching labels"):
            labels_mixin.get_page_labels("987654321")

    def test_get_page_labels_with_empty_results(self, labels_mixin):
        """Test handling of empty results."""
        # Mock empty results
        labels_mixin.confluence.get_page_labels.return_value = {"results": []}

        # Act
        result = labels_mixin.get_page_labels("987654321")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0  # Empty list with no labels

    def test_add_page_label_success(self, labels_mixin):
        """Test adding a label"""
        # Arrange
        page_id = "987654321"
        name = "test-label"
        prefix = "global"

        # Mock add_page_label to return a list of ConfluenceLabels
        with patch.object(
            labels_mixin,
            "get_page_labels",
            return_value=ConfluenceLabel(
                id="123456789",
                name=name,
                prefix=prefix,
            ),
        ):
            # Act
            result = labels_mixin.add_page_label(page_id, name)

            # Assert
            labels_mixin.confluence.set_page_label.assert_called_once_with(
                page_id=page_id, label=name
            )

            # Verify result is a ConfluenceLabel
            assert isinstance(result, ConfluenceLabel)
            assert result.id == "123456789"
            assert result.name == name
            assert result.prefix == prefix

    def test_add_page_label_error(self, labels_mixin):
        """Test error handling when adding a label."""
        # Arrange
        labels_mixin.confluence.set_page_label.side_effect = Exception("API Error")

        # Act/Assert
        with pytest.raises(Exception, match="Failed to add label"):
            labels_mixin.add_page_label("987654321", "test")
