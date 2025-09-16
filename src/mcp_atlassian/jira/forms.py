"""Module for Jira Forms operations."""

import logging
from typing import TYPE_CHECKING, Any

from requests.exceptions import HTTPError

if TYPE_CHECKING:
    from .config import JiraConfig

logger = logging.getLogger("mcp-jira")


class FormsMixin:
    """Mixin for Jira Forms operations."""

    jira_forms: Any
    config: "JiraConfig"

    def __init__(self, config: "JiraConfig", jira_forms: Any) -> None:
        """Initialize the FormsMixin.

        Args:
            config: Jira configuration object
            jira_forms: Jira Forms client object
        """
        self.config = config
        self.jira_forms = jira_forms

    def get_form(self, form_id: str) -> dict:
        """Retrieves a Jira Form definition."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"form/{form_id}"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(f"Error retrieving form {form_id}: {e}")
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def get_issue_forms(self, issue_key: str) -> dict:
        """Retrieves the forms attached to an issue."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(f"Error retrieving forms for issue {issue_key}: {e}")
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def submit_form(self, issue_key: str, form_id: str, answers: dict) -> dict:
        """Submits a form for an issue."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form/{form_id}/submit"
        try:
            response = self.jira_forms.post(endpoint, json=answers)
            return response or {}
        except HTTPError as e:
            logger.error(f"Error submitting form {form_id} for issue {issue_key}: {e}")
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def get_form_answers(self, issue_key: str, form_id: str) -> dict:
        """Retrieve the answers from a submitted form."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form/{form_id}"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error retrieving form answers for form {form_id} on issue {issue_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def attach_form(self, issue_key: str, form_template_id: str) -> dict:
        """Attaches a form template to an issue."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form"
        payload = {"formTemplate": {"id": form_template_id}}
        try:
            response = self.jira_forms.post(endpoint, json=payload)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error attaching form template {form_template_id} to issue {issue_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def get_issue_forms_index(self, issue_key: str) -> dict:
        """Retrieves the index of forms attached to an issue."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(f"Error retrieving form index for issue {issue_key}: {e}")
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def change_form_visibility(
        self, issue_key: str, form_id: str, visibility: str
    ) -> dict:
        """Changes the visibility of a form (external/internal)."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form/{form_id}/visibility"
        payload = {"visibility": visibility}
        try:
            response = self.jira_forms.put(endpoint, json=payload)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error changing visibility for form {form_id} on issue {issue_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def submit_form_action(self, issue_key: str, form_id: str, action: str) -> dict:
        """Submits a form action (submit/reject)."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form/{form_id}/action"
        payload = {"action": action}
        try:
            response = self.jira_forms.post(endpoint, json=payload)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error submitting form action {action} for form {form_id} on issue {issue_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def reopen_form(self, issue_key: str, form_id: str) -> dict:
        """Reopens a form for editing."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form/{form_id}/reopen"
        try:
            response = self.jira_forms.post(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(f"Error reopening form {form_id} on issue {issue_key}: {e}")
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def copy_forms(
        self, source_issue_key: str, target_issue_key: str, form_ids: list
    ) -> dict:
        """Copies forms from one issue to another."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{target_issue_key}/form/copy"
        payload = {"sourceIssueKey": source_issue_key, "formIds": form_ids}
        try:
            response = self.jira_forms.post(endpoint, json=payload)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error copying forms from {source_issue_key} to {target_issue_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def get_form_simplified_answers(self, issue_key: str, form_id: str) -> dict:
        """Retrieves simplified answers from a submitted form."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"issue/{issue_key}/form/{form_id}/answers"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error retrieving simplified answers for form {form_id} on issue {issue_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def get_project_form_templates(self, project_key: str) -> dict:
        """Retrieves form templates for a project."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"project/{project_key}/form"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error retrieving form templates for project {project_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def get_project_form_template(self, project_key: str, template_id: str) -> dict:
        """Retrieves a specific form template for a project."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"project/{project_key}/form/{template_id}"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error retrieving form template {template_id} for project {project_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def export_form_template(self, project_key: str, template_id: str) -> dict:
        """Exports a form template from a project."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"project/{project_key}/form/{template_id}/export"
        try:
            response = self.jira_forms.get(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error exporting form template {template_id} from project {project_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def create_project_form_template(
        self, project_key: str, template_data: dict
    ) -> dict:
        """Creates a new form template in a project."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"project/{project_key}/form"
        try:
            # Add debug logging
            logger.debug(f"Creating form template for project {project_key}")
            logger.debug(
                f"Forms client URL: {getattr(self.jira_forms, 'url', 'No URL available')}"
            )
            logger.debug(f"Endpoint: {endpoint}")
            logger.debug(f"Template data: {template_data}")

            response = self.jira_forms.post(endpoint, json=template_data)
            logger.debug(f"Response: {response}")
            return response or {}
        except HTTPError as e:
            logger.error(f"Error creating form template for project {project_key}: {e}")
            # Enhanced error logging
            if hasattr(e, "response") and e.response:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response headers: {e.response.headers}")
                logger.error(f"Response content: {e.response.text}")
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def update_project_form_template(
        self, project_key: str, template_id: str, template_data: dict
    ) -> dict:
        """Updates an existing form template in a project."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"project/{project_key}/form/{template_id}"
        try:
            response = self.jira_forms.put(endpoint, json=template_data)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error updating form template {template_id} for project {project_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }

    def delete_project_form_template(self, project_key: str, template_id: str) -> dict:
        """Deletes a form template from a project."""
        if not self.jira_forms:
            return {
                "error": "Jira Forms client is not available. Please check your Jira configuration and ensure Forms is enabled for your instance.",
                "status_code": 503,
            }
        endpoint = f"project/{project_key}/form/{template_id}"
        try:
            response = self.jira_forms.delete(endpoint)
            return response or {}
        except HTTPError as e:
            logger.error(
                f"Error deleting form template {template_id} from project {project_key}: {e}"
            )
            return {
                "error": str(e),
                "status_code": e.response.status_code if e.response else None,
            }
