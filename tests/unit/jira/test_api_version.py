"""Tests confirming Jira REST API v3 support is implemented.

Regression tests for https://github.com/sooperset/mcp-atlassian/issues/338
Feature was requested: support Jira REST API v3 for Cloud.
Already implemented — _post_api3 and _put_api3 helpers in client.py,
and Cloud search uses rest/api/3/search/jql endpoint.
"""

import inspect

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.search import SearchMixin


class TestJiraRestApiV3:
    """Jira REST API v3 is used on Cloud for ADF payloads.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/338
    Feature was requested: support Jira REST API v3.
    Already implemented — _post_api3 and _put_api3 helpers in client.py,
    and Cloud search uses rest/api/3/search/jql endpoint.
    """

    def test_client_has_v3_post_method(self, jira_fetcher: JiraFetcher) -> None:
        """JiraClient exposes a v3 POST helper for ADF payloads."""
        assert hasattr(jira_fetcher, "_post_api3"), (
            "_post_api3 method missing from JiraClient"
        )

    def test_client_has_v3_put_method(self, jira_fetcher: JiraFetcher) -> None:
        """JiraClient exposes a v3 PUT helper for ADF payloads."""
        assert hasattr(jira_fetcher, "_put_api3"), (
            "_put_api3 method missing from JiraClient"
        )

    def test_v3_post_method_is_callable(self, jira_fetcher: JiraFetcher) -> None:
        """_post_api3 is a callable method, not a plain attribute."""
        assert callable(jira_fetcher._post_api3), "_post_api3 is not callable"

    def test_v3_put_method_is_callable(self, jira_fetcher: JiraFetcher) -> None:
        """_put_api3 is a callable method, not a plain attribute."""
        assert callable(jira_fetcher._put_api3), "_put_api3 is not callable"

    def test_cloud_uses_v3_search_endpoint(self) -> None:
        """Cloud JQL search is routed through the v3 API endpoint."""
        source = inspect.getsource(SearchMixin.search_issues)
        assert "rest/api/3/search" in source, (
            "Cloud v3 search endpoint not found in search_issues source"
        )

    def test_v3_post_uses_api_version_3(self, jira_fetcher: JiraFetcher) -> None:
        """_post_api3 implementation explicitly requests api_version='3'."""
        source = inspect.getsource(jira_fetcher._post_api3)
        assert 'api_version="3"' in source or "api_version='3'" in source, (
            "_post_api3 does not request API version 3 from resource_url"
        )

    def test_v3_put_uses_api_version_3(self, jira_fetcher: JiraFetcher) -> None:
        """_put_api3 implementation explicitly requests api_version='3'."""
        source = inspect.getsource(jira_fetcher._put_api3)
        assert 'api_version="3"' in source or "api_version='3'" in source, (
            "_put_api3 does not request API version 3 from resource_url"
        )
