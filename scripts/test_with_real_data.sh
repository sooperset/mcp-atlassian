#!/bin/bash

# Unified script for testing with real Atlassian data
# Supports testing models, API, or both

# Default settings
TEST_TYPE="all"  # Can be "all", "models", or "api"
VERBOSITY="-v"   # Verbosity level

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
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --models-only      Test only Pydantic models"
      echo "  --api-only         Test only API integration"
      echo "  --all              Test both models and API (default)"
      echo "  --quiet            Minimal output"
      echo "  --verbose          More detailed output"
      echo "  --with-write-tests Include tests that modify data (use with caution!)"
      echo "  --help             Show this help message"
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
    echo "Error: .env file not found. Please create it with your Atlassian credentials."
    exit 1
fi

# Set environment variable to enable real data testing
export USE_REAL_DATA=true

# Load environment variables from .env
source .env

# Set specific test IDs for API validation tests
export JIRA_TEST_ISSUE_KEY="TES-26"
export JIRA_TEST_EPIC_KEY="TES-25"
export CONFLUENCE_TEST_PAGE_ID="3823370492"
export JIRA_TEST_PROJECT_KEY="TES"
export CONFLUENCE_TEST_SPACE_KEY="TestMCP"

# Ensure required environment variables are set
required_vars=(
    "JIRA_URL"
    "JIRA_USERNAME"
    "JIRA_API_TOKEN"
    "CONFLUENCE_URL"
    "CONFLUENCE_USERNAME"
    "CONFLUENCE_API_TOKEN"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required environment variable $var is not set in .env file."
        exit 1
    fi
done

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

    # Run the read-only tests
    uv run pytest tests/test_real_api_validation.py::test_jira_get_issue tests/test_real_api_validation.py::test_jira_get_epic_issues tests/test_real_api_validation.py::test_confluence_get_page_content $VERBOSITY

    if [[ "$RUN_WRITE_TESTS" == "true" ]]; then
        echo ""
        echo "===== API Write Operation Tests ====="
        echo "WARNING: These tests will create and modify data in your Atlassian instance."
        echo "Press Ctrl+C now to cancel, or wait 5 seconds to continue..."
        sleep 5

        # Run the write operation tests
        uv run pytest tests/test_real_api_validation.py::test_jira_create_issue tests/test_real_api_validation.py::test_jira_add_comment tests/test_real_api_validation.py::test_confluence_create_page $VERBOSITY
        # Optionally run the skipped tests if explicitly requested
        if [[ "$RUN_WRITE_TESTS" == "true" ]]; then
            echo ""
            echo "===== API Advanced Write Tests ====="
            # These are still skipped by default, so we need to use -k to enable them
            uv run pytest tests/test_real_api_validation.py::test_jira_transition_issue tests/test_real_api_validation.py::test_confluence_update_page -v
        fi
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
echo "Testing completed. Check the output for any failures."
