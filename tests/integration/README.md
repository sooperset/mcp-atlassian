# Integration Tests Documentation

This directory contains integration tests that validate MCP Atlassian functionality using real API calls to Atlassian instances.

## Test Files Overview

### 1. MCP Application Tests (`test_mcp_application.py`)

Comprehensive integration tests that validate MCP Atlassian functionality using real API calls. These tests validate the complete user workflow from a business perspective.

**Test Coverage**: 19 comprehensive integration tests covering all major functionality
**Environments**: Both Cloud and Server/Data Center deployments
**Execution**: Requires `--integration` flag and proper environment configuration

#### Running MCP Application Tests

```bash
# Run all integration tests (Server/DC)
uv run --env-file .env.test pytest tests/integration/test_mcp_application.py --integration -v

# Run all integration tests (Cloud)
uv run --env-file .env.realcloud pytest tests/integration/test_mcp_application.py --integration -v

# Run specific test
uv run --env-file .env.test pytest tests/integration/test_mcp_application.py::TestMCPApplication::test_search_functionality --integration -v
```

### 2. Real API Client Tests (`test_real_api.py`)

Direct API client integration tests that validate core API functionality with real Atlassian instances. These tests focus on API client behavior, lifecycle operations, and data handling.

**Test Coverage**: 11 tests covering direct API client testing (create, read, update, delete operations)
**Environments**: Both Cloud and Server/Data Center deployments
**Execution**: Requires `--integration` flag and proper environment configuration

#### Running Real API Client Tests

```bash
# Run all real API client tests (Server/DC)
uv run --env-file .env.test pytest tests/integration/test_real_api.py --integration -v

# Run all real API client tests (Cloud)
uv run --env-file .env.realcloud pytest tests/integration/test_real_api.py --integration -v

# Run specific test
uv run --env-file .env.test pytest tests/integration/test_real_api.py::TestRealJiraAPI::test_complete_issue_lifecycle --integration -v
```

### 3. FastMCP Tool Validation Tests (`test_real_api_tool_validation.py`)

FastMCP tool validation tests that verify MCP tool functionality with real API data. These tests focus on the MCP tool layer and validate that tools return proper data structures.

**Test Coverage**: 57 tests covering FastMCP tool validation (jira_get_issue, jira_search, confluence_get_page, etc.)
**Environments**: Both Cloud and Server/Data Center deployments
**Execution**: No special flags needed (uses environment variables)

#### Running FastMCP Tool Validation Tests

```bash
# Run all FastMCP tool validation tests (Server/DC)
uv run --env-file .env.test pytest tests/integration/test_real_api_tool_validation.py -v

# Run all FastMCP tool validation tests (Cloud)
uv run --env-file .env.realcloud pytest tests/integration/test_real_api_tool_validation.py -v

# Run specific test
uv run --env-file .env.test pytest tests/integration/test_real_api_tool_validation.py::TestRealJiraValidation::test_get_issue -v
```

## Environment Configuration

### Required Environment Variables

**Server/Data Center (.env.test)**:
```bash
JIRA_CLOUD=false
JIRA_URL=https://jira.your-company.com
JIRA_PERSONAL_TOKEN=your_personal_access_token
JIRA_TEST_PROJECT_KEY=YOUR_PROJECT
JIRA_TEST_ISSUE_KEY=YOUR_PROJECT-123
JIRA_TEST_EPIC_KEY=YOUR_PROJECT-456
JIRA_TEST_BOARD_ID=1000
JIRA_TEST_SPRINT_ID=10001

CONFLUENCE_URL=https://confluence.your-company.com
CONFLUENCE_PERSONAL_TOKEN=your_confluence_personal_token
CONFLUENCE_TEST_SPACE_KEY=YOUR_SPACE
CONFLUENCE_TEST_PAGE_ID=123456789

TEST_PROXY_URL=http://test-proxy.example.com:8080
```

**Cloud (.env.realcloud)**:
```bash
JIRA_CLOUD=true
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=your_api_token
JIRA_TEST_PROJECT_KEY=YOUR_PROJECT
JIRA_TEST_ISSUE_KEY=YOUR_PROJECT-123
JIRA_TEST_EPIC_KEY=YOUR_PROJECT-456
JIRA_TEST_BOARD_ID=1000
JIRA_TEST_SPRINT_ID=10001

CONFLUENCE_URL=https://your-company.atlassian.net/wiki
CONFLUENCE_USERNAME=your.email@company.com
CONFLUENCE_API_TOKEN=your_confluence_api_token
CONFLUENCE_TEST_SPACE_KEY=YOUR_SPACE
CONFLUENCE_TEST_PAGE_ID=123456789

TEST_PROXY_URL=http://test-proxy.example.com:8080
```

## Test Execution Patterns

### Integration Test Flags
- `--integration`: Required for comprehensive MCP and direct API client tests
- No special flags: FastMCP tool validation tests run with environment variables only

### Environment Selection
- `.env.test`: Server/Data Center environment with personal access tokens
- `.env.realcloud`: Cloud environment with API tokens and usernames

### Test Categories

#### 1. MCP Application Tests (19 tests)
- Search functionality, issue operations, comment handling
- Epic management, ADF parsing, environment consistency
- Project operations, agile boards, batch operations
- Error handling, pagination behavior differences

#### 2. Real API Client Tests (11 tests)
- Complete issue lifecycle (CRUD operations)
- Attachment upload/download, bulk issue creation, rate limiting
- Page lifecycle, page hierarchy, CQL search, large content handling
- Cross-service Jira-Confluence integration

#### 3. FastMCP Tool Validation Tests (57 tests)
- Core API validation scenarios across Cloud/DC environments
- Tool-specific validation with proper error handling
- Pagination testing with startAt → start_at parameter fixes
- JQL query improvements and Epic functionality testing

## Performance and Compatibility

### Execution Times
- **MCP Application Tests**: ~45s (Server/DC), ~52s (Cloud)
- **Real API Client Tests**: ~22s (Server/DC), ~29s (Cloud)
- **Tool Validation Tests**: Variable based on test selection

### Environment Compatibility
- **100% pass rate** verified in both Server/DC and Cloud environments
- **Cross-environment consistency** validated for all major operations
- **API compatibility** confirmed for pagination and search operations

## Key Test Scenarios

### Core Search & Retrieval
- Validates JQL search and issue retrieval across environments
- Tests pagination with proper startAt → start_at parameter handling
- Verifies API response parsing for paginated results

### Comment Functionality
- Tests comment addition and verification with exact content matching
- Validates ADF parsing for Cloud environments
- Ensures consistent comment handling across platforms

### Epic Management
- Validates agile Epic functionality and linking
- Tests Epic-to-issue relationships with proper JQL queries
- Handles Epic functionality differences between Cloud and Server/DC

### Environment Consistency
- Ensures consistent behavior across Cloud and Server/DC deployments
- Validates API compatibility for different endpoint patterns
- Tests authentication methods (API tokens vs personal access tokens)

### Error Handling
- Validates robust error handling across environments
- Tests skip conditions for insufficient test data
- Ensures graceful handling of API differences

This comprehensive integration test suite provides confidence in MCP Atlassian functionality across all supported Atlassian deployment types.
