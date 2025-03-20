# GitHub Actions Test Workflow

## Overview

This document describes the GitHub Actions test workflow implementation for the MCP Atlassian integration.

## Test Workflow

The GitHub Actions test workflow has been implemented to automatically validate the MCP Atlassian server functionality. It runs on every pull request and push to the main branch.

### Workflow File

The workflow is defined in `.github/workflows/test.yml` and performs the following steps:

1. Checks out the repository
2. Sets up Python 3.10
3. Installs the `uv` package manager
4. Installs project dependencies
5. Creates the necessary MCP configuration
6. Installs mcp-atlassian in development mode
7. Runs the Atlassian test script

### Test Script

The test script (`src/mcp_atlassian/test_mcp_atlassian.py`) validates:

- Whether `uv` is installed
- Whether `mcp-atlassian` is installed
- Validates the MCP configuration
- Tests starting the MCP Atlassian server

## Linting

The existing lint workflow (`.github/workflows/lint.yml`) has been updated to include linting of test files using flake8.

## Pre-commit Integration

The test script has also been integrated into the pre-commit hooks to ensure validation is performed before each commit. This was added as a local hook in the `.pre-commit-config.yaml` file:

```yaml
# Custom local hooks
- repo: local
  hooks:
    - id: atlassian-test
      name: MCP Atlassian Test
      entry: python src/mcp_atlassian/test_mcp_atlassian.py
      language: system
      pass_filenames: false
      files: ^src/mcp_atlassian/
      always_run: true
```

This hook will:

- Run on every commit that modifies files in the `src/mcp_atlassian/` directory
- Execute the test script to validate the MCP Atlassian server functionality
- Fail the commit if the test script returns a non-zero exit code

## Implementation Details

The test workflow creates a minimal MCP configuration for testing, including:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "python",
      "args": ["-m", "mcp_atlassian.server"]
    }
  }
}
```

This allows the test script to validate that the server can be started successfully.

## Future Improvements

Potential future improvements for the test workflow include:

1. Adding more comprehensive tests for the API endpoints
2. Adding mock tests for Jira and Confluence integrations
3. Adding code coverage reporting
