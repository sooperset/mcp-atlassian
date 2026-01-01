"""Module for Jira Forms REST API operations.

This module provides support for the Jira Forms REST API at
https://api.atlassian.com/jira/forms/cloud/{cloudId}.

Features:
- UUID-based form IDs
- Atlassian Document Format (ADF) for form layouts
- Direct field updates via PUT /form/{formId}
- Support for form templates, attachments, and exports
"""

import logging
from typing import Any

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError

from ..models.jira import ProFormaForm
from .client import JiraClient
from .forms_common import handle_forms_http_error

logger = logging.getLogger("mcp-jira")


class FormsApiMixin(JiraClient):
    """Mixin for Jira Forms REST API operations.

    This uses the Forms API at https://api.atlassian.com/jira/forms/cloud/{cloudId}.
    The cloud_id is obtained from OAuth config or must be provided via environment variable.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Forms API mixin.

        Raises:
            ValueError: If cloud_id cannot be determined from config
        """
        super().__init__(*args, **kwargs)

        # Get cloud_id from OAuth config if available
        if self.config.oauth_config and self.config.oauth_config.cloud_id:
            self._cloud_id = self.config.oauth_config.cloud_id
        else:
            # cloud_id is required for Forms API
            error_msg = (
                "Forms API requires a cloud_id. "
                "For OAuth, this is automatically retrieved. "
                "For other auth types, provide it via ATLASSIAN_OAUTH_CLOUD_ID environment variable "
                "or X-Atlassian-Cloud-Id header."
            )
            raise ValueError(error_msg)

        self._forms_api_base = (
            f"https://api.atlassian.com/jira/forms/cloud/{self._cloud_id}"
        )

    def _make_forms_api_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a request to the Forms API.

        Supports all authentication types: OAuth, PAT, and Basic Auth.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (e.g., '/issue/PROJ-123/form')
            data: Optional request body data

        Returns:
            Response data from the API as a dictionary

        Raises:
            MCPAtlassianAuthenticationError: For 403 permission errors
            ValueError: For 404 not found errors
            Exception: For other HTTP errors
        """
        url = f"{self._forms_api_base}{endpoint}"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}

        # Determine authentication method based on config
        auth = None
        if self.config.auth_type == "oauth":
            # For OAuth, use the session from the Jira client which has OAuth configured
            if hasattr(self.jira, "session") and self.jira.session:
                try:
                    response = self.jira.session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=data,
                        timeout=30,
                    )
                    response.raise_for_status()

                    # Handle empty responses (like DELETE)
                    if not response.content:
                        return {}

                    json_response: dict[str, Any] = response.json()
                    return json_response
                except HTTPError as e:
                    logger.error(
                        f"HTTP error in Forms API (OAuth): {e} - Response: {e.response.text[:500]}"
                    )
                    raise handle_forms_http_error(
                        e, "Forms API request", endpoint
                    ) from e
                except requests.RequestException as e:
                    logger.error(
                        f"Request error making Forms API request to {endpoint}: {str(e)}"
                    )
                    raise
            else:
                error_msg = "OAuth session not available in Jira client"
                raise ValueError(error_msg)
        elif self.config.auth_type == "pat":
            # For PAT, use Bearer token authentication
            if self.config.personal_token:
                headers["Authorization"] = f"Bearer {self.config.personal_token}"
            else:
                error_msg = "Personal access token not configured"
                raise ValueError(error_msg)
        else:  # basic auth
            # For basic auth, use HTTPBasicAuth with username and API token
            username = self.jira.username or ""
            password = self.jira.password or ""
            auth = HTTPBasicAuth(username, password)

        # For PAT and basic auth, make the request with requests library
        if self.config.auth_type in ["pat", "basic"]:
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    auth=auth,
                    headers=headers,
                    json=data,
                    timeout=30,
                )
                response.raise_for_status()

                # Handle empty responses (like DELETE)
                if not response.content:
                    return {}

                json_response: dict[str, Any] = response.json()
                return json_response

            except HTTPError as e:
                logger.error(
                    f"HTTP error in Forms API ({self.config.auth_type}): {e} - Response: {e.response.text[:500]}"
                )
                raise handle_forms_http_error(e, "Forms API request", endpoint) from e
            except requests.RequestException as e:
                logger.error(
                    f"Request error making Forms API request to {endpoint}: {str(e)}"
                )
                raise

        error_msg = f"Unsupported auth type: {self.config.auth_type}"
        raise ValueError(error_msg)

    def get_issue_forms(self, issue_key: str) -> list[ProFormaForm]:
        """Get all forms associated with an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of ProFormaForm objects

        Raises:
            Exception: If there is an error getting forms
        """
        try:
            response = self._make_forms_api_request("GET", f"/issue/{issue_key}/form")

            # API should return a list wrapped in a forms key
            forms_data = response.get("forms", []) if isinstance(response, dict) else []

            forms = []
            for form_data in forms_data:
                try:
                    # API returns a simplified list format
                    # We'll need to fetch details for each form to get full data
                    form = ProFormaForm.from_api_response(
                        form_data, issue_key=issue_key
                    )
                    forms.append(form)
                except (KeyError, TypeError, ValueError) as e:
                    logger.error(f"Error parsing form data: {str(e)}")
                    continue

            return forms

        except ValueError:
            # 404 - no forms found
            return []
        except Exception as e:
            logger.error(f"Error getting forms for issue {issue_key}: {str(e)}")
            raise

    def get_form_details(self, issue_key: str, form_id: str) -> ProFormaForm | None:
        """Get detailed information about a specific form.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form UUID (e.g. '1946b8b7-8f03-4dc0-ac2d-5fac0d960c6a')

        Returns:
            ProFormaForm object or None if not found

        Raises:
            Exception: If there is an error getting form details
        """
        try:
            response = self._make_forms_api_request(
                "GET", f"/issue/{issue_key}/form/{form_id}"
            )

            # API returns ADF (Atlassian Document Format) structure
            form = ProFormaForm.from_api_response(
                response, issue_key=issue_key
            )
            return form

        except ValueError:
            # 404 - form not found
            return None
        except Exception as e:
            logger.error(
                f"Error getting form details for {issue_key}/{form_id}: {str(e)}"
            )
            raise

    def update_form_answers(
        self, issue_key: str, form_id: str, answers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Update form field answers directly via the Forms API.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form UUID
            answers: List of answer objects, each with:
                - questionId: ID of the question to answer
                - type: Answer type (TEXT, NUMBER, DATE, etc.)
                - value: The answer value

        Returns:
            Response data from the API

        Raises:
            Exception: If there is an error updating the form
        """
        try:
            # Transform answers from list format to the API's expected object format
            # API expects: {"answers": {"questionId": {"type": value}, ...}}
            # We receive: [{"questionId": "1", "type": "TEXT", "value": "foo"}, ...]
            answers_dict = {}
            for answer in answers:
                question_id = answer.get("questionId")
                answer_type = answer.get("type", "TEXT")
                value = answer.get("value")

                # Map answer types to API field names
                type_mapping = {
                    "TEXT": "text",
                    "NUMBER": "number",
                    "DATE": "date",
                    "DATETIME": "date",
                    "TIME": "time",
                    "SELECT": "choices",
                    "MULTI_SELECT": "choices",
                    "CHECKBOX": "choices",
                    "USER": "users",
                    "MULTI_USER": "users",
                }

                field_name = type_mapping.get(answer_type, "text")

                # For choices/users, ensure value is an array
                if field_name in ("choices", "users") and not isinstance(value, list):
                    value = [value] if value else []

                answers_dict[question_id] = {field_name: value}

            request_body = {"answers": answers_dict}

            response = self._make_forms_api_request(
                "PUT", f"/issue/{issue_key}/form/{form_id}", data=request_body
            )

            logger.info(f"Successfully updated form {form_id} for issue {issue_key}")
            return response

        except Exception as e:
            logger.error(f"Error updating form {form_id} for {issue_key}: {str(e)}")
            raise

    def add_form_template(self, issue_key: str, template_id: str) -> dict[str, Any]:
        """Add a form template to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            template_id: The form template UUID

        Returns:
            Response data from the API

        Raises:
            Exception: If there is an error adding the template
        """
        try:
            request_body = {"formTemplateId": template_id}

            response = self._make_forms_api_request(
                "POST", f"/issue/{issue_key}/form", data=request_body
            )

            logger.info(f"Successfully added form template to issue {issue_key}")
            return response

        except Exception as e:
            logger.error(f"Error adding form template to {issue_key}: {str(e)}")
            raise

    def delete_form(self, issue_key: str, form_id: str) -> None:
        """Delete a form from an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form UUID

        Raises:
            Exception: If there is an error deleting the form
        """
        try:
            self._make_forms_api_request("DELETE", f"/issue/{issue_key}/form/{form_id}")

            logger.info(f"Successfully deleted form {form_id} from issue {issue_key}")

        except Exception as e:
            logger.error(f"Error deleting form {form_id} from {issue_key}: {str(e)}")
            raise

    def get_form_attachments(
        self, issue_key: str, form_id: str
    ) -> list[dict[str, Any]]:
        """Get attachment metadata for a form.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form UUID

        Returns:
            List of attachment metadata

        Raises:
            Exception: If there is an error getting attachments
        """
        try:
            response = self._make_forms_api_request(
                "GET", f"/issue/{issue_key}/form/{form_id}/attachment"
            )

            # API should return attachments wrapped in an 'attachments' key
            attachments = response.get("attachments", [])
            if not isinstance(attachments, list):
                return []

            return attachments

        except ValueError:
            # 404 - no attachments
            return []
        except Exception as e:
            logger.error(f"Error getting attachments for form {form_id}: {str(e)}")
            raise
