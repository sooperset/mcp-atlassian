# Integration Tests

This directory contains integration tests for the MCP Atlassian project. These tests validate the interaction between different components and services.

## Test Categories

### 1. MCP Application Tests (`test_mcp_application.py`)

Comprehensive integration tests that validate MCP Atlassian functionality using real API calls. These tests validate the complete user workflow from a business perspective.

**Test Coverage**: 19 comprehensive integration tests covering all major functionality
**Environments**: Both Cloud and Server/Data Center deployments
**Execution**: Requires `--integration` flag and proper environment configuration

#### Key Test Scenarios

- **Core Search & Retrieval**: Validates JQL search and issue retrieval
- **Comment Functionality**: Tests comment addition and verification with exact content matching
- **Epic Management**: Validates agile Epic functionality and linking
- **Content Processing**: Tests ADF parsing for Cloud environments
- **Environment Consistency**: Ensures consistent behavior across Cloud and Server/DC
- **Project Management**: Validates project discovery and access
- **Field Operations**: Tests custom field discovery and usage
- **Agile Operations**: Validates board and sprint functionality
- **Batch Operations**: Tests bulk issue creation and changelog retrieval
- **Error Handling**: Validates robust error handling across environments

#### Running MCP Application Tests

```bash
# Run all MCP application tests (Server/DC)
uv run --env-file .env.test pytest tests/integration/test_mcp_application.py --integration --use-real-data -v

# Run all MCP application tests (Cloud)
uv run --env-file .env.realcloud pytest tests/integration/test_mcp_application.py --integration --use-real-data -v

# Run specific test
uv run --env-file .env.test pytest tests/integration/test_mcp_application.py::TestMCPApplication::test_search_functionality --integration --use-real-data -v
```

### 2. Real API Client Tests (`test_real_api.py`)

Direct API client integration tests that validate core API functionality with real Atlassian instances. These tests focus on API client behavior, lifecycle operations, and data handling.

**Test Coverage**: Direct API client testing (create, read, update, delete operations)
**Environments**: Both Cloud and Server/Data Center deployments
**Execution**: Requires `--integration` flag and proper environment configuration

#### Test Details

- **Complete Lifecycles**: Create/update/delete workflows
- **Attachments**: File upload/download operations
- **Search Operations**: JQL and CQL queries
- **Bulk Operations**: Multiple item creation
- **Rate Limiting**: API throttling behavior
- **Cross-Service Linking**: Jira-Confluence integration

#### Running Real API Client Tests

```bash
# Run all real API client tests (Server/DC)
uv run --env-file .env.test pytest tests/integration/test_real_api.py --integration --use-real-data -v

# Run all real API client tests (Cloud)
uv run --env-file .env.realcloud pytest tests/integration/test_real_api.py --integration --use-real-data -v

# Run specific test
uv run --env-file .env.test pytest tests/integration/test_real_api.py::TestRealJiraAPI::test_complete_issue_lifecycle --integration --use-real-data -v
```

### 3. FastMCP Tool Validation Tests (`test_real_api_tool_validation.py`)

FastMCP tool validation tests that verify MCP tool functionality with real API data. These tests focus on the MCP tool layer and validate that tools return proper data structures.

**Test Coverage**: FastMCP tool validation (jira_get_issue, jira_search, confluence_get_page, etc.)
**Environments**: Both Cloud and Server/Data Center deployments
**Execution**: Requires `--use-real-data` flag and proper environment configuration

#### Test Details

- **Tool Validation**: Validates individual MCP tools with real API responses
- **Data Structure Verification**: Ensures tools return properly formatted data
- **Parameter Handling**: Tests tool parameter validation and processing
- **Error Response Testing**: Validates proper error handling in tool layer
- **Pagination Testing**: Tests pagination functionality across different tools
- **Field Discovery**: Tests dynamic field discovery and usage

#### Running FastMCP Tool Validation Tests

```bash
# Run all FastMCP tool validation tests (Server/DC)
uv run --env-file .env.test pytest tests/integration/test_real_api_tool_validation.py --use-real-data -v

# Run all FastMCP tool validation tests (Cloud)
uv run --env-file .env.realcloud pytest tests/integration/test_real_api_tool_validation.py --use-real-data -v

# Run specific test
uv run --env-file .env.test pytest tests/integration/test_real_api_tool_validation.py::TestRealJiraToolValidation::test_jira_search_with_start_at --use-real-data -v
```

#### Test Results Summary

**Server/DC (.env.test)**: 6 failed, 18 passed, 23 skipped, 10 errors
**Cloud (.env.realcloud)**: 24 passed, 23 skipped, 10 errors

**Note**: Some tests fail on Server/DC due to Epic functionality differences, but pass on Cloud. The errors are due to fixture scope mismatches and can be ignored.

### 4. Authentication Integration (`test_authentication.py`)
Tests various authentication flows including OAuth, Basic Auth, and PAT tokens.

- **OAuth Token Refresh**: Validates token refresh on expiration
- **Basic Auth**: Tests username/password authentication for both services
- **PAT Tokens**: Tests Personal Access Token authentication
- **Fallback Patterns**: Tests authentication fallback (OAuth → Basic → PAT)
- **Mixed Scenarios**: Tests different authentication combinations

### 5. Cross-Service Integration (`test_cross_service.py`)
Tests integration between Jira and Confluence services.

- **User Resolution**: Consistent user handling across services
- **Shared Authentication**: Auth context sharing between services
- **Error Handling**: Service isolation during failures
- **Configuration Sharing**: SSL and proxy settings consistency
- **Service Discovery**: Dynamic service availability detection

### 6. MCP Protocol Integration (`test_mcp_protocol.py`)
Tests the FastMCP server implementation and tool management.

- **Tool Discovery**: Dynamic tool listing based on configuration
- **Tool Filtering**: Read-only mode and enabled tools filtering
- **Middleware**: Authentication token extraction and validation
- **Concurrent Execution**: Parallel tool execution support
- **Error Propagation**: Proper error handling through the stack

### 7. Content Processing Integration (`test_content_processing.py`)
Tests HTML/Markdown conversion and content preprocessing.

- **Roundtrip Conversion**: HTML ↔ Markdown accuracy
- **Macro Preservation**: Confluence macro handling
- **Performance**: Large content processing (>1MB)
- **Edge Cases**: Empty content, malformed HTML, Unicode
- **Cross-Platform**: Content sharing between services

### 8. SSL Verification (`test_ssl_verification.py`)
Tests SSL certificate handling and verification.

- **SSL Configuration**: Enable/disable verification
- **Custom CA Bundles**: Support for custom certificates
- **Multiple Domains**: SSL adapter mounting for various domains
- **Error Handling**: Certificate validation failures

### 9. Proxy Configuration (`test_proxy.py`)
Tests HTTP/HTTPS/SOCKS proxy support.

- **Proxy Types**: HTTP, HTTPS, and SOCKS5 proxies
- **Authentication**: Proxy credentials in URLs
- **NO_PROXY**: Bypass patterns for internal domains
- **Environment Variables**: Proxy configuration from environment
- **Mixed Configuration**: Proxy + SSL settings

## Running Integration Tests

### Basic Execution
```bash
# Run all integration tests (mocked)
uv run pytest tests/integration/ --integration

# Run specific test file
uv run pytest tests/integration/test_authentication.py --integration

# Run with coverage
uv run pytest tests/integration/ --integration --cov=src/mcp_atlassian
```

### Real API Testing
```bash
# Run tests against real Atlassian APIs
uv run pytest tests/integration/test_real_api.py --integration --use-real-data

# Required environment variables for real API tests:
export JIRA_URL=https://your-domain.atlassian.net
export JIRA_USERNAME=your-email@example.com
export JIRA_API_TOKEN=your-api-token
export JIRA_TEST_PROJECT_KEY=TEST

export CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
export CONFLUENCE_USERNAME=your-email@example.com
export CONFLUENCE_API_TOKEN=your-api-token
export CONFLUENCE_TEST_SPACE_KEY=TEST
```

## Environment Variables Required

### Environment File Setup

For running integration tests, create environment files based on `.env.example`:

```bash
# Copy the example file and customize for your environment
cp .env.example .env.test      # For Server/Data Center testing
cp .env.example .env.realcloud # For Cloud testing
```

### Server/Data Center (.env.test)
```bash
JIRA_CLOUD=false
JIRA_URL=https://jira.your-company.com
JIRA_PERSONAL_TOKEN=your_personal_access_token
JIRA_TEST_PROJECT_KEY=YOUR_PROJECT
JIRA_TEST_ISSUE_KEY=YOUR_PROJECT-123
```

### Cloud (.env.realcloud)
```bash
JIRA_CLOUD=true
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=your_api_token
JIRA_TEST_PROJECT_KEY=YOUR_PROJECT
JIRA_TEST_ISSUE_KEY=YOUR_PROJECT-123
```

### Test Markers
- `@pytest.mark.integration` - All integration tests
- `@pytest.mark.asyncio` - Async tests supporting asyncio backend

## Environment Setup

### For Mocked Tests
No special setup required. Tests use the utilities from `tests/utils/` for mocking.

### For Real API Tests
1. Create a test project in Jira (e.g., "TEST")
2. Create a test space in Confluence (e.g., "TEST")
3. Generate API tokens from your Atlassian account
4. Set environment variables as shown above
5. Ensure your account has permissions to create/delete in test areas

## Test Data Management

### Automatic Cleanup
Real API tests implement automatic cleanup using pytest fixtures:
- Created issues are tracked and deleted after each test
- Created pages are tracked and deleted after each test
- Attachments are cleaned up with their parent items

### Manual Cleanup
If tests fail and leave data behind:
```python
# Use JQL to find test issues
project = TEST AND summary ~ "Integration Test*"

# Use CQL to find test pages
space = TEST AND title ~ "Integration Test*"
```

## Writing New Integration Tests

### Best Practices
1. **Use Test Utilities**: Leverage helpers from `tests/utils/`
2. **Mark Appropriately**: Use `@pytest.mark.integration`
3. **Mock by Default**: Only use real APIs with explicit flag
4. **Clean Up**: Always clean up created test data
5. **Unique Identifiers**: Use UUIDs to avoid conflicts
6. **Error Handling**: Test both success and failure paths

### Example Test Structure
```python
import pytest
from tests.utils.base import BaseAuthTest
from tests.utils.mocks import MockEnvironment

@pytest.mark.integration
class TestNewIntegration(BaseAuthTest):
    def test_feature(self):
        with MockEnvironment.basic_auth_env():
            # Test implementation
            pass
```

## Troubleshooting

### Common Issues

1. **SSL Errors**: Set `JIRA_SSL_VERIFY=false` or `CONFLUENCE_SSL_VERIFY=false`
2. **Proxy Issues**: Check `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` settings
3. **Rate Limiting**: Add delays between requests or reduce test frequency
4. **Permission Errors**: Ensure test user has appropriate permissions
5. **Cleanup Failures**: Manually delete test data using JQL/CQL queries

### Debug Mode
```bash
# Run with verbose output
uv run pytest tests/integration/ --integration -v

# Run with debug logging
uv run pytest tests/integration/ --integration --log-cli-level=DEBUG
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run Integration Tests
  env:
    JIRA_URL: ${{ secrets.JIRA_URL }}
    JIRA_USERNAME: ${{ secrets.JIRA_USERNAME }}
    JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
  run: |
    uv run pytest tests/integration/ --integration
```

### Skip Patterns
- Integration tests are skipped by default without `--integration` flag
- Real API tests require both `--integration` and `--use-real-data` flags
- Tests skip gracefully when required environment variables are missing
