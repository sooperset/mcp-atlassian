"""Tests for the AIO Tests HTTP client."""

from unittest.mock import MagicMock

import pytest
import requests

from mcp_atlassian.aio.client import AIOApiError, AIOClient
from mcp_atlassian.aio.config import AIOConfig
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError


def make_response(
    status_code: int = 200, json_body=None, text: str = "", content: bytes = b"{}"
) -> MagicMock:
    """Build a mock requests.Response.

    Args:
        status_code: HTTP status code.
        json_body: Body returned by ``.json()``; a ValueError is raised if unset.
        text: Raw response text.
        content: Raw response bytes.

    Returns:
        The mock response.
    """
    response = MagicMock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.text = text
    response.content = content
    if json_body is None:
        response.json.side_effect = ValueError("no json")
    else:
        response.json.return_value = json_body
    return response


class TestAIOClientAuth:
    """Tests for authentication header setup."""

    def test_cloud_token_uses_aioauth_scheme(self):
        """Cloud tokens are sent with the AioAuth scheme."""
        client = AIOClient(
            config=AIOConfig(url="https://x/api/v1", auth_type="token", api_token="tok")
        )
        assert client.session.headers["Authorization"] == "AioAuth tok"

    def test_pat_uses_bearer_scheme(self):
        """Server/DC PATs are sent as bearer tokens."""
        client = AIOClient(
            config=AIOConfig(
                url="https://x/api/v1", auth_type="pat", personal_token="pat"
            )
        )
        assert client.session.headers["Authorization"] == "Bearer pat"

    def test_basic_auth_sets_session_auth(self):
        """Basic auth is applied to the session."""
        client = AIOClient(
            config=AIOConfig(
                url="https://x/api/v1",
                auth_type="basic",
                username="user",
                password="pass",
            )
        )
        assert client.session.auth == ("user", "pass")

    def test_custom_headers_applied(self):
        """Custom headers reach the session."""
        client = AIOClient(
            config=AIOConfig(
                url="https://x/api/v1",
                auth_type="token",
                api_token="tok",
                custom_headers={"X-Trace": "1"},
            )
        )
        assert client.session.headers["X-Trace"] == "1"


class TestProjectPath:
    """Tests for project path building."""

    def test_builds_escaped_path(self):
        """Segments are joined and URL-escaped."""
        assert (
            AIOClient.project_path("PROJ", "testcase", "AT-TC-1", "detail")
            == "/project/PROJ/testcase/AT-TC-1/detail"
        )

    def test_escapes_special_characters(self):
        """Slashes inside a segment cannot break out of the path."""
        assert AIOClient.project_path("A/B", "tag") == "/project/A%2FB/tag"

    def test_numeric_segments(self):
        """Numeric segments are stringified."""
        assert (
            AIOClient.project_path(10010, "testcase", 5) == "/project/10010/testcase/5"
        )

    @pytest.mark.parametrize("project_key", ["", "   "])
    def test_empty_project_key_raises(self, project_key):
        """An empty project key is rejected."""
        with pytest.raises(ValueError, match="Project key or ID is required"):
            AIOClient.project_path(project_key)


class TestAIOClientRequest:
    """Tests for request execution and error handling."""

    @pytest.fixture
    def client(self) -> AIOClient:
        """Provide a client with a mocked session."""
        client = AIOClient(
            config=AIOConfig(
                url="https://tcms.example.com/api/v1",
                auth_type="token",
                api_token="tok",
            )
        )
        client.session = MagicMock()
        return client

    def test_get_returns_json(self, client):
        """A successful GET returns the decoded body."""
        client.session.request.return_value = make_response(json_body={"ID": 1})

        assert client.get("/project/PROJ/tag") == {"ID": 1}
        _, kwargs = client.session.request.call_args
        args, _ = client.session.request.call_args
        assert args[0] == "GET"
        assert args[1] == "https://tcms.example.com/api/v1/project/PROJ/tag"

    def test_none_params_are_dropped(self, client):
        """Unset query parameters are not sent."""
        client.session.request.return_value = make_response(json_body={})

        client.get("/path", params={"a": 1, "b": None, "c": False})

        _, kwargs = client.session.request.call_args
        assert kwargs["params"] == {"a": 1, "c": False}

    def test_empty_params_send_none(self, client):
        """An empty parameter dict is sent as no parameters."""
        client.session.request.return_value = make_response(json_body={})

        client.get("/path")

        _, kwargs = client.session.request.call_args
        assert kwargs["params"] is None

    def test_empty_body_returns_none(self, client):
        """A 204-style empty body decodes to None."""
        client.session.request.return_value = make_response(content=b"")

        assert client.put("/path") is None

    def test_non_json_body_returns_text(self, client):
        """A non-JSON body is returned as text."""
        client.session.request.return_value = make_response(
            text="plain", content=b"plain"
        )

        assert client.post("/path") == "plain"

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_errors_raise_authentication_error(self, client, status_code):
        """401 and 403 map to the shared authentication error."""
        client.session.request.return_value = make_response(
            status_code=status_code, text="denied", content=b"denied"
        )

        with pytest.raises(MCPAtlassianAuthenticationError, match="Authentication"):
            client.get("/path")

    def test_other_errors_raise_api_error_with_status(self, client):
        """Other error statuses surface as AIOApiError."""
        client.session.request.return_value = make_response(
            status_code=404, text="Resource Not Found", content=b"Resource Not Found"
        )

        with pytest.raises(AIOApiError, match="404") as exc_info:
            client.get("/path")
        assert exc_info.value.status_code == 404
        assert "Resource Not Found" in str(exc_info.value)

    def test_long_error_body_is_truncated(self, client):
        """Very long error bodies are truncated before logging."""
        body = "x" * 900
        client.session.request.return_value = make_response(
            status_code=500, text=body, content=body.encode()
        )

        with pytest.raises(AIOApiError) as exc_info:
            client.get("/path")
        assert "..." in str(exc_info.value)
        assert len(str(exc_info.value)) < 700

    def test_network_error_raises_api_error(self, client):
        """Network failures are wrapped in AIOApiError."""
        client.session.request.side_effect = requests.ConnectionError("boom")

        with pytest.raises(AIOApiError, match="Network error"):
            client.get("/path")

    def test_post_sends_json_body(self, client):
        """POST forwards the JSON payload."""
        client.session.request.return_value = make_response(json_body={"ok": True})

        client.post("/path", json={"title": "x"})

        _, kwargs = client.session.request.call_args
        assert kwargs["json"] == {"title": "x"}
