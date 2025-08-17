"""Tests for Jira protocol definitions."""

import inspect
from typing import Any, get_type_hints

from mcp_atlassian.jira.protocols import (
    AttachmentsOperationsProto,
    UsersOperationsProto,
)
from mcp_atlassian.models.jira import JiraIssue
from mcp_atlassian.models.jira.search import JiraSearchResult


class TestProtocolCompliance:
    """Tests for protocol compliance checking."""

    def test_compliant_attachments_implementation(self):
        """Test compliant attachments implementation."""

        class CompliantAttachments:
            def upload_attachments(
                self, issue_key: str, file_paths: list[str]
            ) -> dict[str, Any]:
                return {"uploaded": len(file_paths)}

        instance = CompliantAttachments()
        assert hasattr(instance, "upload_attachments")
        assert callable(instance.upload_attachments)

    def test_compliant_issue_implementation(self):
        """Test compliant issue implementation."""

        class CompliantIssues:
            def get_issue(
                self,
                issue_key: str,
                expand: str | None = None,
                comment_limit: int | str | None = 10,
                fields: str | list[str] | tuple[str, ...] | set[str] | None = (
                    "summary,description,status,assignee,reporter,labels,"
                    "priority,created,updated,issuetype"
                ),
                properties: str | list[str] | None = None,
                *,
                update_history: bool = True,
            ) -> JiraIssue:
                return JiraIssue(id="123", key=issue_key, summary="Test Issue")

        instance = CompliantIssues()
        assert hasattr(instance, "get_issue")
        result = instance.get_issue("TEST-1")
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-1"

    def test_compliant_search_implementation(self):
        """Test compliant search implementation."""

        class CompliantSearch:
            def search_issues(
                self,
                jql: str,
                fields: str | list[str] | tuple[str, ...] | set[str] | None = (
                    "summary,description,status,assignee,reporter,labels,"
                    "priority,created,updated,issuetype"
                ),
                start: int = 0,
                limit: int = 50,
                expand: str | None = None,
                projects_filter: str | None = None,
            ) -> JiraSearchResult:
                return JiraSearchResult(
                    total=0, start_at=start, max_results=limit, issues=[]
                )

        instance = CompliantSearch()
        result = instance.search_issues("project = TEST")
        assert isinstance(result, JiraSearchResult)

    def test_runtime_checkable_users_protocol(self):
        """Test runtime checking for UsersOperationsProto."""

        class CompliantUsers:
            def _get_account_id(self, assignee: str) -> str:
                return f"account-id-for-{assignee}"

        class NonCompliantUsers:
            pass

        compliant_instance = CompliantUsers()
        non_compliant_instance = NonCompliantUsers()

        # Runtime checkable only checks method existence
        assert isinstance(compliant_instance, UsersOperationsProto)
        assert not isinstance(non_compliant_instance, UsersOperationsProto)


class TestProtocolContractValidation:
    """Tests for validating protocol contract compliance."""

    def test_method_signature_validation(self):
        """Test method signature validation helper."""

        def validate_method_signature(protocol_class, method_name: str, implementation):
            """Validate implementation method signature matches protocol."""
            protocol_method = getattr(protocol_class, method_name)
            impl_method = getattr(implementation, method_name)

            protocol_sig = inspect.signature(protocol_method)
            impl_sig = inspect.signature(impl_method)

            # Compare parameter names (excluding 'self')
            protocol_params = [p for p in protocol_sig.parameters.keys() if p != "self"]
            impl_params = [p for p in impl_sig.parameters.keys() if p != "self"]

            return protocol_params == impl_params

        class TestImplementation:
            def upload_attachments(
                self, issue_key: str, file_paths: list[str]
            ) -> dict[str, Any]:
                return {}

        impl = TestImplementation()
        assert validate_method_signature(
            AttachmentsOperationsProto, "upload_attachments", impl
        )

    def test_type_hint_validation(self):
        """Test type hint compliance validation."""

        def validate_type_hints(protocol_class, method_name: str, implementation):
            """Validate type hints match between protocol and implementation."""
            protocol_method = getattr(protocol_class, method_name)
            impl_method = getattr(implementation, method_name)

            protocol_hints = get_type_hints(protocol_method)
            impl_hints = get_type_hints(impl_method)

            # Check return type
            return protocol_hints.get("return") == impl_hints.get("return")

        class TypeCompliantImplementation:
            def upload_attachments(
                self, issue_key: str, file_paths: list[str]
            ) -> dict[str, Any]:
                return {}

        impl = TypeCompliantImplementation()
        assert validate_type_hints(
            AttachmentsOperationsProto, "upload_attachments", impl
        )

    def test_structural_compliance_check(self):
        """Test structural typing validation."""

        def check_structural_compliance(instance, protocol_class):
            """Check if instance structurally complies with protocol."""
            abstract_methods = []
            for attr_name in dir(protocol_class):
                if not attr_name.startswith("__"):
                    attr = getattr(protocol_class, attr_name, None)
                    if (
                        callable(attr)
                        and hasattr(attr, "__isabstractmethod__")
                        and attr.__isabstractmethod__
                    ):
                        abstract_methods.append(attr_name)

            # Check if instance has all required methods
            for method_name in abstract_methods:
                if not hasattr(instance, method_name):
                    return False
                if not callable(getattr(instance, method_name)):
                    return False
            return True

        class CompliantImplementation:
            def upload_attachments(
                self, issue_key: str, file_paths: list[str]
            ) -> dict[str, Any]:
                return {}

        class NonCompliantImplementation:
            def some_other_method(self):
                pass

        compliant = CompliantImplementation()
        non_compliant = NonCompliantImplementation()

        assert check_structural_compliance(compliant, AttachmentsOperationsProto)
        assert not check_structural_compliance(
            non_compliant, AttachmentsOperationsProto
        )
