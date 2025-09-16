"""Module for Jira Forms operations."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import JiraConfig

logger = logging.getLogger("mcp-jira")


class FormsMixin:
    """Mixin for Jira Forms operations."""

    jira: Any
    config: "JiraConfig"

    def __init__(self, config: "JiraConfig") -> None:
        """Initialize the FormsMixin.

        Args:
            config: Jira configuration object
        """
        self.config = config

    def get_form(self, form_id: str) -> dict:
        """Retrieves a Jira Form definition."""
        endpoint = f"form/{form_id}"
        response = self.jira.get(endpoint)
        return response or {}

    def get_issue_forms(self, issue_key: str) -> dict:
        """Retrieves the forms attached to an issue."""
        endpoint = f"issue/{issue_key}/form"
        response = self.jira.get(endpoint)
        return response or {}

    def submit_form(self, issue_key: str, form_id: str, answers: dict) -> dict:
        """Submits a form for an issue."""
        endpoint = f"issue/{issue_key}/form/{form_id}/submit"
        response = self.jira.post(endpoint, json=answers)
        return response or {}

    def get_form_answers(self, issue_key: str, form_id: str) -> dict:
        """Retrieve the answers from a submitted form."""
        endpoint = f"issue/{issue_key}/form/{form_id}"
        response = self.jira.get(endpoint)
        return response or {}

    def attach_form(self, issue_key: str, form_template_id: str) -> dict:
        """Attaches a form template to an issue."""
        endpoint = f"issue/{issue_key}/form"
        payload = {"formTemplate": {"id": form_template_id}}
        response = self.jira.post(endpoint, json=payload)
        return response or {}

    def get_issue_forms_index(self, issue_key: str) -> dict:
        """Retrieves the index of forms attached to an issue."""
        endpoint = f"issue/{issue_key}/form"
        response = self.jira.get(endpoint)
        return response or {}

    def change_form_visibility(
        self, issue_key: str, form_id: str, visibility: str
    ) -> dict:
        """Changes the visibility of a form (external/internal)."""
        endpoint = f"issue/{issue_key}/form/{form_id}/visibility"
        payload = {"visibility": visibility}
        response = self.jira.put(endpoint, json=payload)
        return response or {}

    def submit_form_action(self, issue_key: str, form_id: str, action: str) -> dict:
        """Submits a form action (submit/reject)."""
        endpoint = f"issue/{issue_key}/form/{form_id}/action"
        payload = {"action": action}
        response = self.jira.post(endpoint, json=payload)
        return response or {}

    def reopen_form(self, issue_key: str, form_id: str) -> dict:
        """Reopens a form for editing."""
        endpoint = f"issue/{issue_key}/form/{form_id}/reopen"
        response = self.jira.post(endpoint)
        return response or {}

    def copy_forms(
        self, source_issue_key: str, target_issue_key: str, form_ids: list
    ) -> dict:
        """Copies forms from one issue to another."""
        endpoint = f"issue/{target_issue_key}/form/copy"
        payload = {"sourceIssueKey": source_issue_key, "formIds": form_ids}
        response = self.jira.post(endpoint, json=payload)
        return response or {}

    def get_form_simplified_answers(self, issue_key: str, form_id: str) -> dict:
        """Retrieves simplified answers from a submitted form."""
        endpoint = f"issue/{issue_key}/form/{form_id}/answers"
        response = self.jira.get(endpoint)
        return response or {}

    def get_project_form_templates(self, project_key: str) -> dict:
        """Retrieves form templates for a project."""
        endpoint = f"project/{project_key}/form"
        response = self.jira.get(endpoint)
        return response or {}

    def get_project_form_template(self, project_key: str, template_id: str) -> dict:
        """Retrieves a specific form template for a project."""
        endpoint = f"project/{project_key}/form/{template_id}"
        response = self.jira.get(endpoint)
        return response or {}

    def export_form_template(self, project_key: str, template_id: str) -> dict:
        """Exports a form template from a project."""
        endpoint = f"project/{project_key}/form/{template_id}/export"
        response = self.jira.get(endpoint)
        return response or {}

    def create_project_form_template(
        self, project_key: str, template_data: dict
    ) -> dict:
        """Creates a new form template in a project."""
        endpoint = f"project/{project_key}/form"
        response = self.jira.post(endpoint, json=template_data)
        return response or {}

    def update_project_form_template(
        self, project_key: str, template_id: str, template_data: dict
    ) -> dict:
        """Updates an existing form template in a project."""
        endpoint = f"project/{project_key}/form/{template_id}"
        response = self.jira.put(endpoint, json=template_data)
        return response or {}

    def delete_project_form_template(self, project_key: str, template_id: str) -> dict:
        """Deletes a form template from a project."""
        endpoint = f"project/{project_key}/form/{template_id}"
        response = self.jira.delete(endpoint)
        return response or {}
