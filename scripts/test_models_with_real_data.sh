#!/bin/bash

# This script sets up the environment for testing with real Atlassian data
# and runs the model tests against real Jira and Confluence instances.

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Please create it with your Atlassian credentials."
    exit 1
fi

# Set environment variable to enable real data testing
export USE_REAL_DATA=true

# Load environment variables from .env
source .env

# Run the tests
echo "Running Pydantic model tests with real data..."
echo ""

echo "===== Base Model Tests ====="
uv run pytest tests/unit/models/test_base_models.py -v

echo ""
echo "===== Jira Model Tests ====="
uv run pytest tests/unit/models/test_jira_models.py::TestRealJiraData -v

echo ""
echo "===== Confluence Model Tests ====="
uv run pytest tests/unit/models/test_confluence_models.py::TestRealConfluenceData -v

echo ""
echo "===== API Validation Tests ====="
uv run pytest tests/test_real_api_validation.py --use-real-data -v

echo ""
echo "Testing completed. Check the output for any failures."
