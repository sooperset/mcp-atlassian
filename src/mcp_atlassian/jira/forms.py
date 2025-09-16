"""Module for Jira Forms operations."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import JiraConfig

logger = logging.getLogger("mcp-jira")


class FormsMixin:
    """Mixin for Jira Forms operations."""

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
        return response

    def get_issue_forms(self, issue_key: str) -> dict:
        """Retrieves the forms attached to an issue."""
        endpoint = f"issue/{issue_key}/form"
        response = self.jira.get(endpoint)
        return response

    def submit_form(self, issue_key: str, form_id: str, answers: dict) -> dict:
        """Submits a form for an issue."""
        endpoint = f"issue/{issue_key}/form/{form_id}/submit"
        response = self.jira.post(endpoint, json=answers)
        return response

    def get_form_answers(self, issue_key: str, form_id: str) -> dict:
        """Retrieve the answers from a submitted form."""
        endpoint = f"issue/{issue_key}/form/{form_id}"
        response = self.jira.get(endpoint)
        return response
