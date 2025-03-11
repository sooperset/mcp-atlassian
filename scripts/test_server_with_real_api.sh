#!/bin/bash

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Please create it with your Atlassian credentials."
    exit 1
fi

# Load environment variables
source .env

# Set required test variables
export JIRA_TEST_ISSUE_KEY="TES-26"
export JIRA_TEST_EPIC_KEY="TES-25"
export CONFLUENCE_TEST_PAGE_ID="3823370492"

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

# Run the tests using pytest with both asyncio and trio backends
echo "Running API validation tests with real data..."
uv run pytest tests/test_real_api_validation.py::test_jira_get_issue tests/test_real_api_validation.py::test_jira_get_epic_issues tests/test_real_api_validation.py::test_confluence_get_page_content -v
