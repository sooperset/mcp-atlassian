"""Tests for Jira protocol definitions."""

import inspect
from abc import ABC, abstractmethod
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


class TestAttachmentsOperationsProto:
    """Tests for AttachmentsOperationsProto protocol."""

    def test_protocol_is_defined(self):
        """Test that AttachmentsOperationsProto is properly defined as a Protocol."""
        assert issubclass(AttachmentsOperationsProto, Protocol)

    def test_upload_attachments_method_signature(self):
        """Test upload_attachments method signature compliance."""
        method = AttachmentsOperationsProto.upload_attachments
        type_hints = get_type_hints(method)

        assert "issue_key" in type_hints
        assert type_hints["issue_key"] is str
        assert "file_paths" in type_hints
        assert type_hints["file_paths"] == list[str]
        assert type_hints["return"] == dict[str, Any]

    def test_upload_attachments_is_abstract(self):
        """Test that upload_attachments is an abstract method."""
        method = AttachmentsOperationsProto.upload_attachments
        assert hasattr(method, "__isabstractmethod__")
        assert method.__isabstractmethod__ is True

    def test_compliant_implementation_structure(self):
        """Test that a compliant implementation has proper structure."""

        class CompliantAttachments:
            def upload_attachments(
                self, issue_key: str, file_paths: list[str]
            ) -> dict[str, Any]:
                return {"status": "success", "uploaded": len(file_paths)}

        instance = CompliantAttachments()
        assert hasattr(instance, "upload_attachments")
        assert callable(instance.upload_attachments)

        # Test method signature
        method = instance.upload_attachments
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert "issue_key" in params
        assert "file_paths" in params

    def test_non_compliant_implementation_missing_method(self):
        """Test that non-compliant implementation lacks required methods."""

        class NonCompliantAttachments:
            pass

        instance = NonCompliantAttachments()
        assert not hasattr(instance, "upload_attachments")

    def test_method_parameter_validation(self):
        """Test method parameter validation."""
        method = AttachmentsOperationsProto.upload_attachments
        sig = inspect.signature(method)

        # Check required parameters exist
        assert "issue_key" in sig.parameters
        assert "file_paths" in sig.parameters

        # Check parameter types
        type_hints = get_type_hints(method)
        assert type_hints["issue_key"] is str
        assert type_hints["file_paths"] == list[str]


class TestIssueOperationsProto:
    """Tests for IssueOperationsProto protocol."""

    def test_protocol_is_defined(self):
        """Test that IssueOperationsProto is properly defined as a Protocol."""
        assert issubclass(IssueOperationsProto, Protocol)

    def test_get_issue_method_signature(self):
        """Test get_issue method signature compliance."""
        method = IssueOperationsProto.get_issue
        type_hints = get_type_hints(method)

        assert "issue_key" in type_hints
        assert type_hints["issue_key"] is str
        assert type_hints["return"] is JiraIssue

    def test_get_issue_default_parameters(self):
        """Test get_issue method default parameters."""
        method = IssueOperationsProto.get_issue
        sig = inspect.signature(method)

        # Check parameter defaults
        assert sig.parameters["expand"].default is None
        assert sig.parameters["comment_limit"].default == 10
        assert sig.parameters["update_history"].default is True

        # Check fields default value
        expected_fields = (
            "summary,description,status,assignee,reporter,labels,"
            "priority,created,updated,issuetype"
        )
        assert sig.parameters["fields"].default == expected_fields

    def test_get_issue_is_abstract(self):
        """Test that get_issue is an abstract method."""
        method = IssueOperationsProto.get_issue
        assert hasattr(method, "__isabstractmethod__")
        assert method.__isabstractmethod__ is True

    def test_compliant_implementation_structure(self):
        """Test that a compliant implementation has proper structure."""

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
        assert callable(instance.get_issue)

    def test_non_compliant_implementation_missing_method(self):
        """Test that non-compliant implementation lacks required methods."""

        class NonCompliantIssues:
            pass

        instance = NonCompliantIssues()
        assert not hasattr(instance, "get_issue")


class TestSearchOperationsProto:
    """Tests for SearchOperationsProto protocol."""

    def test_protocol_is_defined(self):
        """Test that SearchOperationsProto is properly defined as a Protocol."""
        assert issubclass(SearchOperationsProto, Protocol)

    def test_search_issues_method_signature(self):
        """Test search_issues method signature compliance."""
        method = SearchOperationsProto.search_issues
        type_hints = get_type_hints(method)

        assert "jql" in type_hints
        assert type_hints["jql"] is str
        assert type_hints["return"] is JiraSearchResult

    def test_search_issues_default_parameters(self):
        """Test search_issues method default parameters."""
        method = SearchOperationsProto.search_issues
        sig = inspect.signature(method)

        # Check parameter defaults
        assert sig.parameters["start"].default == 0
        assert sig.parameters["limit"].default == 50
        assert sig.parameters["expand"].default is None
        assert sig.parameters["projects_filter"].default is None

        # Check fields default value
        expected_fields = (
            "summary,description,status,assignee,reporter,labels,"
            "priority,created,updated,issuetype"
        )
        assert sig.parameters["fields"].default == expected_fields

    def test_search_issues_is_abstract(self):
        """Test that search_issues is an abstract method."""
        method = SearchOperationsProto.search_issues
        assert hasattr(method, "__isabstractmethod__")
        assert method.__isabstractmethod__ is True

    def test_compliant_implementation_structure(self):
        """Test that a compliant implementation has proper structure."""

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
        assert hasattr(instance, "search_issues")
        assert callable(instance.search_issues)

    def test_non_compliant_implementation_missing_method(self):
        """Test that non-compliant implementation lacks required methods."""

        class NonCompliantSearch:
            pass

        instance = NonCompliantSearch()
        assert not hasattr(instance, "search_issues")


class TestEpicOperationsProto:
    """Tests for EpicOperationsProto protocol."""

    def test_protocol_is_defined(self):
        """Test that EpicOperationsProto is properly defined as a Protocol."""
        assert issubclass(EpicOperationsProto, Protocol)

    def test_update_epic_fields_method_signature(self):
        """Test update_epic_fields method signature compliance."""
        method = EpicOperationsProto.update_epic_fields
        type_hints = get_type_hints(method)

        assert "issue_key" in type_hints
        assert type_hints["issue_key"] is str
        assert "kwargs" in type_hints
        assert type_hints["kwargs"] == dict[str, Any]
        assert type_hints["return"] is JiraIssue

    def test_prepare_epic_fields_method_signature(self):
        """Test prepare_epic_fields method signature compliance."""
        method = EpicOperationsProto.prepare_epic_fields
        type_hints = get_type_hints(method)

        assert "fields" in type_hints
        assert type_hints["fields"] == dict[str, Any]
        assert "summary" in type_hints
        assert type_hints["summary"] is str
        assert "kwargs" in type_hints
        assert type_hints["kwargs"] == dict[str, Any]
        assert type_hints["return"] is type(None)

    def test_try_discover_fields_from_existing_epic_method_signature(self):
        """Test _try_discover_fields_from_existing_epic method signature compliance."""
        method = EpicOperationsProto._try_discover_fields_from_existing_epic
        type_hints = get_type_hints(method)

        assert "field_ids" in type_hints
        assert type_hints["field_ids"] == dict[str, str]
        assert type_hints["return"] is type(None)

    def test_all_methods_are_abstract(self):
        """Test that all EpicOperationsProto methods are abstract."""
        methods = [
            EpicOperationsProto.update_epic_fields,
            EpicOperationsProto.prepare_epic_fields,
            EpicOperationsProto._try_discover_fields_from_existing_epic,
        ]

        for method in methods:
            assert hasattr(method, "__isabstractmethod__")
            assert method.__isabstractmethod__ is True

    def test_compliant_implementation_structure(self):
        """Test that a compliant implementation has proper structure."""

        class CompliantEpic:
            def update_epic_fields(
                self, issue_key: str, kwargs: dict[str, Any]
            ) -> JiraIssue:
                return JiraIssue(id="123", key=issue_key, summary="Epic")

            def prepare_epic_fields(
                self, fields: dict[str, Any], summary: str, kwargs: dict[str, Any]
            ) -> None:
                fields.update(kwargs)

            def _try_discover_fields_from_existing_epic(
                self, field_ids: dict[str, str]
            ) -> None:
                field_ids.update({"epic_name": "customfield_10011"})

        instance = CompliantEpic()
        assert hasattr(instance, "update_epic_fields")
        assert hasattr(instance, "prepare_epic_fields")
        assert hasattr(instance, "_try_discover_fields_from_existing_epic")

        # Test all methods are callable
        assert callable(instance.update_epic_fields)
        assert callable(instance.prepare_epic_fields)
        assert callable(instance._try_discover_fields_from_existing_epic)

    def test_non_compliant_implementation_missing_method(self):
        """Test that non-compliant implementation lacks required methods."""

        class IncompleteEpic:
            def update_epic_fields(
                self, issue_key: str, kwargs: dict[str, Any]
            ) -> JiraIssue:
                return JiraIssue(id="123", key=issue_key, summary="Epic")

            # Missing other required methods

        instance = IncompleteEpic()
        assert hasattr(instance, "update_epic_fields")
        assert not hasattr(instance, "prepare_epic_fields")
        assert not hasattr(instance, "_try_discover_fields_from_existing_epic")


class TestFieldsOperationsProto:
    """Tests for FieldsOperationsProto protocol."""

    def test_protocol_is_defined(self):
        """Test that FieldsOperationsProto is properly defined as a Protocol."""
        assert issubclass(FieldsOperationsProto, Protocol)

    def test_generate_field_map_method_signature(self):
        """Test _generate_field_map method signature compliance."""
        method = FieldsOperationsProto._generate_field_map
        type_hints = get_type_hints(method)

        assert "force_regenerate" in type_hints
        assert type_hints["force_regenerate"] is bool
        assert type_hints["return"] == dict[str, str]

    def test_generate_field_map_default_parameters(self):
        """Test _generate_field_map method default parameters."""
        method = FieldsOperationsProto._generate_field_map
        sig = inspect.signature(method)

        assert sig.parameters["force_regenerate"].default is False

    def test_get_field_by_id_method_signature(self):
        """Test get_field_by_id method signature compliance."""
        method = FieldsOperationsProto.get_field_by_id
        type_hints = get_type_hints(method)

        assert "field_id" in type_hints
        assert type_hints["field_id"] is str
        assert "refresh" in type_hints
        assert type_hints["refresh"] is bool
        assert type_hints["return"] == dict[str, Any] | None

    def test_get_field_ids_to_epic_method_signature(self):
        """Test get_field_ids_to_epic method signature compliance."""
        method = FieldsOperationsProto.get_field_ids_to_epic
        type_hints = get_type_hints(method)

        assert type_hints["return"] == dict[str, str]

    def test_all_methods_are_abstract(self):
        """Test that all FieldsOperationsProto methods are abstract."""
        methods = [
            FieldsOperationsProto._generate_field_map,
            FieldsOperationsProto.get_field_by_id,
            FieldsOperationsProto.get_field_ids_to_epic,
        ]

        for method in methods:
            assert hasattr(method, "__isabstractmethod__")
            assert method.__isabstractmethod__ is True

    def test_compliant_implementation_structure(self):
        """Test that a compliant implementation has proper structure."""

        class CompliantFields:
            def _generate_field_map(
                self, *, force_regenerate: bool = False
            ) -> dict[str, str]:
                return {"summary": "summary", "description": "description"}

            def get_field_by_id(
                self, field_id: str, *, refresh: bool = False
            ) -> dict[str, Any] | None:
                return {"id": field_id, "name": "Field Name"}

            def get_field_ids_to_epic(self) -> dict[str, str]:
                return {
                    "epic_link": "customfield_10014",
                    "epic_name": "customfield_10011",
                }

        instance = CompliantFields()
        assert hasattr(instance, "_generate_field_map")
        assert hasattr(instance, "get_field_by_id")
        assert hasattr(instance, "get_field_ids_to_epic")

        # Test all methods are callable
        assert callable(instance._generate_field_map)
        assert callable(instance.get_field_by_id)
        assert callable(instance.get_field_ids_to_epic)

    def test_non_compliant_implementation_missing_method(self):
        """Test that non-compliant implementation lacks required methods."""

        class IncompleteFields:
            def _generate_field_map(
                self, *, force_regenerate: bool = False
            ) -> dict[str, str]:
                return {}

            # Missing other required methods

        instance = IncompleteFields()
        assert hasattr(instance, "_generate_field_map")
        assert not hasattr(instance, "get_field_by_id")
        assert not hasattr(instance, "get_field_ids_to_epic")


class TestUsersOperationsProto:
    """Tests for UsersOperationsProto protocol."""

    def test_protocol_is_defined(self):
        """Test that UsersOperationsProto is properly defined as a Protocol."""
        assert issubclass(UsersOperationsProto, Protocol)

    def test_protocol_is_runtime_checkable(self):
        """Test that UsersOperationsProto is decorated with @runtime_checkable."""
        # Check if the protocol is runtime checkable by looking for the attribute
        assert getattr(UsersOperationsProto, "_is_runtime_protocol", False)

    def test_get_account_id_method_signature(self):
        """Test _get_account_id method signature compliance."""
        method = UsersOperationsProto._get_account_id
        type_hints = get_type_hints(method)

        assert "assignee" in type_hints
        assert type_hints["assignee"] is str
        assert type_hints["return"] is str

    def test_get_account_id_is_abstract(self):
        """Test that _get_account_id is an abstract method."""
        method = UsersOperationsProto._get_account_id
        assert hasattr(method, "__isabstractmethod__")
        assert method.__isabstractmethod__ is True

    def test_runtime_checkable_compliant_implementation(self):
        """Test runtime checking with compliant implementation."""

        class CompliantUsers:
            def _get_account_id(self, assignee: str) -> str:
                return f"account-id-for-{assignee}"

        instance = CompliantUsers()
        assert isinstance(instance, UsersOperationsProto)

    def test_runtime_checkable_non_compliant_implementation(self):
        """Test runtime checking with non-compliant implementation."""

        class NonCompliantUsers:
            pass

        instance = NonCompliantUsers()
        assert not isinstance(instance, UsersOperationsProto)

    def test_runtime_checkable_wrong_signature(self):
        """Test runtime checking with wrong method signature."""

        class WrongSignatureUsers:
            def _get_account_id(self) -> str:
                return "account-id"

        instance = WrongSignatureUsers()
        # Runtime checkable only checks method existence, not signature
        assert isinstance(instance, UsersOperationsProto)


class TestProtocolInheritancePatterns:
    """Tests for protocol inheritance patterns and relationships."""

    def test_protocols_inherit_from_protocol(self):
        """Test that all protocols properly inherit from Protocol."""
        protocols = [
            AttachmentsOperationsProto,
            IssueOperationsProto,
            SearchOperationsProto,
            EpicOperationsProto,
            FieldsOperationsProto,
            UsersOperationsProto,
        ]

        for protocol in protocols:
            assert issubclass(protocol, Protocol)

    def test_protocols_are_not_concrete_classes(self):
        """Test that protocols cannot be instantiated directly."""
        protocols = [
            AttachmentsOperationsProto,
            IssueOperationsProto,
            SearchOperationsProto,
            EpicOperationsProto,
            FieldsOperationsProto,
            UsersOperationsProto,
        ]

        for protocol in protocols:
            with pytest.raises(TypeError):
                protocol()

    def test_runtime_checkable_protocol_implementation(self):
        """Test that a class can implement the runtime checkable protocol."""

        class MultiProtocolImplementation:
            def _get_account_id(self, assignee: str) -> str:
                return f"account-{assignee}"

        instance = MultiProtocolImplementation()
        # Only UsersOperationsProto is runtime checkable
        assert isinstance(instance, UsersOperationsProto)

    def test_protocol_method_discovery(self):
        """Test discovery of protocol methods using inspection."""
        # Test AttachmentsOperationsProto methods
        methods = [
            attr
            for attr in dir(AttachmentsOperationsProto)
            if callable(getattr(AttachmentsOperationsProto, attr, None))
            and not attr.startswith("__")
        ]

        assert "upload_attachments" in methods

    def test_protocol_abstract_method_count(self):
        """Test counting abstract methods in each protocol."""
        protocol_method_counts = {
            AttachmentsOperationsProto: 1,  # upload_attachments
            IssueOperationsProto: 1,  # get_issue
            SearchOperationsProto: 1,  # search_issues
            EpicOperationsProto: 3,  # update_epic_fields, prepare_epic_fields,
            # _try_discover_fields_from_existing_epic
            FieldsOperationsProto: 3,  # _generate_field_map, get_field_by_id,
            # get_field_ids_to_epic
            UsersOperationsProto: 1,  # _get_account_id
        }

        for protocol, expected_count in protocol_method_counts.items():
            abstract_methods = [
                attr
                for attr in dir(protocol)
                if callable(getattr(protocol, attr, None))
                and not attr.startswith("__")
                and hasattr(getattr(protocol, attr), "__isabstractmethod__")
                and getattr(protocol, attr).__isabstractmethod__
            ]
            assert len(abstract_methods) == expected_count


class TestProtocolContractEnforcement:
    """Tests for protocol contract enforcement and type safety."""

    def test_abstract_method_enforcement_with_abc(self):
        """Test that abstract methods are enforced when mixed with ABC."""

        class AbstractImplementation(ABC):
            @abstractmethod
            def upload_attachments(
                self, issue_key: str, file_paths: list[str]
            ) -> dict[str, Any]:
                pass

        # Should not be able to instantiate without implementing abstract methods
        with pytest.raises(TypeError):
            AbstractImplementation()

    def test_method_signature_validation_helper(self):
        """Test helper function for validating method signatures match protocol."""

        def validate_method_signature(protocol_class, method_name: str, implementation):
            """Validate that implementation method signature matches protocol."""
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

    def test_type_hint_compliance_validation(self):
        """Test type hint compliance between protocol and implementation."""

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

    def test_protocol_method_introspection(self):
        """Test introspection capabilities for protocol methods."""

        # Test that we can discover all abstract methods in a protocol
        def get_abstract_methods(protocol_class):
            """Get all abstract methods from a protocol."""
            methods = []
            for attr_name in dir(protocol_class):
                if not attr_name.startswith("__"):
                    attr = getattr(protocol_class, attr_name, None)
                    if (
                        callable(attr)
                        and hasattr(attr, "__isabstractmethod__")
                        and attr.__isabstractmethod__
                    ):
                        methods.append(attr_name)
            return methods

        # Test each protocol
        attachments_methods = get_abstract_methods(AttachmentsOperationsProto)
        assert "upload_attachments" in attachments_methods

        issue_methods = get_abstract_methods(IssueOperationsProto)
        assert "get_issue" in issue_methods

        search_methods = get_abstract_methods(SearchOperationsProto)
        assert "search_issues" in search_methods

    def test_structural_typing_validation(self):
        """Test structural typing validation for protocol compliance."""

        def check_structural_compliance(instance, protocol_class):
            """Check if an instance structurally complies with a protocol."""
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
