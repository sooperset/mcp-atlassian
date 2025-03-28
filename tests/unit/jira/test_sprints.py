"""Tests for the Jira SprintMixin"""

from unittest.mock import MagicMock

import pytest
import requests

from mcp_atlassian.jira import JiraConfig
from mcp_atlassian.jira.sprints import SprintsMixin
from mcp_atlassian.models.jira import JiraSprint


@pytest.fixture
def mock_config():
    """Fixture to create a mock JiraConfig instance."""
    config = MagicMock(spec=JiraConfig)
    config.url = "https://test.atlassian.net"
    config.username = "test@example.com"
    config.api_token = "test-token"
    config.auth_type = "token"
    return config


@pytest.fixture
def sprints_mixin(mock_config):
    """Fixture to create a SprintsMixin instance for testing."""
    mixin = SprintsMixin(config=mock_config)
    mixin.jira = MagicMock()

    return mixin


@pytest.fixture
def mock_sprints():
    """Fixture to return mock boards data."""
    return {
        "maxResults": 50,
        "startAt": 0,
        "isLast": True,
        "values": [
            {
                "id": 10000,
                "self": "https://test.atlassian.net/rest/agile/1.0/sprint/10000",
                "state": "closed",
                "name": "Sprint 0",
                "startDate": "2024-05-06T02:00:00.000Z",
                "endDate": "2024-05-17T10:00:00.000Z",
                "completeDate": "2024-05-20T05:17:24.302Z",
                "activatedDate": "2024-05-07T01:22:45.128Z",
                "originBoardId": 1000,
                "goal": "",
                "synced": False,
                "autoStartStop": False,
            },
            {
                "id": 10001,
                "self": "https://test.atlassian.net/rest/agile/1.0/sprint/10001",
                "state": "active",
                "name": "Sprint 1",
                "startDate": "2025-03-24T06:13:00.000Z",
                "endDate": "2025-04-07T06:13:00.000Z",
                "activatedDate": "2025-03-24T06:13:20.729Z",
                "originBoardId": 1000,
                "goal": "",
                "synced": False,
                "autoStartStop": False,
            },
            {
                "id": 10002,
                "self": "https://test.atlassian.net/rest/agile/1.0/sprint/10002",
                "state": "future",
                "name": "Sprint 2",
                "originBoardId": 1000,
                "synced": False,
                "autoStartStop": False,
            },
        ],
    }


def test_get_all_sprints_from_board(sprints_mixin, mock_sprints):
    """Test get_all_sprints_from_board method."""
    sprints_mixin.jira.get_all_sprints_from_board.return_value = mock_sprints

    result = sprints_mixin.get_all_sprints_from_board("1000")
    assert result == mock_sprints["values"]


def test_get_all_sprints_from_board_exception(sprints_mixin):
    """Test get_all_sprints_from_board method with exception."""
    sprints_mixin.jira.get_all_sprints_from_board.side_effect = Exception("API Error")

    result = sprints_mixin.get_all_sprints_from_board("1000")
    assert result == []
    sprints_mixin.jira.get_all_sprints_from_board.assert_called_once()


def test_get_all_sprints_from_board_http_error(sprints_mixin):
    """Test get_all_sprints_from_board method with HTTPError."""
    sprints_mixin.jira.get_all_sprints_from_board.side_effect = requests.HTTPError(
        response=MagicMock(content="API Error content")
    )

    result = sprints_mixin.get_all_sprints_from_board("1000")
    assert result == []
    sprints_mixin.jira.get_all_sprints_from_board.assert_called_once()


def test_get_all_sprints_from_board_non_dict_response(sprints_mixin):
    """Test get_all_sprints_from_board method with non-list response."""
    sprints_mixin.jira.get_all_sprints_from_board.return_value = "not a dict"

    result = sprints_mixin.get_all_sprints_from_board("1000")
    assert result == []
    sprints_mixin.jira.get_all_sprints_from_board.assert_called_once()


def test_get_all_sprints_from_board_model(sprints_mixin, mock_sprints):
    sprints_mixin.jira.get_all_sprints_from_board.return_value = mock_sprints

    result = sprints_mixin.get_all_sprints_from_board_model("1000")
    assert result == [
        JiraSprint.from_api_response(value) for value in mock_sprints["values"]
    ]
