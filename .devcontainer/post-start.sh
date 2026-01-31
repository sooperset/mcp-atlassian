#! /bin/bash

set -xe

# Pre-commit hooks cannot be installed in devcontainer due to Windows mount permissions
# The hooks are already installed on the Windows host from Phase 0
# In the container, run checks manually: pre-commit run --all-files

# Ensure git safe.directory is set (in case post-create didn't run)
git config --global --add safe.directory /workspaces/mcp-atlassian 2>/dev/null || true

echo "✅ Container ready! Run 'pre-commit run --all-files' to check code quality."
