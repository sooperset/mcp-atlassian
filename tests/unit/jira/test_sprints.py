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
                "startDate": "2099-05-06T02:00:00.000Z",
                "endDate": "2100-05-17T10:00:00.000Z",
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
                "startDate": "2099-03-24T06:13:00.000Z",
                "endDate": "2100-04-07T06:13:00.000Z",
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

    result = sprints_mixin.get_all_sprints_from_board_model(board_id="1000", state=None)
    assert result == [
        JiraSprint.from_api_response(value) for value in mock_sprints["values"]
    ]


def test_create_sprint(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.return_value = mock_sprints["values"][1]

    result = sprints_mixin.create_sprint(
        sprint_name="Sprint 1",
        board_id="10001",
        start_date="2099-05-01T00:00:00.000Z",
        end_date="2100-05-01T00:00:00.000Z",
        goal="Your goal",
    )
    assert result == JiraSprint.from_api_response(mock_sprints["values"][1])


def test_create_sprint_http_exception(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.side_effect = requests.HTTPError(
        response=MagicMock(content="API Error content")
    )

    with pytest.raises(requests.HTTPError):
        sprints_mixin.create_sprint(
            sprint_name="Sprint 1",
            board_id="10001",
            start_date="2099-05-01T00:00:00.000Z",
            end_date="2100-05-15T00:00:00.000Z",
            goal="Your goal",
        )


def test_create_sprint_exception(sprints_mixin, mock_sprints):
    """Test create_sprint method throws general Exception."""
    sprints_mixin.jira.create_sprint.side_effect = Exception

    with pytest.raises(Exception):
        sprints_mixin.create_sprint(
            sprint_name="Sprint 1",
            board_id="10001",
            start_date="2099-05-01T00:00:00.000Z",
            end_date="2100-05-15T00:00:00.000Z",
            goal="Your goal",
        )


def test_create_sprint_test_missing_startdate(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.return_value = mock_sprints["values"][1]

    with pytest.raises(ValueError) as excinfo:
        sprints_mixin.create_sprint(
            sprint_name="Sprint 1",
            board_id="10001",
            start_date="",
            end_date="2100-05-15T00:00:00.000Z",
            goal="Your goal",
        )
    assert str(excinfo.value) == "Start date is required."


def test_create_sprint_test_invalid_startdate(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.return_value = mock_sprints["values"][1]

    with pytest.raises(ValueError):
        sprints_mixin.create_sprint(
            sprint_name="Sprint 1",
            board_id="10001",
            start_date="IAMNOTADATE!",
            end_date="2100-05-15T00:00:00.000Z",
            goal="Your goal",
        )


def test_create_sprint_test_no_enddate(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.return_value = mock_sprints["values"][1]

    result = sprints_mixin.create_sprint(
        sprint_name="Sprint 1",
        board_id="10001",
        start_date="2099-05-15T00:00:00.000Z",
        end_date=None,
        goal="Your goal",
    )
    assert result == JiraSprint.from_api_response(mock_sprints["values"][1])


def test_create_sprint_test_invalid_enddate(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.return_value = mock_sprints["values"][1]

    with pytest.raises(ValueError):
        sprints_mixin.create_sprint(
            sprint_name="Sprint 1",
            board_id="10001",
            start_date="2099-05-15T00:00:00.000Z",
            end_date="IAMNOTADATE!",
            goal="Your goal",
        )


def test_create_sprint_test_startdate_after_enddate(sprints_mixin, mock_sprints):
    """Test create_sprint method."""
    sprints_mixin.jira.create_sprint.return_value = mock_sprints["values"][1]

    with pytest.raises(ValueError, match="Start date must be before end date."):
        sprints_mixin.create_sprint(
            sprint_name="Sprint 1",
            board_id="10001",
            start_date="2100-05-15T00:00:00.000Z",
            end_date="2099-05-15T00:00:00.000Z",
            goal="Your goal",
        )


def test_update_sprint_success(sprints_mixin, mock_sprints):
    """Test update_sprint method with valid data."""
    mock_updated_sprint = mock_sprints["values"][0]
    sprints_mixin.jira.update_partially_sprint.return_value = mock_updated_sprint

    result = sprints_mixin.update_sprint(
        sprint_id="10000",
        sprint_name="Updated Sprint Name",
        state="active",
        start_date="2024-05-01T00:00:00.000Z",
        end_date="2024-05-15T00:00:00.000Z",
        goal="Updated goal",
    )

    assert result == JiraSprint.from_api_response(mock_updated_sprint)
    sprints_mixin.jira.update_partially_sprint.assert_called_once_with(
        sprint_id="10000",
        data={
            "name": "Updated Sprint Name",
            "state": "active",
            "startDate": "2024-05-01T00:00:00.000Z",
            "endDate": "2024-05-15T00:00:00.000Z",
            "goal": "Updated goal",
        },
    )


def test_update_sprint_invalid_state(sprints_mixin):
    """Test update_sprint method with invalid state."""
    result = sprints_mixin.update_sprint(
        sprint_id="10000",
        sprint_name="Updated Sprint Name",
        state="invalid_state",
        start_date=None,
        end_date=None,
        goal=None,
    )

    assert result is None
    sprints_mixin.jira.update_partially_sprint.assert_not_called()


def test_update_sprint_missing_sprint_id(sprints_mixin):
    """Test update_sprint method with missing sprint_id."""
    result = sprints_mixin.update_sprint(
        sprint_id=None,
        sprint_name="Updated Sprint Name",
        state="active",
        start_date=None,
        end_date=None,
        goal=None,
    )

    assert result is None
    sprints_mixin.jira.update_partially_sprint.assert_not_called()


def test_update_sprint_http_error(sprints_mixin):
    """Test update_sprint method with HTTPError."""
    sprints_mixin.jira.update_partially_sprint.side_effect = requests.HTTPError(
        response=MagicMock(content="API Error content")
    )

    result = sprints_mixin.update_sprint(
        sprint_id="10000",
        sprint_name="Updated Sprint Name",
        state="active",
        start_date=None,
        end_date=None,
        goal=None,
    )

    assert result is None
    sprints_mixin.jira.update_partially_sprint.assert_called_once()


def test_update_sprint_exception(sprints_mixin):
    """Test update_sprint method with a generic exception."""
    sprints_mixin.jira.update_partially_sprint.side_effect = Exception(
        "Unexpected Error"
    )

    result = sprints_mixin.update_sprint(
        sprint_id="10000",
        sprint_name="Updated Sprint Name",
        state="active",
        start_date=None,
        end_date=None,
        goal=None,
    )

    assert result is None
    sprints_mixin.jira.update_partially_sprint.assert_called_once()
