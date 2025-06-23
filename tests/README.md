# MCP Atlassian Test Fixtures Documentation

This document describes the enhanced test fixture system implemented for the MCP Atlassian project.

## Overview

The test fixture system has been significantly improved to provide:

- **Session-scoped fixtures** for expensive operations
- **Factory-based fixtures** for customizable test data
- **Better fixture composition** and reusability
- **Backward compatibility** with existing tests
- **Integration with test utilities** framework

## Architecture

```
tests/
├── conftest.py                 # Root fixtures with session-scoped data
├── unit/
│   ├── jira/conftest.py       # Jira-specific fixtures
│   ├── confluence/conftest.py # Confluence-specific fixtures
│   └── models/conftest.py     # Model testing fixtures
├── utils/                     # Test utilities framework
│   ├── factories.py          # Data factories
│   ├── mocks.py              # Mock utilities
│   ├── base.py               # Base test classes
│   └── assertions.py         # Custom assertions
└── fixtures/                  # Legacy mock data
    ├── jira_mocks.py         # Static Jira mock data
    └── confluence_mocks.py   # Static Confluence mock data
```

## Key Features

### 1. Session-Scoped Fixtures

These fixtures are computed once per test session to improve performance:

- `session_auth_configs`: Authentication configuration templates
- `session_mock_data`: Mock data templates for API responses
- `session_jira_field_definitions`: Jira field definitions
- `session_jira_projects`: Jira project data
- `session_confluence_spaces`: Confluence space definitions

```python
# Example usage
def test_with_session_data(session_jira_field_definitions):
    # Uses cached field definitions, computed once per session
    assert len(session_jira_field_definitions) > 0
```

### 2. Factory-Based Fixtures

These fixtures return factory functions for creating customizable test data:

- `make_jira_issue`: Create Jira issues with custom properties
- `make_confluence_page`: Create Confluence pages with custom properties
- `make_auth_config`: Create authentication configurations
- `make_api_error`: Create API error responses

```python
# Example usage
def test_custom_issue(make_jira_issue):
    issue = make_jira_issue(
        key="CUSTOM-123",
        fields={"priority": {"name": "High"}}
    )
    assert issue["key"] == "CUSTOM-123"
    assert issue["fields"]["priority"]["name"] == "High"
```

### 3. Environment Management

Enhanced environment fixtures for testing different authentication scenarios:

- `clean_environment`: No authentication variables
- `oauth_environment`: OAuth setup
- `basic_auth_environment`: Basic auth setup
- `parametrized_auth_env`: Parameterized auth testing

```python
# Example usage
@pytest.mark.parametrize("parametrized_auth_env",
                       ["oauth", "basic_auth"], indirect=True)
def test_auth_scenarios(parametrized_auth_env):
    # Test runs once for OAuth and once for basic auth
    pass
```

### 4. Enhanced Mock Clients

Improved mock clients with better integration:

- `mock_jira_client`: Pre-configured mock Jira client
- `mock_confluence_client`: Pre-configured mock Confluence client
- `enhanced_mock_jira_client`: Factory-integrated Jira client
- `enhanced_mock_confluence_client`: Factory-integrated Confluence client

### 5. Specialized Data Fixtures

Domain-specific fixtures for complex testing scenarios:

- `make_jira_issue_with_worklog`: Issues with worklog data
- `make_jira_search_results`: JQL search results
- `make_confluence_page_with_content`: Pages with rich content
- `make_confluence_search_results`: CQL search results

## Migration Guide

### For New Tests

Use the enhanced factory-based fixtures:

```python
def test_new_functionality(make_jira_issue, make_confluence_page):
    # Create custom test data
    issue = make_jira_issue(key="NEW-123")
    page = make_confluence_page(title="New Test Page")

    # Test your functionality
    assert issue["key"] == "NEW-123"
    assert page["title"] == "New Test Page"
```

### For Existing Tests

Existing tests continue to work without changes due to backward compatibility:

```python
def test_existing_functionality(jira_issue_data, confluence_page_data):
    # These fixtures still work as before
    assert jira_issue_data["key"] == "TEST-123"
    assert confluence_page_data["title"] == "Test Page"
```

### Performance Testing

Use large dataset fixtures for performance tests:

```python
def test_performance(large_jira_dataset, large_confluence_dataset):
    # 100 issues and pages for performance testing
    assert len(large_jira_dataset) == 100
    assert len(large_confluence_dataset) == 100
```

## Best Practices

### 1. Choose the Right Fixture

- Use **factory fixtures** for customizable data
- Use **session-scoped fixtures** for static, expensive data
- Use **legacy fixtures** only for backward compatibility

### 2. Session-Scoped Data

Take advantage of session-scoped fixtures for data that doesn't change:

```python
# Good: Uses session-scoped data
def test_field_parsing(session_jira_field_definitions):
    parser = FieldParser(session_jira_field_definitions)
    assert parser.is_valid()

# Avoid: Creates new data every time
def test_field_parsing():
    fields = create_field_definitions()  # Expensive operation
    parser = FieldParser(fields)
    assert parser.is_valid()
```

### 3. Factory Customization

Use factories to create exactly the data you need:

```python
# Good: Creates minimal required data
def test_issue_key_validation(make_jira_issue):
    issue = make_jira_issue(key="VALID-123")
    assert validate_key(issue["key"])

# Avoid: Uses complex data when simple would do
def test_issue_key_validation(complete_jira_issue_data):
    assert validate_key(complete_jira_issue_data["key"])
```

### 4. Environment Testing

Use parametrized fixtures for testing multiple scenarios:

```python
@pytest.mark.parametrize("parametrized_auth_env",
                       ["oauth", "basic_auth", "clean"], indirect=True)
def test_auth_detection(parametrized_auth_env):
    # Test with different auth environments
    detector = AuthDetector()
    auth_type = detector.detect_auth_type()
    assert auth_type in ["oauth", "basic", None]
```

## Backward Compatibility

All existing tests continue to work without modification. The enhanced fixtures:

1. **Maintain existing interfaces**: Old fixture names and return types unchanged
2. **Preserve mock data**: Original mock responses still available
3. **Support gradual migration**: Teams can adopt new fixtures incrementally

## Performance Improvements

The enhanced fixture system provides significant performance improvements:

1. **Session-scoped caching**: Expensive data created once per session
2. **Lazy loading**: Data only created when needed
3. **Efficient factories**: Minimal object creation overhead
4. **Reduced duplication**: Shared fixtures across test modules

## Examples

### Basic Usage

```python
def test_jira_issue_creation(make_jira_issue):
    # Create a custom issue
    issue = make_jira_issue(
        key="TEST-456",
        fields={"summary": "Custom test issue"}
    )

    # Test the issue
    model = JiraIssue.from_dict(issue)
    assert model.key == "TEST-456"
    assert model.summary == "Custom test issue"
```

### Advanced Usage

```python
def test_complex_workflow(
    make_jira_issue_with_worklog,
    make_confluence_page_with_content,
    oauth_environment
):
    # Create issue with worklog
    issue = make_jira_issue_with_worklog(
        key="WORKFLOW-123",
        worklog_hours=8,
        worklog_comment="Development work"
    )

    # Create page with content
    page = make_confluence_page_with_content(
        title="Workflow Documentation",
        content="<h1>Workflow</h1><p>Process documentation</p>",
        labels=["workflow", "documentation"]
    )

    # Test workflow with OAuth environment
    workflow = ComplexWorkflow(issue, page)
    result = workflow.execute()

    assert result.success
    assert result.issue_key == "WORKFLOW-123"
    assert "Workflow Documentation" in result.documentation
```

### Integration Testing

```python
def test_real_api_integration(
    jira_integration_client,
    confluence_integration_client,
    use_real_jira_data,
    use_real_confluence_data
):
    if not use_real_jira_data:
        pytest.skip("Real Jira data not available")

    if not use_real_confluence_data:
        pytest.skip("Real Confluence data not available")

    # Test with real API clients
    issues = jira_integration_client.search_issues("project = TEST")
    pages = confluence_integration_client.get_space_pages("TEST")

    assert len(issues) >= 0
    assert len(pages) >= 0
```

## Conclusion

The enhanced fixture system provides a powerful, flexible, and efficient foundation for testing the MCP Atlassian project. It maintains backward compatibility while offering significant improvements in performance, reusability, and developer experience.

Key benefits:

- ⚡ **Faster test execution** through session-scoped caching
- 🔧 **More flexible test data** through factory functions
- 🔄 **Better reusability** across test modules
- 📈 **Improved maintainability** with clear separation of concerns
- 🛡️ **Backward compatibility** with existing tests

For questions or suggestions about the fixture system, please refer to the test utilities documentation in `tests/utils/`.
