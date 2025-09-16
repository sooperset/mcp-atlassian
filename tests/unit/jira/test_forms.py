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
            "id": "123",
            "answers": {"question_1": "answer_1"},
        }
        form = self.mixin.get_form_answers("PROJ-1", "123")
        self.mixin.jira.get.assert_called_with("issue/PROJ-1/form/123")
        self.assertEqual(form["answers"]["question_1"], "answer_1")

    def test_attach_form(self):
        """Test attach_form method."""
        form_template_id = "template-123"
        expected_payload = {"formTemplate": {"id": form_template_id}}
        self.mixin.jira.post.return_value = {
            "id": "456",
            "issueKey": "PROJ-1",
            "status": "attached",
        }
        result = self.mixin.attach_form("PROJ-1", form_template_id)
        self.mixin.jira.post.assert_called_with(
            "issue/PROJ-1/form", json=expected_payload
        )
        self.assertEqual(result["status"], "attached")

    def test_get_issue_forms_index(self):
        """Test get_issue_forms_index method."""
        self.mixin.jira.get.return_value = {
            "forms": [{"id": "123", "name": "Test Form"}]
        }
        result = self.mixin.get_issue_forms_index("PROJ-1")
        self.mixin.jira.get.assert_called_with("issue/PROJ-1/form")
        self.assertEqual(len(result["forms"]), 1)

    def test_change_form_visibility(self):
        """Test change_form_visibility method."""
        expected_payload = {"visibility": "external"}
        self.mixin.jira.put.return_value = {"success": True}
        result = self.mixin.change_form_visibility("PROJ-1", "123", "external")
        self.mixin.jira.put.assert_called_with(
            "issue/PROJ-1/form/123/visibility", json=expected_payload
        )
        self.assertTrue(result["success"])

    def test_submit_form_action(self):
        """Test submit_form_action method."""
        expected_payload = {"action": "submit"}
        self.mixin.jira.post.return_value = {"success": True}
        result = self.mixin.submit_form_action("PROJ-1", "123", "submit")
        self.mixin.jira.post.assert_called_with(
            "issue/PROJ-1/form/123/action", json=expected_payload
        )
        self.assertTrue(result["success"])

    def test_reopen_form(self):
        """Test reopen_form method."""
        self.mixin.jira.post.return_value = {"success": True}
        result = self.mixin.reopen_form("PROJ-1", "123")
        self.mixin.jira.post.assert_called_with("issue/PROJ-1/form/123/reopen")
        self.assertTrue(result["success"])

    def test_copy_forms(self):
        """Test copy_forms method."""
        expected_payload = {"sourceIssueKey": "PROJ-1", "formIds": ["123", "456"]}
        self.mixin.jira.post.return_value = {"success": True}
        result = self.mixin.copy_forms("PROJ-1", "PROJ-2", ["123", "456"])
        self.mixin.jira.post.assert_called_with(
            "issue/PROJ-2/form/copy", json=expected_payload
        )
        self.assertTrue(result["success"])

    def test_get_form_simplified_answers(self):
        """Test get_form_simplified_answers method."""
        self.mixin.jira.get.return_value = {
            "id": "123",
            "answers": {"question_1": "answer_1"},
        }
        result = self.mixin.get_form_simplified_answers("PROJ-1", "123")
        self.mixin.jira.get.assert_called_with("issue/PROJ-1/form/123/answers")
        self.assertEqual(result["answers"]["question_1"], "answer_1")

    def test_get_project_form_templates(self):
        """Test get_project_form_templates method."""
        self.mixin.jira.get.return_value = {
            "templates": [{"id": "123", "name": "Test Template"}]
        }
        result = self.mixin.get_project_form_templates("PROJ")
        self.mixin.jira.get.assert_called_with("project/PROJ/form")
        self.assertEqual(len(result["templates"]), 1)

    def test_get_project_form_template(self):
        """Test get_project_form_template method."""
        self.mixin.jira.get.return_value = {"id": "123", "name": "Test Template"}
        result = self.mixin.get_project_form_template("PROJ", "123")
        self.mixin.jira.get.assert_called_with("project/PROJ/form/123")
        self.assertEqual(result["name"], "Test Template")

    def test_export_form_template(self):
        """Test export_form_template method."""
        self.mixin.jira.get.return_value = {"id": "123", "export_data": "test"}
        result = self.mixin.export_form_template("PROJ", "123")
        self.mixin.jira.get.assert_called_with("project/PROJ/form/123/export")
        self.assertEqual(result["export_data"], "test")

    def test_create_project_form_template(self):
        """Test create_project_form_template method."""
        template_data = {"name": "New Template", "description": "Test template"}
        self.mixin.jira.post.return_value = {"id": "456", "success": True}
        result = self.mixin.create_project_form_template("PROJ", template_data)
        self.mixin.jira.post.assert_called_with("project/PROJ/form", json=template_data)
        self.assertTrue(result["success"])

    def test_update_project_form_template(self):
        """Test update_project_form_template method."""
        template_data = {"name": "Updated Template"}
        self.mixin.jira.put.return_value = {"id": "123", "success": True}
        result = self.mixin.update_project_form_template("PROJ", "123", template_data)
        self.mixin.jira.put.assert_called_with(
            "project/PROJ/form/123", json=template_data
        )
        self.assertTrue(result["success"])

    def test_delete_project_form_template(self):
        """Test delete_project_form_template method."""
        self.mixin.jira.delete.return_value = {"success": True}
        result = self.mixin.delete_project_form_template("PROJ", "123")
        self.mixin.jira.delete.assert_called_with("project/PROJ/form/123")
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
