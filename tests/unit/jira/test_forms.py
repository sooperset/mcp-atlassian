"""Tests for Jira ProForma form operations."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.forms import FormsMixin
from mcp_atlassian.jira.forms_common import handle_forms_http_error


@pytest.fixture
def mock_config():
    """Fixture to create a mock JiraConfig instance."""
    config = MagicMock(spec=JiraConfig)
    config.url = "https://test.atlassian.net"
    config.auth_type = "pat"
    return config


@pytest.fixture
def forms_mixin(mock_config):
    """Fixture to create a FormsMixin instance for testing."""
    mixin = FormsMixin(config=mock_config)
    mixin.jira = MagicMock()
    return mixin


def test_get_issue_forms_404_empty_list(forms_mixin):
    """Test get_issue_forms returns empty list on 404 HTTPError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    error = HTTPError(response=mock_response)
    forms_mixin.jira.get.side_effect = error

    assert forms_mixin.get_issue_forms("TEST-123") == []


def test_get_issue_forms_http_error_no_response(forms_mixin):
    """Test get_issue_forms handles HTTPError when response is None."""
    error = HTTPError()
    error.response = None
    forms_mixin.jira.get.side_effect = error

    with pytest.raises(Exception):
        forms_mixin.get_issue_forms("TEST-123")


def test_get_form_details_404_returns_none(forms_mixin):
    """Test get_form_details returns None on 404 HTTPError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    error = HTTPError(response=mock_response)
    forms_mixin.jira.get.side_effect = error

    assert forms_mixin.get_form_details("TEST-123", "i1") is None


def test_get_form_details_http_error_no_response(forms_mixin):
    """Test get_form_details handles HTTPError when response is None."""
    error = HTTPError()
    error.response = None
    forms_mixin.jira.get.side_effect = error

    with pytest.raises(Exception):
        forms_mixin.get_form_details("TEST-123", "i1")


def test_handle_forms_http_error_without_response():
    """Test handle_forms_http_error does not crash when error.response is None."""
    error = HTTPError()
    error.response = None

    exc = handle_forms_http_error(error, "testing", "TEST-123")
    assert isinstance(exc, Exception)
    assert not isinstance(exc, MCPAtlassianAuthenticationError)
    assert not isinstance(exc, ValueError)
