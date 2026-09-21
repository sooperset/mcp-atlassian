"""Tests for the Jira Worklog mixin."""

from unittest.mock import MagicMock, Mock

import pytest

from mcp_atlassian.jira.worklog import WorklogMixin


class TestWorklogMixin:
    """Tests for the WorklogMixin class."""

    @pytest.fixture
    def worklog_mixin(self, jira_client):
        """Create a WorklogMixin instance with mocked dependencies."""
        mixin = WorklogMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Mock methods that are typically provided by other mixins
        mixin._clean_text = MagicMock(side_effect=lambda text: text if text else "")

        return mixin

    def test_parse_time_spent_with_seconds(self, worklog_mixin):
        """Test parsing time spent with seconds specification."""
        assert worklog_mixin._parse_time_spent("60s") == 60
        assert worklog_mixin._parse_time_spent("3600s") == 3600

    def test_parse_time_spent_with_minutes(self, worklog_mixin):
        """Test parsing time spent with minutes."""
        assert worklog_mixin._parse_time_spent("1m") == 60
        assert worklog_mixin._parse_time_spent("30m") == 1800

    def test_parse_time_spent_with_hours(self, worklog_mixin):
        """Test parsing time spent with hours."""
        assert worklog_mixin._parse_time_spent("1h") == 3600
        assert worklog_mixin._parse_time_spent("2h") == 7200

    def test_parse_time_spent_with_days(self, worklog_mixin):
        """Test parsing time spent with days."""
        assert worklog_mixin._parse_time_spent("1d") == 86400
        assert worklog_mixin._parse_time_spent("2d") == 172800

    def test_parse_time_spent_with_weeks(self, worklog_mixin):
        """Test parsing time spent with weeks."""
        assert worklog_mixin._parse_time_spent("1w") == 604800
        assert worklog_mixin._parse_time_spent("2w") == 1209600

    def test_parse_time_spent_with_mixed_units(self, worklog_mixin):
        """Test parsing time spent with mixed units."""
        assert worklog_mixin._parse_time_spent("1h 30m") == 5400
        assert worklog_mixin._parse_time_spent("1d 6h") == 108000
        assert worklog_mixin._parse_time_spent("1w 2d 3h 4m") == 788640

    def test_parse_time_spent_with_invalid_input(self, worklog_mixin):
        """Test parsing time spent with invalid input."""
        # Should default to 60 seconds
        assert worklog_mixin._parse_time_spent("invalid") == 60

    def test_parse_time_spent_with_numeric_input(self, worklog_mixin):
        """Test parsing time spent with numeric input."""
        assert worklog_mixin._parse_time_spent("60") == 60
        assert worklog_mixin._parse_time_spent("3600") == 3600

    def test_get_worklogs_basic(self, worklog_mixin):
        """Test basic functionality of get_worklogs."""
        mock_result = {
            "total": 1,
            "worklogs": [
                {
                    "id": "10001",
                    "comment": "Work item 1",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T10:30:00.000+0000",
                    "started": "2024-01-01T09:00:00.000+0000",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "Test User"},
                }
            ],
        }
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        worklog_mixin.jira.get.return_value = mock_result

        result = worklog_mixin.get_worklogs("TEST-123")

        worklog_mixin.jira.get.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/worklog",
            params={"maxResults": 100, "startAt": 0},
        )
        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["comment"] == "Work item 1"
        assert result[0]["time_spent"] == "1h"
        assert result[0]["time_spent_seconds"] == 3600
        assert result[0]["author"] == "Test User"

    def test_get_worklogs_with_multiple_entries(self, worklog_mixin):
        """Test get_worklogs with multiple worklog entries."""
        mock_result = {
            "total": 2,
            "worklogs": [
                {
                    "id": "10001",
                    "comment": "Work item 1",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "User 1"},
                },
                {
                    "id": "10002",
                    "comment": "Work item 2",
                    "created": "2024-01-02T10:00:00.000+0000",
                    "timeSpent": "2h",
                    "timeSpentSeconds": 7200,
                    "author": {"displayName": "User 2"},
                },
            ],
        }
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        worklog_mixin.jira.get.return_value = mock_result

        result = worklog_mixin.get_worklogs("TEST-123")

        assert len(result) == 2
        assert result[0]["id"] == "10001"
        assert result[1]["id"] == "10002"
        assert result[0]["time_spent_seconds"] == 3600
        assert result[1]["time_spent_seconds"] == 7200

    def test_get_worklogs_with_missing_fields(self, worklog_mixin):
        """Test get_worklogs with missing fields."""
        mock_result = {
            "total": 1,
            "worklogs": [
                {
                    "id": "10001",
                    # Missing comment
                    "created": "2024-01-01T10:00:00.000+0000",
                    # Missing other fields
                }
            ],
        }
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        worklog_mixin.jira.get.return_value = mock_result

        result = worklog_mixin.get_worklogs("TEST-123")

        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["comment"] == ""
        assert result[0]["time_spent"] == ""
        assert result[0]["time_spent_seconds"] == 0
        assert result[0]["author"] == "Unknown"

    def test_get_worklogs_with_empty_response(self, worklog_mixin):
        """Test get_worklogs with empty response."""
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        worklog_mixin.jira.get.return_value = {"total": 0, "worklogs": []}

        result = worklog_mixin.get_worklogs("TEST-123")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_worklogs_paginates_multiple_pages(self, worklog_mixin):
        """Test that get_worklogs fetches all pages when total exceeds page size."""
        page1 = {
            "total": 3,
            "worklogs": [
                {
                    "id": "1",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "U"},
                },
                {
                    "id": "2",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "U"},
                },
            ],
        }
        page2 = {
            "total": 3,
            "worklogs": [
                {
                    "id": "3",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "U"},
                },
            ],
        }
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        worklog_mixin.jira.get.side_effect = [page1, page2]

        result = worklog_mixin.get_worklogs("TEST-123")

        assert len(result) == 3
        assert worklog_mixin.jira.get.call_count == 2

    def test_get_worklogs_with_error(self, worklog_mixin):
        """Test get_worklogs error handling."""
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        worklog_mixin.jira.get.side_effect = Exception("Worklog fetch error")

        with pytest.raises(
            Exception, match="Error getting worklogs: Worklog fetch error"
        ):
            worklog_mixin.get_worklogs("TEST-123")

    def test_add_worklog_basic(self, worklog_mixin):
        """Test basic functionality of add_worklog."""
        # Setup mock response
        mock_result = {
            "id": "10001",
            "comment": "Added work",
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-01T10:00:00.000+0000",
            "started": "2024-01-01T09:00:00.000+0000",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
            "author": {"displayName": "Test User"},
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        # Mock _markdown_to_jira to return plain string (v2 path)
        worklog_mixin._markdown_to_jira = MagicMock(return_value="Added work")

        # Call the method
        result = worklog_mixin.add_worklog("TEST-123", "1h", comment="Added work")

        # Verify
        worklog_mixin.jira.resource_url.assert_called_once_with("issue")
        worklog_mixin.jira.post.assert_called_once()
        assert result["id"] == "10001"
        assert result["comment"] == "Added work"
        assert result["time_spent"] == "1h"
        assert result["time_spent_seconds"] == 3600
        assert result["author"] == "Test User"
        assert result["original_estimate_updated"] is False
        assert result["remaining_estimate_updated"] is False

    def test_add_worklog_with_original_estimate(self, worklog_mixin):
        """Test add_worklog with original estimate update."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method
        result = worklog_mixin.add_worklog("TEST-123", "1h", original_estimate="4h")

        # Verify
        worklog_mixin.jira.edit_issue.assert_called_once_with(
            issue_id_or_key="TEST-123",
            fields={"timetracking": {"originalEstimate": "4h"}},
        )
        assert result["original_estimate_updated"] is True

    def test_add_worklog_with_remaining_estimate(self, worklog_mixin):
        """Test add_worklog with remaining estimate update."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method
        result = worklog_mixin.add_worklog("TEST-123", "1h", remaining_estimate="3h")

        # Verify post call has correct parameters
        call_args = worklog_mixin.jira.post.call_args
        assert call_args is not None
        args, kwargs = call_args

        # Check that adjustEstimate=new and newEstimate=3h are in params
        assert "params" in kwargs
        assert kwargs["params"]["adjustEstimate"] == "new"
        assert kwargs["params"]["newEstimate"] == "3h"

        assert result["remaining_estimate_updated"] is True

    def test_add_worklog_with_started_time(self, worklog_mixin):
        """Test add_worklog with started time."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Setup started time
        started_time = "2024-01-01T09:00:00.000+0000"

        # Call the method
        worklog_mixin.add_worklog("TEST-123", "1h", started=started_time)

        # Verify worklog data contains started time
        call_args = worklog_mixin.jira.post.call_args
        assert call_args is not None
        args, kwargs = call_args

        assert "data" in kwargs
        assert kwargs["data"]["started"] == started_time

    def test_add_worklog_with_markdown_to_jira_available(self, worklog_mixin):
        """Test add_worklog with _markdown_to_jira conversion."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Add _markdown_to_jira method
        worklog_mixin._markdown_to_jira = MagicMock(return_value="Converted comment")

        # Call the method
        worklog_mixin.add_worklog("TEST-123", "1h", comment="**Markdown** comment")

        # Verify _markdown_to_jira was called
        worklog_mixin._markdown_to_jira.assert_called_once_with("**Markdown** comment")

        # Verify converted comment was used
        call_args = worklog_mixin.jira.post.call_args
        assert call_args is not None
        args, kwargs = call_args

        assert "data" in kwargs
        assert kwargs["data"]["comment"] == "Converted comment"

    def test_add_worklog_with_error(self, worklog_mixin):
        """Test add_worklog error handling."""
        # Setup mock to raise exception
        worklog_mixin.jira.post.side_effect = Exception("Worklog add error")
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method and verify exception
        with pytest.raises(Exception, match="Error adding worklog: Worklog add error"):
            worklog_mixin.add_worklog("TEST-123", "1h")

    def test_add_worklog_with_original_estimate_error(self, worklog_mixin):
        """Test add_worklog with original estimate update error."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Make edit_issue raise an exception
        worklog_mixin.jira.edit_issue.side_effect = Exception("Estimate update error")

        # Call the method - should continue despite estimate update error
        result = worklog_mixin.add_worklog("TEST-123", "1h", original_estimate="4h")

        # Verify post was still called (worklog added despite estimate error)
        worklog_mixin.jira.post.assert_called_once()
        assert result["original_estimate_updated"] is False

    # --- ADF routing tests (Cloud v3 vs Server/DC v2) ---

    @pytest.fixture
    def server_worklog_mixin(self, jira_config_factory):
        """Create a WorklogMixin configured for Server/DC."""
        config = jira_config_factory(url="https://jira.example.com")
        mixin = WorklogMixin(config=config)
        mixin.jira = MagicMock()
        mixin._clean_text = MagicMock(side_effect=lambda text: text if text else "")
        mixin._markdown_to_jira = MagicMock(return_value="wiki markup comment")
        return mixin

    def test_add_worklog_cloud_adf_uses_v3_api(self, worklog_mixin):
        """Cloud + ADF dict comment routes through _post_api3."""
        adf_comment = {
            "type": "doc",
            "version": 1,
            "content": [],
        }
        mock_result = {
            "id": "10001",
            "comment": adf_comment,
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-01T10:00:00.000+0000",
            "started": "2024-01-01T09:00:00.000+0000",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
            "author": {"displayName": "Test User"},
        }
        worklog_mixin._markdown_to_jira = Mock(return_value=adf_comment)
        worklog_mixin._post_api3 = Mock(return_value=mock_result)

        result = worklog_mixin.add_worklog("TEST-123", "1h", comment="test")

        worklog_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/worklog",
            data={
                "timeSpentSeconds": 3600,
                "comment": adf_comment,
            },
            params=None,
        )
        worklog_mixin.jira.post.assert_not_called()
        assert result["id"] == "10001"

    def test_add_worklog_cloud_adf_with_remaining_estimate(self, worklog_mixin):
        """Cloud + ADF + remaining_estimate passes params to v3."""
        adf_comment = {
            "type": "doc",
            "version": 1,
            "content": [],
        }
        mock_result = {
            "id": "10002",
            "comment": adf_comment,
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-01T10:00:00.000+0000",
            "started": "2024-01-01T09:00:00.000+0000",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
            "author": {"displayName": "Test User"},
        }
        worklog_mixin._markdown_to_jira = Mock(return_value=adf_comment)
        worklog_mixin._post_api3 = Mock(return_value=mock_result)

        result = worklog_mixin.add_worklog(
            "TEST-123",
            "1h",
            comment="test",
            remaining_estimate="3h",
        )

        worklog_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/worklog",
            data={
                "timeSpentSeconds": 3600,
                "comment": adf_comment,
            },
            params={
                "adjustEstimate": "new",
                "newEstimate": "3h",
            },
        )
        assert result["remaining_estimate_updated"] is True

    def test_add_worklog_server_uses_v2_api(self, server_worklog_mixin):
        """Server/DC + wiki string routes through jira.post (v2)."""
        mock_result = {
            "id": "10003",
            "comment": "wiki markup comment",
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-01T10:00:00.000+0000",
            "started": "2024-01-01T09:00:00.000+0000",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
            "author": {"displayName": "Test User"},
        }
        server_worklog_mixin.jira.post.return_value = mock_result
        server_worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        server_worklog_mixin._post_api3 = Mock()

        result = server_worklog_mixin.add_worklog("TEST-123", "1h", comment="test")

        server_worklog_mixin.jira.post.assert_called_once()
        server_worklog_mixin.jira.resource_url.assert_called_with("issue")
        server_worklog_mixin._post_api3.assert_not_called()
        assert result["id"] == "10003"


class TestSearchWorklogs:
    """Tests for `WorklogMixin.search_worklogs` (Tempo Timesheets v4)."""

    @staticmethod
    def _row(
        issue_key: str = "SOA-11080",
        tempo_id: int = 5961726,
        started: str = "2026-09-10 10:00:00.000",
        value: str = "Разработка",
    ) -> dict:
        """Build an entry shaped like a live Data Center response.

        The live payload uses `started` and `worker` where Tempo's own OpenAPI
        spec promises `startDate` and `workerKey`, and omits `jiraWorklogId`.
        """
        return {
            "tempoWorklogId": tempo_id,
            "started": started,
            "dateCreated": "2026-09-10 16:02:42.000",
            "dateUpdated": "2026-09-10 16:02:42.000",
            "timeSpent": "6h",
            "timeSpentSeconds": 21600,
            "billableSeconds": 21600,
            "worker": "JIRAUSER389717",
            "updater": "JIRAUSER389717",
            "comment": "анализ проблем кластера",
            "originTaskId": 1721061,
            "issue": {
                "key": issue_key,
                "summary": "Запросы падают по таймауту",
                "projectKey": "SOA",
                "epicKey": "SOA-10915",
            },
            "attributes": {
                "_Видработ_": {
                    "workAttributeId": 1,
                    "value": value,
                    "type": "STATIC_LIST",
                    "key": "_Видработ_",
                    "name": "Вид работ",
                }
            },
        }

    @classmethod
    def _mixin(cls, *, is_cloud: bool = False, rows: object = None):
        """Build the worklog mixin with only the Jira client mocked.

        `__new__` is used because `JiraClient.__init__` builds a real session
        from `config.url`, which a bare MagicMock cannot satisfy.
        """
        mixin = WorklogMixin.__new__(WorklogMixin)
        mixin.config = MagicMock(is_cloud=is_cloud)
        mixin.jira = MagicMock()
        mixin.jira.myself.return_value = {"key": "JIRAUSER389717"}
        mixin.jira.post.return_value = [cls._row()] if rows is None else rows
        mixin._clean_text = MagicMock(side_effect=lambda text: text or "")
        return mixin

    def test_defaults_to_authenticated_worker(self):
        """An unspecified worker narrows the search to the caller."""
        mixin = self._mixin()

        result = mixin.search_worklogs("2026-09-10", "2026-09-10")

        mixin.jira.post.assert_called_once_with(
            "rest/tempo-timesheets/4/worklogs/search",
            data={
                "from": "2026-09-10",
                "to": "2026-09-10",
                "worker": ["JIRAUSER389717"],
            },
        )
        assert result["workers"] == ["JIRAUSER389717"]
        assert result["count"] == 1
        assert result["total_matched"] == 1
        assert result["truncated"] is False

    def test_maps_live_field_names_and_attributes(self):
        """Live response keys map, and Tempo attributes survive the mapping."""
        worklog = self._mixin().search_worklogs("2026-09-10", "2026-09-10")["worklogs"][
            0
        ]

        assert worklog["id"] == "5961726"
        assert worklog["issue_key"] == "SOA-11080"
        assert worklog["project_key"] == "SOA"
        assert worklog["epic_key"] == "SOA-10915"
        assert worklog["author"] == "JIRAUSER389717"
        assert worklog["time_spent"] == "6h"
        assert worklog["time_spent_seconds"] == 21600
        assert worklog["started"].startswith("2026-09-10 10:00:00")
        assert worklog["comment"] == "анализ проблем кластера"
        assert worklog["attributes"]["_Видработ_"]["value"] == "Разработка"

    def test_maps_spec_field_names_as_fallback(self):
        """The spec-documented names map too, so either shape works."""
        row = {
            "jiraWorklogId": 42,
            "startDate": "2026-09-01 09:00:00.000",
            "workerKey": "JIRAUSER1",
            "timeSpent": "1h",
            "timeSpentSeconds": "3600",
        }

        result = self._mixin(rows=[row]).search_worklogs("2026-09-01", "2026-09-01")
        worklog = result["worklogs"][0]

        assert worklog["id"] == "42"
        assert worklog["author"] == "JIRAUSER1"
        assert worklog["time_spent_seconds"] == 3600
        assert worklog["issue_key"] == ""
        assert "attributes" not in worklog

    def test_all_worker_search_requires_narrowing_filter(self):
        """Without a worker, a task or project filter is mandatory."""
        with pytest.raises(ValueError, match="task_keys"):
            self._mixin().search_worklogs("2026-09-10", "2026-09-10", worker_keys=[])

    def test_all_worker_search_with_task_keys_omits_worker(self):
        """Task keys narrow the search instead of the worker list."""
        mixin = self._mixin()

        result = mixin.search_worklogs(
            "2026-09-08",
            "2026-09-11",
            worker_keys=[],
            task_keys=["SOA-11069", " SOA-11080 ", ""],
            project_keys=["SOA"],
        )

        data = mixin.jira.post.call_args.kwargs["data"]
        assert "worker" not in data
        assert data["taskKey"] == ["SOA-11069", "SOA-11080"]
        assert data["projectKey"] == ["SOA"]
        assert result["workers"] == ["*"]

    @pytest.mark.parametrize("bad_date", ["2026/09/10", "20260910", "10-09-2026", ""])
    def test_rejects_malformed_dates(self, bad_date):
        """Tempo's opaque date errors are caught before the request."""
        with pytest.raises(ValueError, match="yyyy-MM-dd"):
            self._mixin().search_worklogs(bad_date, "2026-09-10")

    def test_rejects_reversed_range(self):
        """A descending range fails locally instead of returning nothing."""
        with pytest.raises(ValueError, match="ascending"):
            self._mixin().search_worklogs("2026-09-11", "2026-09-10")

    def test_rejects_non_positive_limit(self):
        """A zero limit would silently discard every result."""
        with pytest.raises(ValueError, match="limit"):
            self._mixin().search_worklogs("2026-09-10", "2026-09-10", limit=0)

    def test_rejects_cloud(self):
        """Tempo Timesheets v4 does not exist on Jira Cloud."""
        with pytest.raises(NotImplementedError, match="Server/Data Center"):
            self._mixin(is_cloud=True).search_worklogs("2026-09-10", "2026-09-10")

    @pytest.mark.parametrize("payload", [{"worklogs": []}, ["not-a-worklog"]])
    def test_rejects_unexpected_response_shape(self, payload):
        """A response Tempo does not document surfaces as a TypeError."""
        mixin = self._mixin(rows=payload)

        with pytest.raises(TypeError, match="worklog search"):
            mixin.search_worklogs("2026-09-10", "2026-09-10")

    def test_results_are_sorted_and_truncated(self):
        """Results are ordered and capped, since Tempo does not paginate."""
        rows = [
            self._row(tempo_id=3, started="2026-09-11 10:00:00.000"),
            self._row(tempo_id=1, started="2026-09-09 10:00:00.000"),
            self._row(tempo_id=2, started="2026-09-10 10:00:00.000"),
        ]

        result = self._mixin(rows=rows).search_worklogs(
            "2026-09-09", "2026-09-11", limit=2
        )

        assert [worklog["id"] for worklog in result["worklogs"]] == ["1", "2"]
        assert result["count"] == 2
        assert result["total_matched"] == 3
        assert result["truncated"] is True

    def test_wraps_transport_failures(self):
        """A failing request keeps the worklog-specific error context."""
        mixin = self._mixin()
        mixin.jira.post.side_effect = RuntimeError("503 Service Unavailable")

        with pytest.raises(Exception, match="Error searching worklogs"):
            mixin.search_worklogs("2026-09-10", "2026-09-10")
