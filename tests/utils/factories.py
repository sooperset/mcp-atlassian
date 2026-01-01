"""Test data factories for creating consistent test objects."""

from typing import Any


class JiraIssueFactory:
    """Factory for creating Jira issue test data."""

    @staticmethod
    def create(key: str = "TEST-123", **overrides) -> dict[str, Any]:
        """Create a Jira issue with default values."""
        defaults = {
            "id": "12345",
            "key": key,
            "self": f"https://test.atlassian.net/rest/api/3/issue/{key}",
            "fields": {
                "summary": "Test Issue Summary",
                "description": "Test issue description",
                "status": {"name": "Open", "id": "1", "statusCategory": {"key": "new"}},
                "issuetype": {"name": "Task", "id": "10001"},
                "priority": {"name": "Medium", "id": "3"},
                "assignee": {
                    "displayName": "Test User",
                    "emailAddress": "test@example.com",
                },
                "created": "2023-01-01T12:00:00.000+0000",
                "updated": "2023-01-01T12:00:00.000+0000",
            },
        }
        return deep_merge(defaults, overrides)

    @staticmethod
    def create_minimal(key: str = "TEST-123") -> dict[str, Any]:
        """Create minimal Jira issue for basic tests."""
        return {
            "key": key,
            "fields": {"summary": "Test Issue", "status": {"name": "Open"}},
        }


class ConfluencePageFactory:
    """Factory for creating Confluence page test data."""

    @staticmethod
    def create(page_id: str = "123456", **overrides) -> dict[str, Any]:
        """Create a Confluence page with default values."""
        defaults = {
            "id": page_id,
            "title": "Test Page",
            "type": "page",
            "status": "current",
            "space": {"key": "TEST", "name": "Test Space"},
            "body": {
                "storage": {"value": "<p>Test content</p>", "representation": "storage"}
            },
            "version": {"number": 1},
            "_links": {
                "webui": f"/spaces/TEST/pages/{page_id}",
                "self": f"https://test.atlassian.net/wiki/rest/api/content/{page_id}",
            },
        }
        return deep_merge(defaults, overrides)


class AuthConfigFactory:
    """Factory for authentication configuration objects."""

    @staticmethod
    def create_oauth_config(**overrides) -> dict[str, str]:
        """Create OAuth configuration."""
        defaults = {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "redirect_uri": "http://localhost:8080/callback",
            "scope": "read:jira-work write:jira-work",
            "cloud_id": "test-cloud-id",
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
        }
        return {**defaults, **overrides}

    @staticmethod
    def create_basic_auth_config(**overrides) -> dict[str, str]:
        """Create basic auth configuration."""
        defaults = {
            "url": "https://test.atlassian.net",
            "username": "test@example.com",
            "api_token": "test-api-token",
        }
        return {**defaults, **overrides}


class ErrorResponseFactory:
    """Factory for creating error response test data."""

    @staticmethod
    def create_api_error(
        status_code: int = 400, message: str = "Bad Request"
    ) -> dict[str, Any]:
        """Create API error response."""
        return {"errorMessages": [message], "errors": {}, "status": status_code}

    @staticmethod
    def create_auth_error() -> dict[str, Any]:
        """Create authentication error response."""
        return {"errorMessages": ["Authentication failed"], "status": 401}

    @staticmethod
    def create_form_not_found_error() -> dict[str, Any]:
        """Create a form not found error response."""
        return ErrorResponseFactory.create_api_error(
            status_code=404, message="Form not found"
        )

    @staticmethod
    def create_form_closed_error() -> dict[str, Any]:
        """Create a form already closed error response."""
        return ErrorResponseFactory.create_api_error(
            status_code=400, message="Form is already closed"
        )

    @staticmethod
    def create_field_validation_error() -> dict[str, Any]:
        """Create a field validation error response."""
        return ErrorResponseFactory.create_api_error(
            status_code=400, message="Field validation failed"
        )


class ProFormaFormFactory:
    """Factory for creating ProForma form test data."""

    @staticmethod
    def create(form_id: str = "12345", **overrides) -> dict[str, Any]:
        """Create a ProForma form with default values."""
        defaults = {
            "id": form_id,
            "name": "Test Form",
            "version": 1,
            "state": "ACTIVE",
            "description": "Test form description",
            "settings": {
                "allowAnonymousSubmissions": False,
                "allowMultipleSubmissions": True,
                "submitButtonText": "Submit",
            },
            "fields": [
                {
                    "id": "field1",
                    "type": "SHORT_TEXT",
                    "label": "Test Field",
                    "required": True,
                    "value": None,
                    "options": [],
                    "description": "Test field description",
                },
            ],
            "issueKey": "TEST-123",
            "_links": {
                "self": f"https://test.atlassian.net/rest/atlassian-forms/1.0/form/{form_id}",
                "webui": f"https://test.atlassian.net/browse/TEST-123?form={form_id}",
            },
        }
        return deep_merge(defaults, overrides)

    @staticmethod
    def create_field(field_id: str = "field1", **overrides) -> dict[str, Any]:
        """Create a ProForma form field with default values."""
        defaults = {
            "id": field_id,
            "type": "SHORT_TEXT",
            "label": "Test Field",
            "required": True,
            "value": None,
            "options": [],
            "description": "Test field description",
        }
        return deep_merge(defaults, overrides)

    @staticmethod
    def create_minimal(form_id: str = "12345") -> dict[str, Any]:
        """Create minimal ProForma form for basic tests."""
        return {
            "id": form_id,
            "name": "Test Form",
            "state": "ACTIVE",
            "fields": [],
        }

    @staticmethod
    def create_closed_form(form_id: str = "12345", **overrides) -> dict[str, Any]:
        """Create a closed ProForma form."""
        return ProFormaFormFactory.create(form_id, state="CLOSED", **overrides)

    @staticmethod
    def create_with_multiple_fields(
        form_id: str = "12345", **overrides
    ) -> dict[str, Any]:
        """Create a ProForma form with multiple field types."""
        fields = [
            {
                "id": "text_field",
                "type": "SHORT_TEXT",
                "label": "Text Input",
                "required": True,
                "value": "Default text",
                "description": "Enter text here",
            },
            {
                "id": "select_field",
                "type": "SELECT",
                "label": "Select Option",
                "required": False,
                "value": "option1",
                "options": ["option1", "option2", "option3"],
                "description": "Select an option",
            },
            {
                "id": "checkbox_field",
                "type": "CHECKBOX",
                "label": "Checkbox Field",
                "required": False,
                "value": True,
                "description": "Check if applicable",
            },
        ]
        return ProFormaFormFactory.create(form_id, fields=fields, **overrides)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
