#!/bin/bash

# Unified script for testing with real Atlassian data
# Supports testing models, API, or both

# Default settings
TEST_TYPE="all"  # Can be "all", "models", or "api"
VERBOSITY="-v"   # Verbosity level
RUN_WRITE_TESTS=false
FILTER=""        # Test filter using pytest's -k option

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --models-only)
      TEST_TYPE="models"
      shift
      ;;
    --api-only)
      TEST_TYPE="api"
      shift
      ;;
    --all)
      TEST_TYPE="all"
      shift
      ;;
    --quiet)
      VERBOSITY=""
      shift
      ;;
    --verbose)
      VERBOSITY="-vv"
      shift
      ;;
    --with-write-tests)
      RUN_WRITE_TESTS=true
      shift
      ;;
    -k)
      FILTER="-k \"$2\""
      shift
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --models-only          Test only Pydantic models"
      echo "  --api-only             Test only API integration"
      echo "  --all                  Test both models and API (default)"
      echo "  --quiet                Minimal output"
      echo "  --verbose              More detailed output"
      echo "  --with-write-tests     Include tests that modify data (including TextContent validation)"
      echo "  -k \"PATTERN\"         Only run tests matching the given pattern (uses pytest's -k option)"
      echo "  --help                 Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Tests will be skipped if environment variables are not set."
else
    # Load environment variables from .env
    source .env
fi

# Set environment variable to enable real data testing
export USE_REAL_DATA=true

# Set specific test IDs for API validation tests
# These will be used if they're set, otherwise tests will be skipped
export JIRA_TEST_ISSUE_KEY="${JIRA_TEST_ISSUE_KEY:-}"
export JIRA_TEST_EPIC_KEY="${JIRA_TEST_EPIC_KEY:-}"
export CONFLUENCE_TEST_PAGE_ID="${CONFLUENCE_TEST_PAGE_ID:-}"
export JIRA_TEST_PROJECT_KEY="${JIRA_TEST_PROJECT_KEY:-}"
export CONFLUENCE_TEST_SPACE_KEY="${CONFLUENCE_TEST_SPACE_KEY:-}"

# Check required environment variables and warn if any are missing
required_vars=(
    "JIRA_URL"
    "JIRA_USERNAME"
    "JIRA_API_TOKEN"
    "CONFLUENCE_URL"
    "CONFLUENCE_USERNAME"
    "CONFLUENCE_API_TOKEN"
)

missing_vars=0
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Warning: Environment variable $var is not set. Some tests will be skipped."
        missing_vars=$((missing_vars+1))
    fi
done

if [ $missing_vars -gt 0 ]; then
    echo "Found $missing_vars missing required variables. Tests requiring these variables will be skipped."
    echo "You can set these in your .env file to run all tests."
fi

# Function to run model tests
run_model_tests() {
    echo "Running Pydantic model tests with real data..."
    echo ""

    echo "===== Base Model Tests ====="
    uv run pytest tests/unit/models/test_base_models.py $VERBOSITY

    echo ""
    echo "===== Jira Model Tests ====="
    uv run pytest tests/unit/models/test_jira_models.py::TestRealJiraData $VERBOSITY

    echo ""
    echo "===== Confluence Model Tests ====="
    uv run pytest tests/unit/models/test_confluence_models.py::TestRealConfluenceData $VERBOSITY
}

# Function to run API tests
run_api_tests() {
    echo ""
    echo "===== API Read-Only Tests ====="

    # If a filter is provided, run all tests with that filter
    if [[ -n "$FILTER" ]]; then
        echo "Running tests with filter: $FILTER"
        eval "uv run pytest tests/test_real_api_validation.py $VERBOSITY $FILTER"
        return
    fi

    # Otherwise run specific tests based on write/read only setting
    # Run the read-only tests
    uv run pytest tests/test_real_api_validation.py::test_jira_get_issue tests/test_real_api_validation.py::test_jira_get_issue_with_fields tests/test_real_api_validation.py::test_jira_get_epic_issues tests/test_real_api_validation.py::test_confluence_get_page_content $VERBOSITY

    if [[ "$RUN_WRITE_TESTS" == "true" ]]; then
        echo ""
        echo "===== API Write Operation Tests ====="
        echo "WARNING: These tests will create and modify data in your Atlassian instance."
        echo "Press Ctrl+C now to cancel, or wait 5 seconds to continue..."
        sleep 5

        # Run the write operation tests
        uv run pytest tests/test_real_api_validation.py::test_jira_create_issue tests/test_real_api_validation.py::test_jira_create_subtask tests/test_real_api_validation.py::test_jira_create_task_with_parent tests/test_real_api_validation.py::test_jira_add_comment tests/test_real_api_validation.py::test_confluence_create_page tests/test_real_api_validation.py::test_confluence_update_page tests/test_real_api_validation.py::test_jira_create_epic tests/test_real_api_validation.py::test_jira_create_epic_two_step $VERBOSITY

        # Run the skipped transition test if explicitly requested write tests
        echo ""
        echo "===== API Advanced Write Tests ====="
        echo "Running tests for status transitions"
        uv run pytest tests/test_real_api_validation.py::test_jira_transition_issue -v -k "test_jira_transition_issue"
    fi
}

# Run the appropriate tests based on the selected type
case $TEST_TYPE in
    "models")
        run_model_tests
        ;;
    "api")
        run_api_tests
        ;;
    "all")
        run_model_tests
        run_api_tests
        ;;
esac

echo ""
echo "Testing completed. Check the output for any failures or skipped tests."
