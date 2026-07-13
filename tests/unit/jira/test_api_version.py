"""Regression tests for Jira REST API v3 support.

The v3 helpers are required for Jira Cloud payloads that contain Atlassian
Document Format (ADF) objects. Regression coverage for issue #338.
"""

from typing import Any

from mcp_atlassian.jira import JiraFetcher


class TestJiraRestApiV3:
    """Jira Cloud ADF writes use the REST API v3 endpoint."""

    def test_post_api3_uses_v3_endpoint_and_forwards_params(
        self, jira_fetcher: JiraFetcher
    ) -> None:
        """The v3 POST helper builds a v3 URL and forwards its request."""
        payload: dict[str, Any] = {
            "fields": {
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": [],
                }
            }
        }
        params = {"notifyUsers": "false"}
        expected_response = {"id": "10000"}
        expected_url = "https://jira.example.com/rest/api/3/issue"
        jira_fetcher.jira.resource_url.return_value = expected_url
        jira_fetcher.jira.post.return_value = expected_response

        result = jira_fetcher._post_api3("issue", data=payload, params=params)

        assert result == expected_response
        jira_fetcher.jira.resource_url.assert_called_once_with("issue", api_version="3")
        jira_fetcher.jira.post.assert_called_once_with(
            expected_url, data=payload, params=params
        )

    def test_put_api3_uses_v3_endpoint_and_forwards_payload(
        self, jira_fetcher: JiraFetcher
    ) -> None:
        """The v3 PUT helper builds a v3 URL and forwards the payload."""
        payload: dict[str, Any] = {
            "fields": {
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": [],
                }
            }
        }
        expected_response = {"key": "TEST-123"}
        expected_url = "https://jira.example.com/rest/api/3/issue/TEST-123"
        jira_fetcher.jira.resource_url.return_value = expected_url
        jira_fetcher.jira.put.return_value = expected_response

        result = jira_fetcher._put_api3("issue/TEST-123", data=payload)

        assert result == expected_response
        jira_fetcher.jira.resource_url.assert_called_once_with(
            "issue/TEST-123", api_version="3"
        )
        jira_fetcher.jira.put.assert_called_once_with(expected_url, data=payload)
