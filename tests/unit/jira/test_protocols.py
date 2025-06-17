"""Tests for Jira protocol definitions."""

import inspect
from typing import Any, Protocol, get_type_hints

import pytest

from mcp_atlassian.jira.protocols import (
    AttachmentsOperationsProto,
    EpicOperationsProto,
    FieldsOperationsProto,
    IssueOperationsProto,
    SearchOperationsProto,
    UsersOperationsProto,
)
from mcp_atlassian.models.jira import JiraIssue
from mcp_atlassian.models.jira.search import JiraSearchResult


class TestProtocolDefinitions:
    """Tests for protocol definition compliance."""

    @pytest.mark.parametrize(
        "protocol_class",
        [
            AttachmentsOperationsProto,
            IssueOperationsProto,
            SearchOperationsProto,
            EpicOperationsProto,
            FieldsOperationsProto,
            UsersOperationsProto,
        ],
    )
    def test_protocol_inheritance(self, protocol_class):
        """Test that all protocols inherit from Protocol."""
        assert issubclass(protocol_class, Protocol)

    @pytest.mark.parametrize(
        "protocol_class",
        [
            AttachmentsOperationsProto,
            IssueOperationsProto,
            SearchOperationsProto,
            EpicOperationsProto,
            FieldsOperationsProto,
            UsersOperationsProto,
        ],
    )
    def test_protocol_cannot_be_instantiated(self, protocol_class):
        """Test that protocols cannot be instantiated directly."""
        with pytest.raises(TypeError):
            protocol_class()


class TestMethodSignatures:
    """Tests for protocol method signatures."""

    def test_attachments_upload_method(self):
        """Test upload_attachments method signature."""
        method = AttachmentsOperationsProto.upload_attachments
        type_hints = get_type_hints(method)

        assert type_hints["issue_key"] is str
        assert type_hints["file_paths"] == list[str]
        assert type_hints["return"] == dict[str, Any]
        assert method.__isabstractmethod__ is True

    def test_issue_get_method(self):
        """Test get_issue method signature and defaults."""
        method = IssueOperationsProto.get_issue
        sig = inspect.signature(method)
        type_hints = get_type_hints(method)

        # Type hints
        assert type_hints["issue_key"] is str
        assert type_hints["return"] is JiraIssue

        # Default parameters
        assert sig.parameters["expand"].default is None
        assert sig.parameters["comment_limit"].default == 10
        assert sig.parameters["update_history"].default is True

        expected_fields = (
            "summary,description,status,assignee,reporter,labels,"
            "priority,created,updated,issuetype"
        )
        assert sig.parameters["fields"].default == expected_fields

    def test_search_issues_method(self):
        """Test search_issues method signature and defaults."""
        method = SearchOperationsProto.search_issues
        sig = inspect.signature(method)
        type_hints = get_type_hints(method)

        # Type hints
        assert type_hints["jql"] is str
        assert type_hints["return"] is JiraSearchResult

        # Default parameters
        assert sig.parameters["start"].default == 0
        assert sig.parameters["limit"].default == 50
        assert sig.parameters["expand"].default is None

    @pytest.mark.parametrize(
        "method_name,expected_count",
        [
            ("update_epic_fields", 1),
            ("prepare_epic_fields", 1),
            ("_try_discover_fields_from_existing_epic", 1),
        ],
    )
    def test_epic_methods(self, method_name, expected_count):
        """Test EpicOperationsProto method signatures."""
        method = getattr(EpicOperationsProto, method_name)
        assert method.__isabstractmethod__ is True

        if method_name == "update_epic_fields":
            type_hints = get_type_hints(method)
            assert type_hints["issue_key"] is str
            assert type_hints["kwargs"] == dict[str, Any]
            assert type_hints["return"] is JiraIssue

    def test_fields_methods(self):
        """Test FieldsOperationsProto method signatures."""
        # Test _generate_field_map
        method = FieldsOperationsProto._generate_field_map
        sig = inspect.signature(method)
        type_hints = get_type_hints(method)

        assert sig.parameters["force_regenerate"].default is False
        assert type_hints["return"] == dict[str, str]

        # Test get_field_by_id
        method = FieldsOperationsProto.get_field_by_id
        type_hints = get_type_hints(method)
        assert type_hints["field_id"] is str
        assert type_hints["return"] == dict[str, Any] | None

    def test_users_method(self):
        """Test UsersOperationsProto method signature."""
        method = UsersOperationsProto._get_account_id
        type_hints = get_type_hints(method)

        assert type_hints["assignee"] is str
        assert type_hints["return"] is str
        assert method.__isabstractmethod__ is True


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


class TestAbstractMethodCounts:
    """Tests for verifying abstract method counts in protocols."""

    @pytest.mark.parametrize(
        "protocol_class,expected_count",
        [
            (AttachmentsOperationsProto, 1),  # upload_attachments
            (IssueOperationsProto, 1),  # get_issue
            (SearchOperationsProto, 1),  # search_issues
            (
                EpicOperationsProto,
                3,
            ),  # update_epic_fields, prepare_epic_fields, _try_discover_fields_from_existing_epic
            (
                FieldsOperationsProto,
                3,
            ),  # _generate_field_map, get_field_by_id, get_field_ids_to_epic
            (UsersOperationsProto, 1),  # _get_account_id
        ],
    )
    def test_abstract_method_count(self, protocol_class, expected_count):
        """Test counting abstract methods in each protocol."""
        abstract_methods = [
            attr
            for attr in dir(protocol_class)
            if callable(getattr(protocol_class, attr, None))
            and not attr.startswith("__")
            and hasattr(getattr(protocol_class, attr), "__isabstractmethod__")
            and getattr(protocol_class, attr).__isabstractmethod__
        ]
        assert len(abstract_methods) == expected_count
