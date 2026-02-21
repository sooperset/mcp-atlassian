#!/bin/bash

# Unified script for testing with real Atlassian data
# Supports testing models or running E2E tests against DC/Cloud instances

# Default settings
TEST_TYPE="all"  # Can be "all", "models", "e2e", or "cloud"
VERBOSITY="-v"   # Verbosity level
FILTER=""        # Test filter using pytest's -k option

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --models-only)
      TEST_TYPE="models"
      shift
      ;;
    --e2e-only)
      TEST_TYPE="e2e"
      shift
      ;;
    --cloud-only)
      TEST_TYPE="cloud"
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
    -k)
      FILTER="-k \"$2\""
      shift
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --models-only          Test only Pydantic models with real data"
      echo "  --e2e-only             Run only DC E2E tests against DC instances"
      echo "  --cloud-only           Run only Cloud E2E tests against Cloud instances"
      echo "  --all                  Test models + DC E2E (default)"
      echo "  --quiet                Minimal output"
      echo "  --verbose              More detailed output"
      echo "  -k \"PATTERN\"         Only run tests matching the given pattern"
      echo "  --help                 Show this help message"
      echo ""
      echo "Prerequisites for DC E2E tests:"
      echo "  1. Start DC instances: cd tests/e2e/docker && docker compose --env-file .env.example up -d"
      echo "  2. Complete setup wizard in browser (first time only)"
      echo "  3. Create test data: bash tests/e2e/docker/setup-test-data.sh"
      echo ""
      echo "Prerequisites for Cloud E2E tests:"
      echo "  Set CLOUD_E2E_JIRA_URL, CLOUD_E2E_CONFLUENCE_URL,"
      echo "  CLOUD_E2E_USERNAME, and CLOUD_E2E_API_TOKEN env vars."
      echo "  Optionally set CLOUD_E2E_OAUTH_ACCESS_TOKEN and CLOUD_E2E_OAUTH_CLOUD_ID."
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
    echo "Note: .env file not found. Using defaults for DC instances (localhost:8080/8090)."
else
    source .env
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

# Function to run DC E2E tests
run_e2e_tests() {
    echo ""
    echo "===== E2E Tests against DC Instances ====="

    if [[ -n "$FILTER" ]]; then
        echo "Running DC E2E tests with filter: $FILTER"
        eval "uv run pytest tests/e2e/ --dc-e2e -xvs $FILTER"
        return
    fi

    uv run pytest tests/e2e/ --dc-e2e -xvs $VERBOSITY
}

# Function to run Cloud E2E tests
run_cloud_tests() {
    echo ""
    echo "===== E2E Tests against Cloud Instances ====="

    if [[ -n "$FILTER" ]]; then
        echo "Running Cloud E2E tests with filter: $FILTER"
        eval "uv run pytest tests/e2e/cloud/ --cloud-e2e -xvs $FILTER"
        return
    fi

    uv run pytest tests/e2e/cloud/ --cloud-e2e -xvs $VERBOSITY
}

# Run the appropriate tests based on the selected type
case $TEST_TYPE in
    "models")
        run_model_tests
        ;;
    "e2e")
        run_e2e_tests
        ;;
    "cloud")
        run_cloud_tests
        ;;
    "all")
        run_model_tests
        run_e2e_tests
        ;;
esac

echo ""
echo "Testing completed. Check the output for any failures or skipped tests."
