"""Module for Jira ProForma form operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..models.jira import ProFormaForm
from .client import JiraClient
from .forms_common import handle_forms_http_error

logger = logging.getLogger("mcp-jira")


class FormsMixin(JiraClient):
    """Mixin for Jira ProForma form operations."""

    def get_issue_forms(self, issue_key: str) -> list[ProFormaForm]:
        """
        Get all ProForma forms associated with an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of ProFormaForm objects

        Raises:
            Exception: If there is an error getting forms
        """
        try:
            # Get the issue properties to find forms
            response = self.jira.get(
                f"rest/api/3/issue/{issue_key}/properties/proforma.forms"
            )

            if not isinstance(response, dict):
                msg = f"Unexpected response type from forms API: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            forms_data = response.get("value", {})
            forms = []

            # Parse form data from the response
            for form_key, form_data in forms_data.items():
                if form_key.startswith("i"):  # Form identifiers start with 'i'
                    form = ProFormaForm.from_api_response(
                        form_data, issue_key=issue_key
                    )
                    form.form_id = form_key
                    forms.append(form)

            return forms

        except HTTPError as e:
            if e.response.status_code == 404:
                # No forms found for this issue
                return []
            raise handle_forms_http_error(e, "getting forms", issue_key) from e
        except Exception as e:
            logger.error(f"Error getting forms for issue {issue_key}: {str(e)}")
            error_msg = f"Error getting forms: {str(e)}"
            raise Exception(error_msg) from e

    def get_form_details(self, issue_key: str, form_id: str) -> ProFormaForm | None:
        """
        Get detailed information about a specific ProForma form.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form identifier (e.g. 'i12345')

        Returns:
            ProFormaForm object or None if not found

        Raises:
            Exception: If there is an error getting form details
        """
        try:
            response = self.jira.get(
                f"rest/api/3/issue/{issue_key}/properties/proforma.forms.{form_id}"
            )

            if not isinstance(response, dict):
                msg = (
                    f"Unexpected response type from form details API: {type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            form_data = response.get("value", {})
            if not form_data:
                return None

            form = ProFormaForm.from_api_response(form_data, issue_key=issue_key)
            form.form_id = form_id
            return form

        except HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise handle_forms_http_error(
                e, "getting form details", f"{issue_key}/{form_id}"
            ) from e
        except Exception as e:
            logger.error(
                f"Error getting form details for {issue_key}/{form_id}: {str(e)}"
            )
            error_msg = f"Error getting form details: {str(e)}"
            raise Exception(error_msg) from e

    def reopen_form(self, issue_key: str, form_id: str) -> dict[str, Any]:
        """
        Reopen a submitted ProForma form to allow editing.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form identifier (e.g. 'i12345')

        Returns:
            Response data from the API

        Raises:
            Exception: If there is an error reopening the form
        """
        try:
            # Prepare the request body to set form status to open
            request_body = {"value": {"state": {"status": "o"}}}

            # Make the PUT request to reopen the form
            response = self.jira.put(
                f"rest/api/3/issue/{issue_key}/properties/proforma.forms.{form_id}",
                data=request_body,
            )

            logger.info(f"Successfully reopened form {form_id} for issue {issue_key}")
            return response if isinstance(response, dict) else {}

        except HTTPError as e:
            raise handle_forms_http_error(
                e, "reopening form", f"{issue_key}/{form_id}"
            ) from e
        except Exception as e:
            logger.error(
                f"Error reopening form {form_id} for issue {issue_key}: {str(e)}"
            )
            error_msg = f"Error reopening form: {str(e)}"
            raise Exception(error_msg) from e

    def submit_form(self, issue_key: str, form_id: str) -> dict[str, Any]:
        """
        Submit a ProForma form after making changes.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            form_id: The form identifier (e.g. 'i12345')

        Returns:
            Response data from the API

        Raises:
            Exception: If there is an error submitting the form
        """
        try:
            # Make the POST request to submit the form
            response = self.jira.post(
                f"rest/api/3/issue/{issue_key}/properties/proforma.forms.{form_id}/submit"
            )

            logger.info(f"Successfully submitted form {form_id} for issue {issue_key}")
            return response if isinstance(response, dict) else {}

        except HTTPError as e:
            raise handle_forms_http_error(
                e, "submitting form", f"{issue_key}/{form_id}"
            ) from e
        except Exception as e:
            logger.error(
                f"Error submitting form {form_id} for issue {issue_key}: {str(e)}"
            )
            error_msg = f"Error submitting form: {str(e)}"
            raise Exception(error_msg) from e

    def update_form_field(
        self, issue_key: str, field_id: str, field_value: Any
    ) -> dict[str, Any]:
        """
        Update a field in a ProForma form by updating the associated Jira field.

        This method works by updating the Jira custom field that is linked
        to the ProForma form field. This is often more reliable than trying
        to update the form directly.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            field_id: The Jira field ID (e.g. 'customfield_10001')
            field_value: The new value for the field

        Returns:
            Response data from the API

        Raises:
            Exception: If there is an error updating the field
        """
        try:
            # Prepare the field update
            update_data = {"fields": {field_id: field_value}}

            # Update the issue with the new field value
            response = self.jira.put(f"rest/api/3/issue/{issue_key}", data=update_data)

            logger.info(f"Successfully updated field {field_id} for issue {issue_key}")
            return response if isinstance(response, dict) else {}

        except HTTPError as e:
            raise handle_forms_http_error(
                e, "updating field", f"{issue_key}/{field_id}"
            ) from e
        except Exception as e:
            logger.error(
                f"Error updating field {field_id} for issue {issue_key}: {str(e)}"
            )
            error_msg = f"Error updating field: {str(e)}"
            raise Exception(error_msg) from e
