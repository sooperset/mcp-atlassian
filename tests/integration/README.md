# Integration Tests

This directory contains integration tests for the MCP Atlassian project. These tests validate the interaction between different components and services.

## Test Categories

### 1. Authentication Integration (`test_authentication.py`)
Tests various authentication flows including OAuth, Basic Auth, and PAT tokens.

- **OAuth Token Refresh**: Validates token refresh on expiration
- **Basic Auth**: Tests username/password authentication for both services
- **PAT Tokens**: Tests Personal Access Token authentication
- **Fallback Patterns**: Tests authentication fallback (OAuth → Basic → PAT)
- **Mixed Scenarios**: Tests different authentication combinations

### 2. Cross-Service Integration (`test_cross_service.py`)
Tests integration between Jira and Confluence services.

- **User Resolution**: Consistent user handling across services
- **Shared Authentication**: Auth context sharing between services
- **Error Handling**: Service isolation during failures
- **Configuration Sharing**: SSL and proxy settings consistency
- **Service Discovery**: Dynamic service availability detection

### 3. MCP Protocol Integration (`test_mcp_protocol.py`)
Tests the FastMCP server implementation and tool management.

- **Tool Discovery**: Dynamic tool listing based on configuration
- **Tool Filtering**: Read-only mode and enabled tools filtering
- **Middleware**: Authentication token extraction and validation
- **Concurrent Execution**: Parallel tool execution support
- **Error Propagation**: Proper error handling through the stack

### 4. Content Processing Integration (`test_content_processing.py`)
Tests HTML/Markdown conversion and content preprocessing.

- **Roundtrip Conversion**: HTML ↔ Markdown accuracy
- **Macro Preservation**: Confluence macro handling
- **Performance**: Large content processing (>1MB)
- **Edge Cases**: Empty content, malformed HTML, Unicode
- **Cross-Platform**: Content sharing between services

### 5. SSL Verification (`test_ssl_verification.py`)
Tests SSL certificate handling and verification.

- **SSL Configuration**: Enable/disable verification
- **Custom CA Bundles**: Support for custom certificates
- **Multiple Domains**: SSL adapter mounting for various domains
- **Error Handling**: Certificate validation failures

### 6. Proxy Configuration (`test_proxy.py`)
Tests HTTP/HTTPS/SOCKS proxy support.

- **Proxy Types**: HTTP, HTTPS, and SOCKS5 proxies
- **Authentication**: Proxy credentials in URLs
- **NO_PROXY**: Bypass patterns for internal domains
- **Environment Variables**: Proxy configuration from environment
- **Mixed Configuration**: Proxy + SSL settings

### 7. Real API Tests (`test_real_api.py`)
Tests with actual Atlassian APIs (requires `--use-real-data` flag).

- **Complete Lifecycles**: Create/update/delete workflows
- **Attachments**: File upload/download operations
- **Search Operations**: JQL and CQL queries
- **Bulk Operations**: Multiple item creation
- **Rate Limiting**: API throttling behavior
- **Cross-Service Linking**: Jira-Confluence integration

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

### Test Markers
- `@pytest.mark.integration` - All integration tests
- `@pytest.mark.anyio` - Async tests supporting multiple backends

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
