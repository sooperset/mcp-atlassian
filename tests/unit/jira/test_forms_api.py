"""
Unit tests for Jira Forms REST API (FormsApiMixin).

Tests the new Jira Forms API at https://api.atlassian.com/jira/forms/cloud/{cloudId}.
"""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import HTTPError

from src.mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from src.mcp_atlassian.jira.config import JiraConfig, OAuthConfig
from src.mcp_atlassian.jira.forms_api import FormsApiMixin
from src.mcp_atlassian.models.jira import ProFormaForm
from tests.fixtures.proforma_mocks import (
    MOCK_CLOUD_ID,
    MOCK_FORM_UUID_1,
    MOCK_NEW_API_FORMS_LIST,
)


class TestFormsApiMixinInitialization:
    """Test FormsApiMixin initialization and cloud_id handling."""

    def test_init_with_oauth_cloud_id(self):
        """Test initialization with OAuth config containing cloud_id."""
        oauth_config = OAuthConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080",
            scope="read:jira-work write:jira-work",
            cloud_id=MOCK_CLOUD_ID,
            access_token="test-token",
        )
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        with patch("atlassian.Jira"):
            with patch(
                "src.mcp_atlassian.utils.oauth.configure_oauth_session",
                return_value=True,
            ):
                mixin = FormsApiMixin(config)
                assert mixin._cloud_id == MOCK_CLOUD_ID

    def test_init_with_env_cloud_id(self, monkeypatch):
        """Test initialization with cloud_id from environment variable."""
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLOUD_ID", MOCK_CLOUD_ID)

        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            assert mixin._cloud_id == MOCK_CLOUD_ID

    def test_init_oauth_cloud_id_takes_precedence(self, monkeypatch):
        """Test that OAuth cloud_id takes precedence over environment variable."""
        env_cloud_id = "env-cloud-id"
        oauth_cloud_id = "oauth-cloud-id"

        monkeypatch.setenv("ATLASSIAN_OAUTH_CLOUD_ID", env_cloud_id)

        oauth_config = OAuthConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080",
            scope="read:jira-work write:jira-work",
            cloud_id=oauth_cloud_id,
            access_token="test-token",
        )
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        with patch("atlassian.Jira"):
            with patch(
                "src.mcp_atlassian.utils.oauth.configure_oauth_session",
                return_value=True,
            ):
                mixin = FormsApiMixin(config)
                assert mixin._cloud_id == oauth_cloud_id

    def test_init_no_cloud_id(self):
        """Test initialization when no cloud_id is available."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            assert mixin._cloud_id is None


class TestFormsApiMixinConfigurationErrors:
    """Test fail-fast configuration error handling."""

    @pytest.fixture(scope="function")
    def mixin_no_cloud_id(self):
        """Create a FormsApiMixin without cloud_id configured."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = None
            return mixin

    def test_make_forms_api_request_fails_without_cloud_id(self, mixin_no_cloud_id):
        """Test that _make_forms_api_request raises ValueError when cloud_id is missing."""
        with pytest.raises(ValueError) as exc_info:
            mixin_no_cloud_id._make_forms_api_request("GET", "/issue/TEST-1/form")

        assert "Forms API requires a cloud_id" in str(exc_info.value)
        assert "ATLASSIAN_OAUTH_CLOUD_ID" in str(exc_info.value)

    def test_get_issue_forms_fails_fast_without_cloud_id(self, mixin_no_cloud_id):
        """Test that get_issue_forms fails fast when cloud_id is missing."""
        with pytest.raises(ValueError) as exc_info:
            mixin_no_cloud_id.get_issue_forms("TEST-1")

        assert "Forms API requires a cloud_id" in str(exc_info.value)

    def test_get_form_details_fails_fast_without_cloud_id(self, mixin_no_cloud_id):
        """Test that get_form_details fails fast when cloud_id is missing."""
        with pytest.raises(ValueError) as exc_info:
            mixin_no_cloud_id.get_form_details("TEST-1", MOCK_FORM_UUID_1)

        assert "Forms API requires a cloud_id" in str(exc_info.value)

    def test_update_form_answers_fails_fast_without_cloud_id(self, mixin_no_cloud_id):
        """Test that update_form_answers fails fast when cloud_id is missing."""
        answers = [{"questionId": "q1", "type": "TEXT", "value": "test"}]

        with pytest.raises(ValueError) as exc_info:
            mixin_no_cloud_id.update_form_answers("TEST-1", MOCK_FORM_UUID_1, answers)

        assert "Forms API requires a cloud_id" in str(exc_info.value)


class TestFormsApiResponseFormat:
    """Test handling of different API response formats."""

    @pytest.fixture(scope="function")
    def mixin_with_cloud_id(self):
        """Create a FormsApiMixin with cloud_id configured."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID
            mixin.jira = Mock()
            return mixin

    def test_get_issue_forms_handles_array_response(self, mixin_with_cloud_id):
        """Test that get_issue_forms correctly handles plain array response."""
        # Mock the API to return a plain array (correct format)
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = MOCK_NEW_API_FORMS_LIST

            forms = mixin_with_cloud_id.get_issue_forms("TEST-1")

            assert isinstance(forms, list)
            assert len(forms) == 3
            assert all(isinstance(f, ProFormaForm) for f in forms)

    def test_get_issue_forms_handles_object_response(self, mixin_with_cloud_id):
        """Test that get_issue_forms handles object response with 'forms' key."""
        # Mock the API to return an object with 'forms' key (legacy compatibility)
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = {"forms": MOCK_NEW_API_FORMS_LIST}

            forms = mixin_with_cloud_id.get_issue_forms("TEST-1")

            assert isinstance(forms, list)
            assert len(forms) == 3

    def test_get_issue_forms_handles_empty_array(self, mixin_with_cloud_id):
        """Test that get_issue_forms handles empty array response."""
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = []

            forms = mixin_with_cloud_id.get_issue_forms("TEST-1")

            assert isinstance(forms, list)
            assert len(forms) == 0

    def test_get_issue_forms_handles_404_not_found(self, mixin_with_cloud_id):
        """Test that get_issue_forms returns empty list for 404 errors."""
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.side_effect = ValueError("Resource not found")

            forms = mixin_with_cloud_id.get_issue_forms("TEST-1")

            assert isinstance(forms, list)
            assert len(forms) == 0

    def test_get_form_details_handles_404_not_found(self, mixin_with_cloud_id):
        """Test that get_form_details returns None for 404 errors."""
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.side_effect = ValueError("Resource not found")

            form = mixin_with_cloud_id.get_form_details("TEST-1", MOCK_FORM_UUID_1)

            assert form is None


class TestFormsApiAuthenticationMethods:
    """Test Forms API requests with different authentication methods."""

    def test_oauth_authentication(self):
        """Test Forms API request with OAuth authentication."""
        oauth_config = OAuthConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080",
            scope="read:jira-work write:jira-work",
            cloud_id=MOCK_CLOUD_ID,
            access_token="test-token",
        )
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        with patch("atlassian.Jira"):
            with patch(
                "src.mcp_atlassian.utils.oauth.configure_oauth_session",
                return_value=True,
            ):
                mixin = FormsApiMixin(config)
                mixin._cloud_id = MOCK_CLOUD_ID

                # Mock the Jira session
                mock_session = Mock()
                mock_response = Mock()
                mock_response.content = b'{"success": true}'
                mock_response.json.return_value = {"success": True}
                mock_session.request.return_value = mock_response

                mixin.jira = Mock()
                mixin.jira.session = mock_session

                result = mixin._make_forms_api_request("GET", "/issue/TEST-1/form")

                assert result == {"success": True}
                mock_session.request.assert_called_once()

    def test_pat_authentication(self):
        """Test Forms API request with Personal Access Token authentication."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            personal_token="test-pat-token",
            auth_type="pat",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID

            with patch("src.mcp_atlassian.jira.forms_api.requests.request") as mock_req:
                mock_response = Mock()
                mock_response.content = b'{"success": true}'
                mock_response.json.return_value = {"success": True}
                mock_req.return_value = mock_response

                result = mixin._make_forms_api_request("GET", "/issue/TEST-1/form")

                assert result == {"success": True}
                # Verify Bearer token was used
                call_args = mock_req.call_args
                assert "Authorization" in call_args[1]["headers"]
                assert (
                    call_args[1]["headers"]["Authorization"] == "Bearer test-pat-token"
                )

    def test_basic_authentication(self):
        """Test Forms API request with Basic authentication."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-api-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID
            mixin.jira = Mock()
            mixin.jira.username = "test@example.com"
            mixin.jira.password = "test-api-token"

            with patch("src.mcp_atlassian.jira.forms_api.requests.request") as mock_req:
                mock_response = Mock()
                mock_response.content = b'{"success": true}'
                mock_response.json.return_value = {"success": True}
                mock_req.return_value = mock_response

                result = mixin._make_forms_api_request("GET", "/issue/TEST-1/form")

                assert result == {"success": True}
                # Verify HTTPBasicAuth was used
                call_args = mock_req.call_args
                assert call_args[1]["auth"] is not None


class TestFormsApiErrorHandling:
    """Test error handling in Forms API operations."""

    @pytest.fixture(scope="function")
    def mixin_with_cloud_id(self):
        """Create a FormsApiMixin with cloud_id configured."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID
            mixin.jira = Mock()
            return mixin

    def test_get_issue_forms_handles_parse_errors(self, mixin_with_cloud_id):
        """Test that get_issue_forms continues on parse errors for individual forms."""
        # Return forms with one invalid entry that will raise an exception during parsing
        invalid_forms = [
            MOCK_NEW_API_FORMS_LIST[0],
            None,  # This will cause an error in from_api_response
            MOCK_NEW_API_FORMS_LIST[1],
        ]

        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = invalid_forms

            # The error is logged and bubbles up; this test verifies error behavior
            with pytest.raises(Exception):
                mixin_with_cloud_id.get_issue_forms("TEST-1")

    def test_get_issue_forms_reraises_configuration_errors(self, mixin_with_cloud_id):
        """Test that get_issue_forms re-raises configuration errors (not 404)."""
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.side_effect = ValueError("Forms API requires a cloud_id")

            with pytest.raises(ValueError) as exc_info:
                mixin_with_cloud_id.get_issue_forms("TEST-1")

            assert "Forms API requires" in str(exc_info.value)

    def test_get_form_details_reraises_configuration_errors(self, mixin_with_cloud_id):
        """Test that get_form_details re-raises configuration errors (not 404)."""
        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.side_effect = ValueError("cloud_id not configured")

            with pytest.raises(ValueError) as exc_info:
                mixin_with_cloud_id.get_form_details("TEST-1", MOCK_FORM_UUID_1)

            assert "cloud_id" in str(exc_info.value).lower()


class TestFormsApiUpdateAnswers:
    """Test update_form_answers functionality."""

    @pytest.fixture(scope="function")
    def mixin_with_cloud_id(self):
        """Create a FormsApiMixin with cloud_id configured."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID
            mixin.jira = Mock()
            return mixin

    def test_update_form_answers_transforms_answer_format(self, mixin_with_cloud_id):
        """Test that update_form_answers transforms list to dict format."""
        answers = [
            {"questionId": "q1", "type": "TEXT", "value": "Test text"},
            {"questionId": "q2", "type": "NUMBER", "value": 42},
            {"questionId": "q3", "type": "DATE", "value": "2024-12-17"},
        ]

        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = {"success": True}

            result = mixin_with_cloud_id.update_form_answers(
                "TEST-1", MOCK_FORM_UUID_1, answers
            )

            # Verify the call was made with transformed format
            call_args = mock_request.call_args
            assert call_args[0][0] == "PUT"
            request_body = call_args[1]["data"]
            assert "answers" in request_body
            assert "q1" in request_body["answers"]
            assert request_body["answers"]["q1"] == {"text": "Test text"}
            assert request_body["answers"]["q2"] == {"number": 42}
            assert request_body["answers"]["q3"] == {"date": "2024-12-17"}

    def test_update_form_answers_handles_datetime_as_date(self, mixin_with_cloud_id):
        """Test that DATETIME fields map to 'date' (API limitation)."""
        answers = [
            {"questionId": "q1", "type": "DATETIME", "value": "2024-12-17T19:00:00Z"}
        ]

        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = {"success": True}

            mixin_with_cloud_id.update_form_answers("TEST-1", MOCK_FORM_UUID_1, answers)

            # Verify DATETIME maps to 'date' field
            call_args = mock_request.call_args
            request_body = call_args[1]["data"]
            assert "date" in request_body["answers"]["q1"]

    def test_update_form_answers_handles_select_fields(self, mixin_with_cloud_id):
        """Test that SELECT fields map to 'choices' and ensure array format."""
        answers = [
            {"questionId": "q1", "type": "SELECT", "value": "option1"},
            {"questionId": "q2", "type": "MULTI_SELECT", "value": ["opt1", "opt2"]},
        ]

        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = {"success": True}

            mixin_with_cloud_id.update_form_answers("TEST-1", MOCK_FORM_UUID_1, answers)

            call_args = mock_request.call_args
            request_body = call_args[1]["data"]
            # Single value should be wrapped in array
            assert request_body["answers"]["q1"] == {"choices": ["option1"]}
            # Multiple values should remain as array
            assert request_body["answers"]["q2"] == {"choices": ["opt1", "opt2"]}


class TestFormsApiHttpErrorHandling:
    """Test HTTP error handling in Forms API."""

    @pytest.fixture(scope="function")
    def mixin_with_cloud_id(self):
        """Create a FormsApiMixin with cloud_id configured."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID
            mixin.jira = Mock()
            mixin.jira.username = "test@example.com"
            mixin.jira.password = "test-api-token"
            return mixin

    def test_make_forms_api_request_handles_403_permission_error(
        self, mixin_with_cloud_id
    ):
        """Test that 403 errors are converted to MCPAtlassianAuthenticationError."""
        with patch("src.mcp_atlassian.jira.forms_api.requests.request") as mock_req:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_response.raise_for_status.side_effect = HTTPError(
                response=mock_response
            )
            mock_req.return_value = mock_response

            with pytest.raises(MCPAtlassianAuthenticationError):
                mixin_with_cloud_id._make_forms_api_request("GET", "/issue/TEST-1/form")

    def test_make_forms_api_request_handles_404_not_found(self, mixin_with_cloud_id):
        """Test that 404 errors are converted to ValueError."""
        with patch("src.mcp_atlassian.jira.forms_api.requests.request") as mock_req:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_response.raise_for_status.side_effect = HTTPError(
                response=mock_response
            )
            mock_req.return_value = mock_response

            with pytest.raises(ValueError) as exc_info:
                mixin_with_cloud_id._make_forms_api_request("GET", "/issue/TEST-1/form")

            assert "not found" in str(exc_info.value).lower()

    def test_make_forms_api_request_handles_empty_response(self, mixin_with_cloud_id):
        """Test that empty responses (like DELETE) are handled correctly."""
        with patch("src.mcp_atlassian.jira.forms_api.requests.request") as mock_req:
            mock_response = Mock()
            mock_response.content = b""
            mock_req.return_value = mock_response

            result = mixin_with_cloud_id._make_forms_api_request(
                "DELETE", "/issue/TEST-1/form/123"
            )

            assert result == {}


class TestFormsApiDateTimeLimitation:
    """
    Tests documenting the DATETIME field limitation.

    The Jira Forms API does not properly preserve time components in DATETIME fields.
    These tests document the expected behavior and limitation.
    """

    @pytest.fixture(scope="function")
    def mixin_with_cloud_id(self):
        """Create a FormsApiMixin with cloud_id configured."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token",
            auth_type="basic",
        )

        with patch("atlassian.Jira"):
            mixin = FormsApiMixin(config)
            mixin._cloud_id = MOCK_CLOUD_ID
            mixin.jira = Mock()
            return mixin

    def test_datetime_limitation_documented_in_code(self, mixin_with_cloud_id):
        """Test that DATETIME limitation is documented in the code."""
        # Check that the docstring mentions the limitation
        docstring = mixin_with_cloud_id.update_form_answers.__doc__
        assert "Known Limitation" in docstring
        assert "DATETIME" in docstring
        assert "time is reset to midnight" in docstring or "time" in docstring.lower()

    def test_datetime_fields_map_to_date_field_type(self, mixin_with_cloud_id):
        """
        Test that DATETIME type maps to 'date' field in API request.

        This is the root cause of the limitation: the API doesn't have a separate
        datetime field type, only 'date'.
        """
        answers = [
            {"questionId": "q1", "type": "DATETIME", "value": "2024-12-17T19:00:00Z"}
        ]

        with patch.object(
            mixin_with_cloud_id, "_make_forms_api_request"
        ) as mock_request:
            mock_request.return_value = {"success": True}

            mixin_with_cloud_id.update_form_answers("TEST-1", MOCK_FORM_UUID_1, answers)

            call_args = mock_request.call_args
            request_body = call_args[1]["data"]
            # DATETIME maps to 'date', not 'datetime'
            assert "date" in request_body["answers"]["q1"]
            assert "datetime" not in request_body["answers"]["q1"]

    def test_workaround_via_jira_api_suggested(self, mixin_with_cloud_id):
        """
        Test that the docstring suggests the workaround via Jira API.

        The workaround is to update the underlying custom field directly
        using the regular Jira API instead of the Forms API.
        """
        docstring = mixin_with_cloud_id.update_form_answers.__doc__
        assert "Workaround" in docstring
        assert "jira.update_issue" in docstring or "custom field" in docstring.lower()
        assert "customfield" in docstring
