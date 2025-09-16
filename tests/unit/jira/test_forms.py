"""Unit tests for Jira Forms operations."""

import unittest
from unittest.mock import MagicMock, patch

from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.forms import FormsMixin


class TestFormsMixin(unittest.TestCase):
    """Test suite for the FormsMixin."""

    @patch("mcp_atlassian.jira.config.JiraConfig.from_env")
    def setUp(self, mock_from_env):
        """Set up the test case."""
        mock_config = MagicMock(spec=JiraConfig)
        mock_config.url = "https://test.jira.com"
        mock_from_env.return_value = mock_config
        self.mixin = FormsMixin(config=mock_config)
        self.mixin.jira = MagicMock()

    def test_get_form(self):
        """Test get_form method."""
        self.mixin.jira.get.return_value = {"id": "123", "name": "Test Form"}
        form = self.mixin.get_form("123")
        self.mixin.jira.get.assert_called_with("form/123")
        self.assertEqual(form["name"], "Test Form")

    def test_get_issue_forms(self):
        """Test get_issue_forms method."""
        self.mixin.jira.get.return_value = [{"id": "123", "name": "Test Form"}]
        forms = self.mixin.get_issue_forms("PROJ-1")
        self.mixin.jira.get.assert_called_with("issue/PROJ-1/form")
        self.assertEqual(len(forms), 1)

    def test_submit_form(self):
        """Test submit_form method."""
        answers = {"question_1": "answer_1"}
        self.mixin.jira.post.return_value = {"success": True}
        result = self.mixin.submit_form("PROJ-1", "123", answers)
        self.mixin.jira.post.assert_called_with(
            "issue/PROJ-1/form/123/submit", json=answers
        )
        self.assertTrue(result["success"])

    def test_get_form_answers(self):
        """Test get_form_answers method."""
        self.mixin.jira.get.return_value = {
            "id": "123", "answers": {"question_1": "answer_1"}
        }
        form = self.mixin.get_form_answers("PROJ-1", "123")
        self.mixin.jira.get.assert_called_with("issue/PROJ-1/form/123")
        self.assertEqual(form["answers"]["question_1"], "answer_1")


if __name__ == "__main__":
    unittest.main()
